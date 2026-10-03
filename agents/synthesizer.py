import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()
_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-120b"

SYNTHESIZER_PROMPT = """You are a research report writer. You are given an original question and a set of \
research summaries (each covering a sub-question with sources). Write a clear, well-structured report in \
Markdown that answers the original question, synthesizing the information into a coherent whole — \
not just listing the summaries one after another. Include a short "Sources" section at the end listing \
all unique URLs used."""


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

    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYNTHESIZER_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,  # un peu de liberte pour une redaction naturelle
    )

    return response.choices[0].message.content