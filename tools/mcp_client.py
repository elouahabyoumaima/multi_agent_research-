import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# parametres pour lancer mcp-server-fetch comme sous-processus.
# sys.executable = le Python de l'environnement courant (venv local, ou venv de Streamlit Cloud):
# "python" tout court pouvait pointer vers un autre Python, sans le module mcp_server_fetch.
_server_params = StdioServerParameters(
    command=sys.executable,
    args=["-m", "mcp_server_fetch"],
)


async def _fetch_async(url: str) -> dict:
    """Se connecte au serveur MCP fetch, appelle son outil 'fetch', puis ferme la connexion."""
    async with stdio_client(_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("fetch", {"url": url})

            # le contenu renvoye est une liste de blocs (texte, image, etc.)
            text_parts = [block.text for block in result.content if hasattr(block, "text")]
            return {"url": url, "content": "\n".join(text_parts)[:3000]}  # on limite la taille


def fetch_url(url: str) -> dict:
    """Version synchrone utilisable facilement dans le reste du code (FastAPI, agents...)."""
    try:
        return asyncio.run(_fetch_async(url))
    except Exception as e:
        return {"error": str(e)}