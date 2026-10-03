import time

from agents.planner import plan
from agents.researcher import research
from agents.synthesizer import synthesize


def run_research_pipeline(question: str) -> dict:
    """
    Execute le pipeline complet: planification -> recherche -> synthese.
    Renvoie le rapport final + les etapes intermediaires (utile pour l'UI).
    """
    steps = []
    start = time.time()

    sub_questions = plan(question)
    steps.append({"stage": "planning", "sub_questions": sub_questions})

    research_results = []
    for sq in sub_questions:
        result = research(sq)
        research_results.append(result)
        steps.append({
            "stage": "research",
            "sub_question": sq,
            "sources_count": len(result.get("sources", [])),
        })

    report = synthesize(question, research_results)
    steps.append({"stage": "synthesis", "done": True})

    all_sources = sorted({
        url for r in research_results for url in r.get("sources", [])
    })

    return {
        "question": question,
        "report": report,
        "sub_questions": sub_questions,
        "sources": all_sources,
        "steps": steps,
        "duration_seconds": round(time.time() - start, 1),
    }