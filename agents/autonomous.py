import json
import os
import time

from dotenv import load_dotenv
from groq import APIConnectionError, BadRequestError, Groq, RateLimitError

from agents.synthesizer import synthesize
from tools.tavily_search import web_search
from tools.mcp_client import fetch_url

load_dotenv()
_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-120b"
MAX_RETRIES = 3
MAX_SEARCHES = 3       # budget: recherches web max
MAX_FETCHES = 2        # budget: pages lues en entier max
MIN_FETCHES = 2        # l'agent doit lire au moins 2 pages avant de finir
MAX_SECONDS = 75       # budget: temps max avant de forcer la redaction
MAX_TURNS = 10         # securite: nombre max de tours LLM
MAX_REFUSALS = 3       # apres 3 appels refuses (doublon / limite), on arrete l'agent
TOOL_OUTPUT_LIMIT = 2500
FINDING_LIMIT = 1500   # taille gardee par resultat pour la redaction finale

_use_effort = {"on": True}  # reasoning_effort=low pour accelerer gpt-oss (desactive si refuse)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web. Use a specific query that covers a NEW angle.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The search query."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Read the full content of ONE URL already found in a search result.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The exact URL."}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "note",
            "description": "Save a short note (a key fact, a number, a gap still to fill) in your scratchpad.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "The note."}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Call this when you have enough information. Another step will write the final report.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string", "description": "Why you can stop."}},
                "required": [],
            },
        },
    },
]

AGENT_PROMPT = """You are an autonomous research agent. Goal: gather enough reliable information to answer \
the user's question well, then stop.

Each turn, call ONE tool:
- web_search: new angle only, never repeat or rephrase a previous query.
- fetch_url: read ONE promising URL in full (never the same URL twice).
- note: record a key fact or a gap.
- finish: call it as soon as the main aspects of the question are covered.

Hard limits: {max_searches} searches and {max_fetches} fetches in total. Read at least {min_fetches} pages with \
fetch_url before finishing; typically 2 searches + 2 fetches is enough. Do not search again unless you name a specific missing aspect. Use ONLY these tools (no code execution). \
Do NOT write the report yourself. Any text you write must be in the language of the question."""


def _chat(messages: list[dict]):
    """Appel Groq avec retry (tool_use_failed, rate limit, reseau)."""
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            kwargs = {
                "model": MODEL,
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
                "temperature": 0,
            }
            if _use_effort["on"]:
                kwargs["extra_body"] = {"reasoning_effort": "low"}
            return _client.chat.completions.create(**kwargs).choices[0].message
        except BadRequestError as e:
            last_error = e
            text = str(e)
            if "tool_use_failed" in text:
                time.sleep(1 + attempt)
            elif _use_effort["on"] and "reasoning" in text.lower():
                _use_effort["on"] = False  # parametre refuse: on reessaie sans
            else:
                raise
        except RateLimitError as e:
            last_error = e
            time.sleep(4 * (attempt + 1))
        except APIConnectionError as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    raise last_error


