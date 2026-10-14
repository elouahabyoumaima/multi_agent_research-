import json
import os
import time

from dotenv import load_dotenv
from groq import APIConnectionError, BadRequestError, Groq, RateLimitError

from tools.tavily_search import web_search
from tools.mcp_client import fetch_url

load_dotenv()
_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-120b"
FALLBACK_MODEL = "llama-3.3-70b-versatile"
MAX_RETRIES = 3
MAX_TOOL_ROUNDS = 2  # au plus 2 tours d'outils, ensuite on force le resume

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for general information on a topic. Use this by default.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and read the full content of ONE specific URL that is already known "
                           "(e.g. from a previous search result). The tool name is exactly 'fetch_url'. "
                           "Do not use for general searches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The exact URL to fetch."},
                },
                "required": ["url"],
            },
        },
    },
]

TOOL_FUNCTIONS = {"web_search": web_search, "fetch_url": fetch_url}

RESEARCHER_PROMPT = """You are a research assistant. For the given sub-question, use ONLY the two tools \
provided (web_search, fetch_url) to gather real information. Call a tool AT MOST ONCE \
(twice maximum if the first result is insufficient). Never call any other tool (no code execution). \
When you have enough, reply with a concise summary (3-5 sentences), citing sources by URL."""

SUMMARY_PROMPT = """You are a research assistant. You are given a sub-question and raw findings from web \
searches. You have NO tools: never call any function. Write a concise summary (3-5 sentences) that answers \
the sub-question, citing sources by URL. Write in the same language as the sub-question."""


def _chat(model: str, messages: list[dict], tools=None):
    """Appel Groq avec retry (tool_use_failed, rate limit, reseau). Renvoie le message."""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            kwargs = {"model": model, "messages": messages, "temperature": 0}
            if tools:
                kwargs.update(tools=tools, tool_choice="auto")
            return _client.chat.completions.create(**kwargs).choices[0].message
        except BadRequestError as e:
            last_error = e
            if "tool_use_failed" not in str(e):
                raise
            time.sleep(1 + attempt)
        except RateLimitError as e:
            last_error = e
            time.sleep(4 * (attempt + 1))
        except APIConnectionError as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    raise last_error


def _summarize(sub_question: str, observations: list[str]) -> str:
    """Resume final SANS outils (evite que le modele essaie d'appeler un tool)."""
    findings = "\n\n".join(observations) if observations else "(no findings)"
    messages = [
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": f"Sub-question: {sub_question}\n\nFindings:\n{findings}"},
    ]
    last_error = None
    for model in (MODEL, FALLBACK_MODEL):
        try:
            text = (_chat(model, messages).content or "").strip()
            if text:
                return text
        except Exception as e:
            last_error = e
    raise RuntimeError(last_error or "resume vide")


def research(sub_question: str) -> dict:
    """Effectue la recherche pour une sous-question et renvoie un resume + les sources utilisees."""
    messages = [
        {"role": "system", "content": RESEARCHER_PROMPT},
        {"role": "user", "content": sub_question},
    ]
    sources: list[str] = []
    observations: list[str] = []

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            msg = _chat(MODEL, messages, tools=TOOLS)

            if not msg.tool_calls:
                if msg.content and msg.content.strip():
                    return {"sub_question": sub_question, "summary": msg.content.strip(),
                            "sources": list(dict.fromkeys(sources))}
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

            for call in msg.tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                    result = TOOL_FUNCTIONS[name](**args)
                except Exception as e:
                    result = {"error": str(e)}

                # on garde une trace des URLs consultees
                if isinstance(result, dict):
                    if "results" in result:
                        sources.extend(r["url"] for r in result["results"] if "url" in r)
                    elif "url" in result:
                        sources.append(result["url"])

                content = json.dumps(result, default=str)[:3000]  # limite la taille envoyee au LLM
                observations.append(f"[{name}] {content}")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
    except Exception as e:
        # on ne perd pas tout : si on a deja des resultats, on tente quand meme le resume
        if not observations:
            return {"sub_question": sub_question,
                    "summary": f"Erreur lors de la recherche: {e}",
                    "sources": list(dict.fromkeys(sources))}

    try:
        summary = _summarize(sub_question, observations)
    except Exception as e:
        return {"sub_question": sub_question,
                "summary": f"Erreur lors de la recherche: {e}",
                "sources": list(dict.fromkeys(sources))}

    return {"sub_question": sub_question, "summary": summary, "sources": list(dict.fromkeys(sources))}