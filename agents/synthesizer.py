import os
import time

from dotenv import load_dotenv
from groq import BadRequestError, Groq

load_dotenv()
_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-120b"
FALLBACK_MODEL = "llama-3.3-70b-versatile"
MAX_RETRIES = 3

SYNTHESIZER_PROMPT = """You are a research report writer. You are given an original question and a set of \
research summaries (each covering a sub-question with sources). Write a clear, well-structured report in \
Markdown that answers the original question, synthesizing the information into a coherent whole — \
not just listing the summaries one after another. Include a short "Sources" section at the end listing \
all unique URLs used.

Strict rules:
- Use ONLY information present in the research findings. Do not invent numbers, benchmarks, percentages \
or quotes; if a figure is not in the findings, do not state it (say it is not documented instead).
- Do NOT add "Sources:" lines under individual sections and do NOT attribute a claim to a named source \
unless the findings explicitly say so. Put all URLs only in one final "Sources" section.
- Do NOT use citation markers of any kind (no [1], no \u3010 1 \u3011, no "Reference" column). Tables must not \
have a column of source numbers.
- The final "Sources" section is a plain list of the URLs given (one per line). Add no commentary after it \
(no remark about URLs being unique or listed).
- Write the report in the same language as the original question.

You have NO tools. Never call any function or tool (no code execution, no search). \
Reply only with the final report as plain Markdown text."""


def _call(model: str, messages: list[dict]) -> str:
    response = _client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,  # un peu de liberte pour une redaction naturelle
    )
    return (response.choices[0].message.content or "").strip()


def synthesize(original_question: str, research_results: list[dict]) -> str:
    """Compile les resultats de recherche en un rapport final structure."""
    context_parts = []
    all_sources = set()

    for r in research_results:
        context_parts.append(f"Sub-question: {r['sub_question']}\nFindings: {r['summary']}")
        all_sources.update(r.get("sources", []))

    context = "\n\n".join(context_parts)
    sources_list = "\n".join(f"- {url}" for url in sorted(all_sources))

    user_content = (
        f"Original question: {original_question}\n\n"
        f"Research findings:\n{context}\n\n"
        f"Available sources:\n{sources_list}"
    )

    messages = [
        {"role": "system", "content": SYNTHESIZER_PROMPT},
        {"role": "user", "content": user_content},
    ]

    # 1) gpt-oss-120b : on retente si Groq rejette (tool_use_failed) ou si la reponse est vide
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            text = _call(MODEL, messages)
            if text:
                return text
        except BadRequestError as e:
            last_error = e
            if "tool_use_failed" not in str(e):
                raise
        time.sleep(1 + attempt)

    # 2) Fallback : un modele qui n'essaie pas d'appeler des outils
    try:
        text = _call(FALLBACK_MODEL, messages)
        if text:
            return text
    except Exception as e:
        last_error = e

    raise RuntimeError(f"Synthese impossible apres retries et fallback: {last_error}")