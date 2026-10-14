import os
import time

from dotenv import load_dotenv
from groq import APIConnectionError, BadRequestError, Groq, RateLimitError

load_dotenv()
_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-120b"
FALLBACK_MODEL = "llama-3.3-70b-versatile"
MAX_RETRIES = 3

# protection des tokens: on borne tout ce qu'on envoie au modele
MAX_QUESTION_CHARS = 1000
MAX_REPORT_CHARS = 8000
MAX_HISTORY_TURNS = 3
MAX_ANSWER_CHARS_IN_HISTORY = 1500

FOLLOWUP_PROMPT = """You answer follow-up questions about a research report that was written earlier in \
this conversation. Use ONLY the report and the previous exchanges below. If the answer is not covered, say so \
in one sentence and suggest enabling the web search option. Do not invent facts, numbers or sources. Be \
concise and clear, use Markdown when it helps. Answer in the language of the follow-up question. \
You have NO tools: never call any function."""


def _call(model: str, messages: list[dict]) -> str:
    response = _client.chat.completions.create(model=model, messages=messages, temperature=0.2)
    return (response.choices[0].message.content or "").strip()


def answer_followup(question: str, report: str, history: list[dict] | None = None) -> str:
    """Repond a une question de suivi a partir du rapport et des derniers echanges (sans recherche web)."""
    question = (question or "").strip()[:MAX_QUESTION_CHARS]
    report = (report or "")[:MAX_REPORT_CHARS]
    turns = (history or [])[-MAX_HISTORY_TURNS:]

    messages = [
        {"role": "system", "content": FOLLOWUP_PROMPT + "\n\nResearch report:\n" + report},
    ]
    for t in turns:
        messages.append({"role": "user", "content": str(t.get("q", ""))[:MAX_QUESTION_CHARS]})
        messages.append({"role": "assistant", "content": str(t.get("a", ""))[:MAX_ANSWER_CHARS_IN_HISTORY]})
    messages.append({"role": "user", "content": question})

    last_error = None
    for model in (MODEL, FALLBACK_MODEL):
        for attempt in range(MAX_RETRIES):
            try:
                text = _call(model, messages)
                if text:
                    return text
            except BadRequestError as e:
                last_error = e
                if "tool_use_failed" not in str(e):
                    break
                time.sleep(1 + attempt)
            except RateLimitError as e:
                last_error = e
                time.sleep(4 * (attempt + 1))
            except APIConnectionError as e:
                last_error = e
                time.sleep(2 * (attempt + 1))

    raise RuntimeError(f"Reponse impossible: {last_error}")