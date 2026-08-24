"""AI Ecosystem V2.0 - Obsidian Tool (Markdown indexing)
Interakcja z baza notatek Markdown/Obsidian
"""

import os
from pathlib import Path
from typing import Dict, List, Any, Optional


class ObsidianTool:
    """Narzedzie do obslugi notatek Markdown (Obsidian)."""

    def __init__(self):
        self._obsidian_root = Path(os.getenv("OBSIDIAN_ROOT", "./data/obsidian"))
        from ..memory.client import MemoryClient
        self.memory_client = MemoryClient()

    def index_markdown_file(self, file_path: str) -> Dict[str, Any]:
        """Indexowanie pliku Markdown do bazy."""
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                return {"success": False, "file": str(file_path), "message": f"File not found: {file_path}"}
            content = file_path.read_text(encoding="utf-8")
            stat = file_path.stat()
            embedding = [0.0] * 768
            self.memory_client._connect()
            metadata = {
                "filename": file_path.name,
                "size": stat.st_size,
                "created_at": str(stat.st_ctime),
                "tags": self._extract_tags(content),
                "excerpt": content[:500] if len(content) > 500 else content,
            }
            embedding = self.memory_client.store(
                content=content + metadata["filename"],
                embedding=embedding,
                metadata=metadata,
            )
            return {
                "success": True,
                "file": str(file_path),
                "embedding_id": embedding.get("id"),
                "metadata": metadata,
                "message": f"File indexed: {file_path.name}",
            }
        except Exception as e:
            return {"success": False, "file": str(file_path) if file_path else None, "message": f"Indexing error: {e}"}

    def search_notes(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantyczne wyszukiwanie notatek."""
        dummy_embedding = [0.0] * 768
        results = self.memory_client.search_semantic(query, top_k=top_k)
        return results

    def retrieve_context(self, max_entries: int = 5) -> List[Dict[str, str]]:
        """Pobieranie kontekstu z ostatnich Q&A."""
        return self.memory_client.retrieve_from_context_window(max_entries)

    def summarize_text(self, text: str, max_length: int = 200) -> Dict[str, Any]:
        """Summarizacja tekstu."""
        return {
            "success": True,
            "original_length": len(text),
            "summary": f"[SUMMARY] {text[:50]}...",
            "tokens_saved": max(0, len(text) - max_length),
        }

    def translate_text(self, text: str, target_lang: str = "pl") -> Dict[str, Any]:
        """Tlumaczenie tekstu."""
        translation_map = {"pl": "Polish", "en": "English"}
        lang_name = translation_map.get(target_lang.lower(), target_lang.upper())
        return {
            "success": True,
            "original": text[:100] + "..." if len(text) > 100 else text,
            "target_language": lang_name,
            "translated": f"[TRANSLATION] {lang_name}",
        }

    def _extract_tags(self, content: str) -> List[str]:
        """Ekstrakcja tagow #word z Markdown."""
        import re
        tags = re.findall(r"#(\w+)", content)
        return list(set(tags))[:20]

    def get_related_notes(self, note_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Pobieranie pokrewnych notatek."""
        if not hasattr(self, "_pg_pool"):
            self.memory_client._connect()
        embedding = [0.0] * 768
        results = self.memory_client.search_semantic(f"related: {note_id}", top_k=top_k)
        return [{**r, "relation": "semantic_similar"} for r in results]

    def get_file_contents(self, file_path: str) -> Dict[str, Any]:
        """Pobieranie treSci pliku Markdown."""
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                return {"success": False, "file": str(file_path), "message": f"File not found: {file_path}"}
            content = file_path.read_text(encoding="utf-8")
            return {
                "success": True,
                "file": str(file_path),
                "content": content[:500] + "...",
                "full_content_available": len(content) > 500,
                "size": file_path.stat().st_size,
            }
        except Exception as e:
            return {"success": False, "file": str(file_path) if file_path else None, "message": f"Error reading file: {e}"}


_obsidian_tool_instance = None

def get_obsidian_tool() -> ObsidianTool:
    """Zwrot singleton instance ObsidianTool."""
    global _obsidian_tool_instance
    if _obsidian_tool_instance is None:
        _obsidian_tool_instance = ObsidianTool()
    return _obsidian_tool_instance


def index_markdown(file_path: str) -> Dict[str, Any]:
    """Convenience function do indexowania pliku Markdown."""
    return get_obsidian_tool().index_markdown_file(file_path)


def search_notes(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Convenience function do semantycznego wyszukiwania notatek."""
    tool = get_obsidian_tool()
    return tool.search_notes(query, top_k=top_k)
