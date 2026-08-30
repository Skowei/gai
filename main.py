import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from watchfiles import awatch
from pathlib import Path

from app.api.routes import chat, cline
from app.core.config import settings
from app.memory.l2.client import UnifiedMemoryManager
from app.memory.l4.indexer import index_single_file, sync_obsidian_vault
from app.api.deps import redis_client
from app.services.cache_service import get_cache_stats

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize memory managers
memory_manager = UnifiedMemoryManager()


async def obsidian_folder_watcher():
    """Background watcher for Obsidian vault changes."""
    vault_path = Path("/app/obsidian_vault")
    logger.info(f"[Watcher] Starting L4 observer: {vault_path}")
    
    try:
        async for changes in awatch(vault_path, force_polling=True):
            for change_type, file_path_str in changes:
                if change_type in (1, 2):
                    file_path = Path(file_path_str)
                    if file_path.suffix.lower() in [".md", ".pdf"]:
                        await index_single_file(file_path)
    except asyncio.CancelledError:
        logger.info("[Watcher] Stopped.")
    except Exception as err:
        logger.error(f"[Watcher] Error: {err}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    logger.info("[System] Starting Enterprise AI Core L0-L4...")
    
    # 1. Setup Ollama models
    from app.services.llm_service import LLMFactory
    await LLMFactory.ensure_models_setup()
    
    # 2. Initialize databases
    await memory_manager.initialize()
    
    # 3. Initial vault scan
    await sync_obsidian_vault()
    
    # 4. Start background watcher
    watcher_task = asyncio.create_task(obsidian_folder_watcher())
    
    logger.info("[System] All layers operational.")
    yield
    
    logger.info("[System] Shutting down...")
    watcher_task.cancel()
    await memory_manager.close()


app = FastAPI(
    title="AI Cognitive Core Gateway",
    description="Enterprise L0-L4 AI Memory System",
    version="3.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(chat.router, prefix="/api")
app.include_router(cline.router)


@app.get("/health")
async def health_check():
    """System health check."""
    health = {"status": "ok", "services": {}}
    
    try:
        if memory_manager.pool:
            async with memory_manager.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health["services"]["postgres"] = "ok"
        else:
            health["services"]["postgres"] = "not_initialized"
    except Exception as e:
        health["services"]["postgres"] = f"error: {str(e)}"
        health["status"] = "degraded"
    
    try:
        await redis_client.ping()
        health["services"]["redis"] = "ok"
    except Exception as e:
        health["services"]["redis"] = f"error: {str(e)}"
        health["status"] = "degraded"
    
    try:
        # get_cache_stats() is synchronous (returns a plain dict) - no await
        health["services"]["cache"] = get_cache_stats()
    except Exception as e:
        health["services"]["cache"] = f"error: {str(e)}"
    
    return health


@app.websocket("/ws/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time streaming."""
    await websocket.accept()
    logger.info("[WebSocket] Connected")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"status": "processed", "message": "Indexed."})
    except WebSocketDisconnect:
        logger.info("[WebSocket] Disconnected")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
