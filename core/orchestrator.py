import time
from concurrent.futures import ThreadPoolExecutor

from agents.critic import review
from agents.planner import plan
from agents.researcher import research
from agents.synthesizer import synthesize

MAX_PARALLEL = 3         # recherches lancees en meme temps
MAX_REVIEW_ROUNDS = 2    # nombre maximum de tours "critique -> recherches de suivi"
MAX_FOLLOW_UPS = 2       # questions de suivi par tour

_FAILED_PREFIXES = ("Erreur lors de la recherche", "Recherche incomplete")


def _failed(result: dict) -> bool:
    """Une recherche a echoue si son resume est vide ou est un message d'erreur."""
    summary = (result.get("summary") or "").strip()
    return not summary or summary.startswith(_FAILED_PREFIXES)


def _timed_research(sub_question: str) -> dict:
    """Lance la recherche d'une sous-question et mesure sa duree."""
    start = time.time()
    result = research(sub_question)
    result["seconds"] = round(time.time() - start, 1)
    return result


def _research_batch(questions: list[str], steps: list) -> list[dict]:
    """Lance les recherches en parallele (ordre conserve) et note chaque etape."""
    workers = max(1, min(MAX_PARALLEL, len(questions)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_timed_research, questions))

    for sq, result in zip(questions, results):
        steps.append({
            "stage": "research",
            "sub_question": sq,
            "sources_count": len(result.get("sources", [])),
            "seconds": result["seconds"],
            "failed": _failed(result),
        })
    return results


def run_research_pipeline(question: str) -> dict:
    """
    Pipeline: planification -> recherches (parallele) -> [critique -> recherches de suivi]* -> synthese.
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

    # 2) premieres recherches
    asked = list(sub_questions)
    results = _research_batch(sub_questions, steps)

    # 3) boucle de critique: l'agent juge si c'est suffisant, sinon il relance des recherches ciblees
    for round_no in range(1, MAX_REVIEW_ROUNDS + 1):
        t = time.time()
        usable = [r for r in results if not _failed(r)]
        follow_ups = review(question, usable, MAX_FOLLOW_UPS) if usable else []

        known = {q.strip().lower() for q in asked}
        follow_ups = [q for q in follow_ups if q.strip().lower() not in known][:MAX_FOLLOW_UPS]

        steps.append({
            "stage": "review",
            "round": round_no,
            "follow_up_questions": follow_ups,
            "seconds": round(time.time() - t, 1),
        })
        if not follow_ups:
            break

        asked.extend(follow_ups)
        results.extend(_research_batch(follow_ups, steps))

    # 4) synthese (on ecarte les recherches echouees, sauf si tout a echoue)
    final_results = [r for r in results if not _failed(r)] or results
    t = time.time()
    report = synthesize(question, final_results)
    steps.append({"stage": "synthesis", "done": True, "seconds": round(time.time() - t, 1)})

    all_sources = sorted({
        url for r in final_results for url in r.get("sources", [])
    })

    return {
        "question": question,
        "report": report,
        "sub_questions": asked,
        "sources": all_sources,
        "steps": steps,
        "duration_seconds": round(time.time() - start, 1),
    }