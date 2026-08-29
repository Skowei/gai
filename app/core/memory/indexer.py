import asyncio
import os
from pathlib import Path
import json
from pypdf import PdfReader
from app.core.memory.postgres import UnifiedMemoryManager
from app.core.llm_factory import LLMFactory

def _chunk_text(text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> list[str]:
    """Tnie tekst na małe fragmenty z nakładaniem się, chroniąc przed zatykaniem VRAM bota."""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - chunk_overlap
    return chunks

def _extract_text_from_pdf(pdf_path: Path) -> str:
    """Wyciąga surowy tekst z pliku PDF."""
    try:
        reader = PdfReader(pdf_path)
        text_parts = []
        for page_num, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"[Page {page_num + 1}] {page_text}")
        return "\n".join(text_parts)
    except Exception as e:
        print(f"❌ [PDF Parser] Error reading {pdf_path.name}: {e}")
        return ""

async def sync_obsidian_vault():
    """[L4 GLOBAL SCANNER] Processes files incrementally using chunking for ultra-fast RAG."""
    print("\n🔍 [L4 Scanner] Starting full scan with chunked optimization (.md + .pdf)...")
    
    vault_path = Path("/app/obsidian_vault")
    memory_manager = UnifiedMemoryManager()
    await memory_manager.initialize()
    
    embed_engine = LLMFactory.get_embedding_engine()
    loop = asyncio.get_running_loop()
    
    if not vault_path.exists():
        print(f"❌ [L4 Scanner] Path {vault_path} does not exist!")
        await memory_manager.close()
        return

    # Czyszczenie starej bazy, aby usunąć gigantyczne, niezoptymalizowane bloki tekstu
    try:
        async with memory_manager.pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE agent_memory;")
            print("🧹 [L4 Scanner] Cleared old oversized records from vector storage.")
    except Exception as d_err:
        print(f"⚠️ [L4 Scanner] Table clear info: {d_err}")

    total_chunks_indexed = 0
    
    for file_path in vault_path.rglob("*"):
        if file_path.suffix.lower() not in [".md", ".pdf"]:
            continue
        if any(part.startswith('.') for part in file_path.parts):
            continue
            
        try:
            rel_path = file_path.relative_to(vault_path)
            
            if file_path.suffix.lower() == ".pdf":
                raw_content = _extract_text_from_pdf(file_path)
            else:
                raw_content = file_path.read_text(encoding="utf-8")
                
            if not raw_content.strip():
                continue

            # 🚨 KLUCZOWA POPRAWKA: Tniemy plik na małe, lekkie dla GPU kawałki!
            text_chunks = _chunk_text(raw_content)
            
            for index, chunk in enumerate(text_chunks):
                # Generujemy embedding wyłącznie dla małego fragmentu
                embedding = await loop.run_in_executor(
                    None, 
                    embed_engine.embed_query, 
                    f"File: {rel_path.name}. Context: {chunk[:400]}"
                )
                embedding_str = str(embedding)
                
                metadata = {
                    "source": "Obsidian-L4-Chunked-Scanner",
                    "memory_level": "L4",
                    "file_name": file_path.name,
                    "relative_path": str(rel_path),
                    "chunk_index": index,
                    "file_type": file_path.suffix.lower().replace(".", "")
                }
                
                # Unikalny klucz dla każdego fragmentu zapobiega dublowaniu
                unique_file_id = f"obsidian_vault/{rel_path}#chunk_{index}"
                
                async with memory_manager.pool.acquire() as conn:
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
                        unique_file_id, chunk, embedding_str, json.dumps(metadata)
                    )
                total_chunks_indexed += 1
        except Exception as e:
            print(f"❌ [L4 Scanner Error] Failed to index {file_path.name}: {e}")
            
    print(f"✅ [L4 Scanner] Success! Total optimized chunks indexed: {total_chunks_indexed}\n")
    await memory_manager.close()


async def index_single_file(file_path: Path):
    """[L4 LIVE WATCHER] Processes a single modified file instantly using chunking logic."""
    if file_path.suffix.lower() not in [".md", ".pdf"]:
        return
        
    vault_path = Path("/app/obsidian_vault")
    if any(part.startswith('.') for part in file_path.parts):
        return

    try:
        rel_path = file_path.relative_to(vault_path)
        print(f"\n⚡ [Auto-Watcher L4] Modified file detected: {rel_path}. Re-chunking parameters...")
        
        if file_path.suffix.lower() == ".pdf":
            raw_content = _extract_text_from_pdf(file_path)
        else:
            raw_content = file_path.read_text(encoding="utf-8")
            
        if not raw_content.strip():
            return

        text_chunks = _chunk_text(raw_content)
        
        memory_manager = UnifiedMemoryManager()
        await memory_manager.initialize()
        embed_engine = LLMFactory.get_embedding_engine()
        loop = asyncio.get_running_loop()
        
        for index, chunk in enumerate(text_chunks):
            embedding = await loop.run_in_executor(
                None, 
                embed_engine.embed_query, 
                f"File: {file_path.name}. Context: {chunk[:400]}"
            )
            embedding_str = str(embedding)
            
            metadata = {
                "source": "Obsidian-L4-Live-Watcher",
                "memory_level": "L4",
                "file_name": file_path.name,
                "relative_path": str(rel_path),
                "chunk_index": index,
                "file_type": file_path.suffix.lower().replace(".", "")
            }
            
            unique_file_id = f"obsidian_vault/{rel_path}#chunk_{index}"
            
            async with memory_manager.pool.acquire() as conn:
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
                    unique_file_id, chunk, embedding_str, json.dumps(metadata)
                )
        print(f"✅ [Auto-Watcher L4] Optimized vector chunks updated successfully.\n")
        await memory_manager.close()
    except Exception as e:
        print(f"❌ [Auto-Watcher L4 Error] Failed to update {file_path.name}: {e}")
