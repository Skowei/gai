import asyncio
import os
import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiofiles
from app.core.config import settings
from app.core.memory.postgres import UnifiedMemoryManager

log = logging.getLogger("obsidian-tool")

class AsyncObsidianTool:
    """
    Asynchroniczne narzędzie do integracji z Obsidian Vault (Warstwa L3).
    Umożliwia pełne skanowanie, asynchroniczny odczyt plików oraz
    synchronizację wektorową z bazą PostgreSQL (Warstwa L2).
    """
    def __init__(self, memory_manager: UnifiedMemoryManager):
        self.memory_manager = memory_manager
        # Domyślna ścieżka montowania wewnątrz kontenera Docker
        self.vault_root = Path("/app/obsidian_vault")

    @staticmethod
    def _extract_tags(content: str) -> List[str]:
        """Wyciąga hashtagi z treści notatki, eliminując duplikaty."""
        return list(dict.fromkeys(re.findall(r"#(\w+)", content)))[:20]

    async def index_single_file(self, relative_path: str) -> Dict[str, Any]:
        """
        Asynchronicznie odczytuje pełny plik Markdown, ekstrahuje metadane
        i zapisuje jego reprezentację wektorową w PostgreSQL.
        """
        full_path = self.vault_root / relative_path
        if not full_path.exists():
            return {"success": False, "message": f"Nie znaleziono pliku: {relative_path}"}

        try:
            # Asynchroniczny odczyt CAŁEGO pliku zamiast blokującego fragmentu 500 znaków
            async with aiofiles.open(full_path, mode='r', encoding='utf-8') as f:
                content = await f.read()

            stat = full_path.stat()
            metadata = {
                "filename": full_path.name,
                "size_bytes": stat.st_size,
                "tags": self._extract_tags(content),
                "vault_relative_path": str(relative_path)
            }

            # Wyciągamy sam tytuł z nazwy pliku
            title = full_path.stem.replace("_", " ").title()

            # Zapisujemy bezpośrednio przez nasz zintegrowany menedżer pamięci (L2 + L3 sync)
            await self.memory_manager.save_to_vault_and_vector(
                rel_path=str(relative_path),
                content=content,
                metadata=metadata
            )

            return {
                "success": True,
                "file": str(relative_path),
                "message": f"Pomyślnie zindeksowano notatkę: {full_path.name}"
            }
        except Exception as exc:
            log.error(f"Błąd indeksowania pliku {relative_path}: {exc}")
            return {"success": False, "message": f"Błąd: {exc}"}

    async def index_entire_vault(self) -> Dict[str, Any]:
        """
        Skanuje asynchronicznie cały folder Obsidiana i indeksuje wszystkie pliki .md.
        Dzięki asynchroniczności proces ten nie blokuje zapytań z chatu Vue ani Cline.
        """
        if not self.vault_root.exists():
            return {"success": False, "message": f"Folder Vault nie istnieje pod ścieżką: {self.vault_root}"}

        indexed_count = 0
        error_count = 0
        
        # rglob zwraca generator plików, przetwarzamy go bez blokowania wątków
        for md_file in sorted(self.vault_root.rglob("*.md")):
            # Obliczamy ścieżkę względną wobec roota naszego repozytorium notatek
            rel_path = md_file.relative_to(self.vault_root)
            result = await self.index_single_file(str(rel_path))
            if result["success"]:
                indexed_count += 1
            else:
                error_count += 1
                
            # Pozwalamy innym asynchronicznym zadaniom (np. WebSocketom) na wykonanie się w trakcie ciężkiego skanowania
            await asyncio.sleep(0.001)

        return {
            "success": True,
            "total_files_found": indexed_count + error_count,
            "successfully_indexed": indexed_count,
            "errors": error_count
        }

    async def read_full_note_content(self, relative_path: str) -> Dict[str, Any]:
        """Zwraca pełną, nieobciętą treść notatki z dysku za pomocą operacji asynchronicznych."""
        full_path = self.vault_root / relative_path
        if not full_path.exists():
            return {"success": False, "message": "Plik nie istnieje"}

        try:
            async with aiofiles.open(full_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
            return {
                "success": True,
                "file": str(relative_path),
                "content": content,
                "size": full_path.stat().st_size
            }
        except Exception as exc:
            return {"success": False, "message": f"Błąd odczytu: {exc}"}

# =============================================================================
# ASYNC SINGLETON
# =============================================================================
_async_obsidian_tool_instance: Optional[AsyncObsidianTool] = None

def get_async_obsidian_tool(memory_manager: UnifiedMemoryManager) -> AsyncObsidianTool:
    global _async_obsidian_tool_instance
    if _async_obsidian_tool_instance is None:
        _async_obsidian_tool_instance = AsyncObsidianTool(memory_manager)
    return _async_obsidian_tool_instance
