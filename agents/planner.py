import json
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()
_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-120b"

PLANNER_PROMPT = """You are a research planner. Given a user's question, break it down into 2 to 3 specific, \
searchable sub-questions that together would help answer the original question thoroughly.

Respond ONLY with a JSON object in this exact format, nothing else:
{"sub_questions": ["sub-question 1", "sub-question 2", "sub-question 3"]}

If the question is already simple and specific, you may return just 1 sub-question."""


def plan(user_question: str) -> list[str]:
    """Decompose une question en sous-questions de recherche."""
    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": user_question},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    try:
        data = json.loads(content)
        return data.get("sub_questions", [user_question])
    except (json.JSONDecodeError, KeyError):
        # fallback: si le LLM n'a pas respecte le format, on traite la question telle quelle
        return [user_question]