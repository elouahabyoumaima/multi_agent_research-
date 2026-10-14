import json
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()
_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-120b"

CRITIC_PROMPT = """You are a strict but fair research reviewer. You receive an original question and the \
research findings gathered so far (each finding answers one sub-question).

Decide whether the findings are sufficient to write a thorough, accurate answer to the ORIGINAL question.
- If an important aspect of the original question is missing, or a key claim has no support, list up to 2 \
specific, searchable follow-up questions that would fill the most important gaps.
- If coverage is reasonable, do not ask for more.
- Never repeat a sub-question that was already researched.
- Write the follow-up questions in the same language as the original question.

Respond ONLY with a JSON object in this exact format, nothing else:
{"sufficient": true, "follow_up_questions": []}
or
{"sufficient": false, "follow_up_questions": ["question 1", "question 2"]}"""


def review(original_question: str, research_results: list[dict], max_follow_ups: int = 2) -> list[str]:
    """Evalue les resultats de recherche. Renvoie des questions de suivi (liste vide si c'est suffisant)."""
    findings = "\n\n".join(
        f"Sub-question: {r['sub_question']}\nFindings: {r['summary']}" for r in research_results
    )
    user_content = f"Original question: {original_question}\n\nResearch findings so far:\n{findings}"

    try:
        response = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": CRITIC_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
    except Exception:
        # si la critique echoue, on ne bloque pas le pipeline: on considere que c'est suffisant
        return []

    if data.get("sufficient", True):
        return []

    follow_ups = data.get("follow_up_questions", [])
    if not isinstance(follow_ups, list):
        return []
    return [q.strip() for q in follow_ups if isinstance(q, str) and q.strip()][:max_follow_ups]