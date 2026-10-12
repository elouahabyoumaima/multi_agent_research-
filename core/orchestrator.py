import time
from concurrent.futures import ThreadPoolExecutor

from agents.planner import plan
from agents.researcher import research
from agents.synthesizer import synthesize

MAX_PARALLEL = 3  # nombre maximum de recherches lancees en meme temps


def _timed_research(sub_question: str) -> dict:
    """Lance la recherche d'une sous-question et mesure sa duree."""
    start = time.time()
    result = research(sub_question)
    result["seconds"] = round(time.time() - start, 1)
    return result


def run_research_pipeline(question: str) -> dict:
    """
    Execute le pipeline complet: planification -> recherches (en parallele) -> synthese.
    Renvoie le rapport final + les etapes intermediaires (utile pour l'UI).
    """
    steps = []
    start = time.time()

    # 1) planification
    t = time.time()
    sub_questions = plan(question) or [question]
    steps.append({
        "stage": "planning",
        "sub_questions": sub_questions,
        "seconds": round(time.time() - t, 1),
    })

    # 2) recherches en parallele (l'ordre des resultats suit celui des sous-questions)
    workers = max(1, min(MAX_PARALLEL, len(sub_questions)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        research_results = list(pool.map(_timed_research, sub_questions))

    for sq, result in zip(sub_questions, research_results):
        steps.append({
            "stage": "research",
            "sub_question": sq,
            "sources_count": len(result.get("sources", [])),
            "seconds": result["seconds"],
        })

    # 3) synthese
    t = time.time()
    report = synthesize(question, research_results)
    steps.append({"stage": "synthesis", "done": True, "seconds": round(time.time() - t, 1)})

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