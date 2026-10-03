import os
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()
_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


def web_search(query: str, max_results: int = 5) -> dict:
    """
    Recherche web generale via Tavily. Renvoie un resume court
    (titre + extrait + url) pour chaque resultat, pas le contenu complet.
    """
    try:
        result = _client.search(query, max_results=max_results)
    except Exception as e:
        return {"error": str(e)}

    return {
        "query": query,
        "results": [
            {
                "title": r["title"],
                "url": r["url"],
                "snippet": r["content"][:300],  # on coupe pour rester compact
            }
            for r in result.get("results", [])
        ],
    }