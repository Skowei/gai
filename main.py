import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from watchfiles import awatch  # Oficjalny asynchroniczny silnik obserwatora plików
from pathlib import Path

from app.api.routes import chat, cline
from app.core.config import settings
from app.core.memory.postgres import UnifiedMemoryManager
from app.core.memory.indexer import index_single_file, sync_obsidian_vault

# Inicjalizujemy globalny menedżer pamięci relacyjno-wektorowej Enterprise
memory_manager = UnifiedMemoryManager()


async def obsidian_folder_watcher():
    """Asynchroniczny proces w tle monitorujący i indeksujący w locie zmiany w Obsidian Vault (L4)."""
    vault_path = Path("/app/obsidian_vault")
    print(f"👁️ [System] Uruchamiam automatycznego szpiega L4 dla ścieżki: {vault_path}")
    
    try:
        async for changes in awatch(vault_path, force_polling=True):
            for change_type, file_path_str in changes:
                if change_type in (1, 2):
                    file_path = Path(file_path_str)
                    # POPRAWKA: Przepuszczamy zarówno pliki .md jak i .pdf!
                    if file_path.suffix.lower() in [".md", ".pdf"]:
                        await index_single_file(file_path)
    except asyncio.CancelledError:
        print("[System] Zamykam automatycznego szpiega L4.")
    except Exception as err:
        print(f"⚠️ [System Watcher Błąd] Awaria obserwatora: {err}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Obsługuje pełny cykl życia aplikacji w standardzie FastAPI.
    Inicjalizuje modele, bazy danych oraz uruchamia automatycznych szpiegów L4 w tle.
    """
    print("\n🚀 [System] Uruchamiam asynchroniczny silnik kognitywny Enterprise L0-L4...")
    
    # 1. Automatyczna synchronizacja modeli Ollama
    from app.core.llm_factory import LLMFactory
    await LLMFactory.ensure_models_setup()
    
    # 2. Inicjalizacja baz danych i schematów L1-L3 (Redis + Postgres + HNSW)
    await memory_manager.initialize()
    
    # 3. Jednorazowy skan startowy na wypadek dodania notatek przy wyłączonym bocie
    await sync_obsidian_vault()
    
    # 4. Odpalamy automatycznego szpiega w tle jako asynchroniczne zadanie
    watcher_task = asyncio.create_task(obsidian_folder_watcher())
    
    print("✅ [System] Wszystkie warstwy pamięci i automatyczne skanery działają.\n")
    
    yield
    
    print("[System] Zamykam asynchroniczne pule połączeń bazodanowych...")
    watcher_task.cancel()
    await memory_manager.close()


# Inicjalizacja instancji FastAPI z podpiętym lifespanem
app = FastAPI(
    title="AI Cognitive Core Gateway",
    description="Zunifikowany, asynchroniczny silnik operacyjny systemu AI Enterprise L0-L4",
    version="3.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Podłączamy ustrukturyzowany routing (Zarówno czat jak i mostek dla VS Code)
app.include_router(chat.router, prefix="/api")
app.include_router(cline.router)


# Niskolatencyjny kanał dla hardware'u i strumieni wideo (Zostaje w 100% nienaruszony!)
@app.websocket("/ws/v1/stream")
async def websocket_stream_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[WebSocket] Zewnętrzny kanał danych/hardware podłączony.")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"status": "processed", "message": "Zdarzenie zindeksowane."})
    except WebSocketDisconnect:
        print("[WebSocket] Kanał danych rozłączony.")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
