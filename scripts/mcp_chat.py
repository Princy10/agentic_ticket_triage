import asyncio
import os
import httpx

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

MCP_URL = os.getenv("MCP_URL", "http://localhost:8000/mcp/")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

server = MCPServerStreamableHTTP(MCP_URL)

http_client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5, read=120, write=30, pool=5))

model = OpenAIChatModel(
    model_name=OLLAMA_MODEL,
    provider=OllamaProvider(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
        http_client=http_client,
    ),
)

agent = Agent(
    model,
    toolsets=[server],
    instructions=(
        "Tu es un assistant de triage support.\n"
        "Utilise les tools MCP pour lire et appliquer le triage sur les tickets.\n"
        "Quand l'utilisateur demande d'appliquer le triage, tu DOIS appeler uniquement le tool triage_apply (pas update_ticket, pas triage_suggest).\n"
        "Quand l'utilisateur demande un détail ticket, appelle get_ticket.\n"
        "N'invente jamais category_name : utilise uniquement une category_name explicitement fournie par l'utilisateur ou déjà présente/valide côté ticket/système.\n"
        "Si aucune category_name valide n'est disponible, ne devine pas : demande une précision.\n"
        "Sois concis et cite le ticket_id."
    ),
)

async def main():
    print(f"[MCP] {MCP_URL}")
    print(f"[OLLAMA] {OLLAMA_BASE_URL} | model={OLLAMA_MODEL}")
    print("Tape 'exit' pour quitter.\n")

    async with server:
        while True:
            user = input("You> ").strip()
            if user.lower() in {"exit", "quit"}:
                break
            result = await agent.run(user)
            print(f"Bot> {result.output}\n")

    await http_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())