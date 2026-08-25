"""
==============================================================================
AI Ecosystem V2.0 - Obsidian Tool (Markdown indexing)
Interakcja z bazą notatek Markdown/Obsidian (wsparcie dla wielu folderów)
==============================================================================
"""

import os
import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

log = logging.getLogger("obsidian")


class ObsidianTool:
    """Narzędzie do obsługi notatek Markdown (Obsidian) z obsługą wielu katalogów."""

    def __init__(self, vault_paths: Optional[Union[str, List[str]]] = None):
        # Pobieramy ścieżki z argumentu, zmiennej środowiskowej (rozdzielone przecinkami) lub domyślnej
        if vault_paths:
            raw_paths = vault_paths if isinstance(vault_paths, list) else [vault_paths]
        else:
            env_val = os.getenv("OBSIDIAN_ROOT", "./data/obsidian_vault")
            # Obsługa wielu ścieżek rozdzielonych przecinkiem w env, np. OBSIDIAN_ROOT="/app/vault1,/app/vault2"
            raw_paths = [p.strip() for p in env_val.split(",") if p.strip()]

        self._vault_roots = [Path(p) for p in raw_paths]
        self._memory = None  # lazy import, unikamy pętli importów

    # ------------------------------------------------------------ pomocnicze
    def _get_memory(self):
        if self._memory is None:
            from ..memory.client import get_memory_client
            self._memory = get_memory_client()
        return self._memory

    @staticmethod
    def _extract_tags(content: str) -> List[str]:
        return list(dict.fromkeys(re.findall(r"#(\w+)", content)))[:20]

    # ---------------------------------------------------------------- indeks
    def index_markdown_file(self, file_path: str) -> Dict[str, Any]:
        """Indeksowanie pliku Markdown do pamięci (L1 pgvector + L0 redis)."""
        try:
            path = Path(file_path)
            if not path.exists():
                return {"success": False, "file": str(path),
                        "message": f"File not found: {path}"}

            content = path.read_text(encoding="utf-8")
            stat = path.stat()
            metadata = {
                "filename": path.name,
                "path": str(path),
                "size": stat.st_size,
                "created_at": str(stat.st_ctime),
                "tags": self._extract_tags(content),
                "excerpt": content[:500],
            }
            ok = self._get_memory().store(
                key=f"note:{path.name}:{stat.st_mtime_ns}",
                content=content,
                metadata=metadata,
            )
            if ok:
                return {"success": True, "file": str(path),
                        "metadata": metadata,
                        "message": f"File indexed: {path.name}"}
            return {"success": False, "file": str(path),
                    "message": "Błąd zapisu pamięci (embeddings niedostępne?)"}
        except Exception as exc:
            return {"success": False, "file": str(file_path),
                    "message": f"Indexing error: {exc}"}

    def index_directory(self, directory: Optional[Union[str, List[str]]] = None) -> Dict[str, Any]:
        """Indeksowanie wszystkich plików .md ze wszystkich skonfigurowanych katalogów vault."""
        if directory:
            roots = directory if isinstance(directory, list) else [directory]
            target_roots = [Path(r) for r in roots]
        else:
            target_roots = self._vault_roots

        total_indexed, total_errors = 0, 0
        results_summary = []

        for root in target_roots:
            if not root.exists():
                log.warning(f"Vault not found: {root}")
                continue
            
            indexed, errors = 0, 0
            for md in sorted(root.rglob("*.md")):
                r = self.index_markdown_file(str(md))
                if r["success"]:
                    indexed += 1
                else:
                    errors += 1
            
            total_indexed += indexed
            total_errors += errors
            results_summary.append({"vault": str(root), "indexed": indexed, "errors": errors})

        return {
            "success": True, 
            "total_indexed": total_indexed,
            "total_errors": total_errors, 
            "vaults": results_summary
        }

    # ------------------------------------------------------------- wyszukiwanie
    def search_notes(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantyczne wyszukiwanie notatek (L1 pgvector)."""
        return self._get_memory().search_semantic(query, top_k=top_k)

    def get_related_notes(self, note_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Pokrewne notatki — semantyczna odległość względem identyfikatora."""
        results = self._get_memory().search_semantic(f"related: {note_id}", top_k=top_k)
        return [{**r, "relation": "semantic_similar"} for r in results]

    def get_file_contents(self, file_path: str) -> Dict[str, Any]:
        """Treść pliku Markdown (ograniczona do 500 znaków)."""
        try:
            path = Path(file_path)
            if not path.exists():
                return {"success": False, "file": str(path),
                        "message": "File not found"}
            content = path.read_text(encoding="utf-8")
            return {
                "success": True,
                "file": str(path),
                "content": content[:500] + ("..." if len(content) > 500 else ""),
                "size": path.stat().st_size,
            }
        except Exception as exc:
            return {"success": False, "file": str(file_path),
                    "message": f"Error reading file: {exc}"}

    def retrieve_context(self, max_entries: int = 5) -> List[Dict[str, str]]:
        """Ostatnie Q&A z pamięci kontekstu (L3)."""
        return self._get_memory().retrieve_from_context_window(max_entries=max_entries)


# =============================================================================
# SINGLETON + convenience
# =============================================================================

_obsidian_tool_instance: Optional[ObsidianTool] = None


def get_obsidian_tool() -> ObsidianTool:
    global _obsidian_tool_instance
    if _obsidian_tool_instance is None:
        _obsidian_tool_instance = ObsidianTool()
    return _obsidian_tool_instance


def index_markdown(file_path: str) -> Dict[str, Any]:
    """Convenience: indeksowanie jednego pliku."""
    return get_obsidian_tool().index_markdown_file(file_path)


def search_notes(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Convenience: semantyczne wyszukiwanie notatek."""
    return get_obsidian_tool().search_notes(query, top_k=top_k)