def run_agent(question: str) -> dict:
    """Agent autonome: decide lui-meme des actions jusqu'a finish ou jusqu'a epuisement du budget."""
    start = time.time()
    steps: list[dict] = []
    queries: list[str] = []
    sources: list[str] = []
    notes: list[str] = []
    findings: list[str] = []
    seen: set[str] = set()
    searches = fetches = turns = refusals = early_stops = 0
    stop_reason = "budget"

    messages = [
        {"role": "system", "content": AGENT_PROMPT.format(max_searches=MAX_SEARCHES, max_fetches=MAX_FETCHES, min_fetches=MIN_FETCHES)},
        {"role": "user", "content": question},
    ]

    while turns < MAX_TURNS and (time.time() - start) < MAX_SECONDS:
        turns += 1
        t0 = time.time()
        try:
            msg = _chat(messages)
        except Exception as e:
            steps.append({"stage": "agent", "action": "error", "detail": str(e)[:200],
                          "seconds": round(time.time() - t0, 1)})
            stop_reason = "error"
            break

        if not msg.tool_calls:
            if fetches < MIN_FETCHES and searches > 0 and early_stops < 2:
                early_stops += 1
                messages.append({"role": "assistant", "content": msg.content or "OK"})
                messages.append({"role": "user", "content":
                                 "Not enough yet: read at least %d page(s) with fetch_url (pick a URL from the "
                                 "search results), then call finish." % (MIN_FETCHES - fetches)})
                continue
            steps.append({"stage": "agent", "action": "done", "detail": (msg.content or "").strip()[:100],
                          "seconds": round(time.time() - t0, 1)})
            stop_reason = "done"
            break

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in msg.tool_calls
            ],
        })

        finished = False
        for call in msg.tool_calls:
            name = call.function.name
            t1 = time.time()
            args = {}
            refused = False
            try:
                args = json.loads(call.function.arguments or "{}")
                key = name + ":" + json.dumps(args, sort_keys=True)
                if name == "finish":
                    if fetches < MIN_FETCHES and searches > 0 and early_stops < 2:
                        early_stops += 1
                        result = {"error": "Read at least %d page(s) with fetch_url before finish."
                                  % (MIN_FETCHES - fetches)}
                    else:
                        finished = True
                        result = {"ok": True}
                elif name == "note":
                    notes.append(str(args.get("text", "")).strip())
                    result = {"ok": True}
                elif name not in ("web_search", "fetch_url"):
                    refused = True
                    result = {"error": "unknown tool " + name}
                elif key in seen:
                    refused = True
                    result = {"error": "already done. Call finish, or use a really different query/url."}
                elif name == "web_search" and searches >= MAX_SEARCHES:
                    refused = True
                    result = {"error": "search limit reached. Call finish."}
                elif name == "fetch_url" and fetches >= MAX_FETCHES:
                    refused = True
                    result = {"error": "fetch limit reached. Call finish."}
                else:
                    seen.add(key)
                    if name == "web_search":
                        searches += 1
                        queries.append(args.get("query", ""))
                        result = web_search(**args)
                    else:
                        fetches += 1
                        result = fetch_url(**args)
            except Exception as e:
                result = {"error": str(e)}

            if refused:
                refusals += 1

            if isinstance(result, dict):
                if "results" in result:
                    sources.extend(r["url"] for r in result["results"] if "url" in r)
                elif "url" in result:
                    sources.append(result["url"])

            hint = "Left: %d search(es), %d fetch(es). If covered, call finish now." % (
                MAX_SEARCHES - searches, MAX_FETCHES - fetches)
            content = json.dumps({"hint": hint, "result": result}, default=str)[:TOOL_OUTPUT_LIMIT]
            if name in ("web_search", "fetch_url") and not refused:
                findings.append(f"[{name}] {json.dumps(result, default=str)[:FINDING_LIMIT]}")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})

            detail = (args.get("query") or args.get("url") or args.get("text") or args.get("reason") or "") \
                if isinstance(args, dict) else ""
            steps.append({"stage": "agent", "action": name + (" (refused)" if refused else ""),
                          "detail": str(detail)[:150], "seconds": round(time.time() - t1, 1)})

        if finished:
            stop_reason = "done"
            break
        if refusals >= MAX_REFUSALS or (searches >= MAX_SEARCHES and fetches >= MAX_FETCHES):
            stop_reason = "limits"
            break

    sources = list(dict.fromkeys(sources))
    t_syn = time.time()
    summary_parts = []
    if notes:
        summary_parts.append("Agent notes:\n" + "\n".join("- " + n for n in notes if n))
    summary_parts.append("Raw findings:\n" + "\n\n".join(findings) if findings else "No findings.")
    report = synthesize(question, [{
        "sub_question": question,
        "summary": "\n\n".join(summary_parts),
        "sources": sources,
    }])
    steps.append({"stage": "synthesis", "done": True, "stop_reason": stop_reason,
                  "seconds": round(time.time() - t_syn, 1)})

    return {
        "question": question,
        "sub_questions": queries or [question],
        "report": report,
        "sources": sources,
        "steps": steps,
        "duration_seconds": round(time.time() - start, 1),
    }