"""
L2: Memory Repository - CRUD operations
"""
import asyncio
import json
import logging
from typing import Dict, Any
import aiofiles
from app.services.llm_service import LLMFactory
from app.memory.l2.client import format_embedding_for_pgvector

logger = logging.getLogger(__name__)


class MemoryRepository:
    """
    L2: CRUD operations for memory storage.
    Handles saving documents to vault, local notes, and history.
    """
    
    def __init__(self, memory_manager):
        self.memory_manager = memory_manager
    
    async def save_to_vault_and_vector(self, vault_path: str, local_notes_path: str, 
                                       rel_path: str, content: str, metadata: Dict[str, Any]):
        """Save to Obsidian vault (L4) and index in vector DB (L2)."""
        if not self.memory_manager.pool:
            await self.memory_manager.initialize()

        # Save to filesystem
        full_path = vault_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(full_path, mode='w', encoding='utf-8') as f:
            await f.write(content)

        # Generate embedding
        embed_engine = LLMFactory.get_embedding_engine()
        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(None, embed_engine.embed_query, content)
        embedding_str = format_embedding_for_pgvector(embedding)

        # Save to database
        metadata["memory_level"] = "L4"
        async with self.memory_manager.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_memory (file_path, content, embedding, metadata, updated_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (file_path) 
                DO UPDATE SET 
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW();
                """,
                f"obsidian_vault/{rel_path}", content, embedding_str, json.dumps(metadata)
            )
        logger.info(f"[L4+L2] Indexed vault document: {rel_path}")

    async def save_to_local_notes_and_vector(self, rel_path: str, content: str, 
                                             metadata: Dict[str, Any]):
        """Save to local notes (L3) and index in vector DB (L2)."""
        if not self.memory_manager.pool:
            await self.memory_manager.initialize()

        # Save to filesystem
        full_path = self.memory_manager.local_notes_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        frontmatter = f"---\nengine: DeepSeek-R1-8B\nsession_id: {metadata.get('session_id', 'unknown')}\n---\n"
        file_content = f"{frontmatter}\n# Log operacyjny Agenta\n\n{content}"
        async with aiofiles.open(full_path, mode='w', encoding='utf-8') as f:
            await f.write(file_content)

        # Generate embedding
        embed_engine = LLMFactory.get_embedding_engine()
        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(None, embed_engine.embed_query, content)
        embedding_str = format_embedding_for_pgvector(embedding)

        # Save to database
        metadata["memory_level"] = "L3"
        async with self.memory_manager.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_memory (file_path, content, embedding, metadata, updated_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (file_path) 
                DO UPDATE SET 
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW();
                """,
                f"internal_cache/{rel_path}", content, embedding_str, json.dumps(metadata)
            )
        logger.info(f"[L3+L2] Indexed local note: {rel_path}")

    async def log_chat_interaction(self, session_id: str, question: str, answer: str):
        """Log conversation to rag_history."""
        if not self.memory_manager.pool:
            await self.memory_manager.initialize()
        async with self.memory_manager.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO rag_history (session_id, question, answer) VALUES ($1, $2, $3);",
                session_id, question, answer
            )
