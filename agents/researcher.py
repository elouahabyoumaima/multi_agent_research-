import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools.tavily_search import web_search
from tools.mcp_client import fetch_url

load_dotenv()
_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-120b"

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

RESEARCHER_PROMPT = """You are a research assistant. For the given sub-question, use the available tools \
to gather real information, then write a concise summary (3-5 sentences) of what you found, citing sources by URL.

IMPORTANT: Call a tool AT MOST ONCE (twice maximum if the first result is insufficient). \
After that, you MUST write your summary based on what you have, even if imperfect. \
Do not keep searching repeatedly."""


def research(sub_question: str) -> dict:
    """Effectue la recherche pour une sous-question et renvoie un resume + les sources utilisees."""
    messages = [
        {"role": "system", "content": RESEARCHER_PROMPT},
        {"role": "user", "content": sub_question},
    ]
    sources = []

    for _ in range(5):  # max 5 etapes (appel outil -> reponse) par securite
        try:
            response = _client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0,
            )
        except Exception as e:
            return {
                "sub_question": sub_question,
                "summary": f"Erreur lors de la recherche: {e}",
                "sources": sources,
            }
        msg = response.choices[0].message

        if not msg.tool_calls:
            return {"sub_question": sub_question, "summary": msg.content, "sources": sources}

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
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
                    sources.extend(r["url"] for r in result["results"])
                elif "url" in result:
                    sources.append(result["url"])

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str)[:4000],  # on limite la taille envoyee au LLM
            })

    return {"sub_question": sub_question, "summary": "Recherche incomplete (trop d'etapes).", "sources": sources}