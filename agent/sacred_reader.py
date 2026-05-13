# ============================================================
# قارئ الدستور المقدس
# ============================================================

from pathlib import Path
from typing import Optional, List
import hashlib
import logging

logger = logging.getLogger(__name__)

class SacredReader:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._sacred_text = ""
        self._chunks = []
        self._hash = ""
        self._load()

    def _load(self):
        if not self.file_path.exists():
            return
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self._sacred_text = f.read()
            self._hash = hashlib.md5(self._sacred_text.encode()).hexdigest()
            self._chunk_text()
            logger.info(f"📖 تم تحميل الدستور: {len(self._sacred_text):,} حرفاً، {len(self._chunks)} مقطعاً")
        except Exception as e:
            logger.error(f"فشل تحميل الدستور: {e}")

    def _chunk_text(self, chunk_size: int = 500):
        if not self._sacred_text:
            return
        words = self._sacred_text.split()
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size])
            self._chunks.append(chunk)

    def get_chunk(self, index: int) -> str:
        if not self._chunks:
            return ""
        return self._chunks[index % len(self._chunks)]

    def find_article(self, keyword: str) -> Optional[str]:
        if not self._chunks:
            return None
        keyword_lower = keyword.lower()
        best_match = None
        best_score = 0
        for chunk in self._chunks:
            chunk_lower = chunk.lower()
            if keyword_lower in chunk_lower:
                score = len(chunk_lower)
                if score > best_score:
                    best_score = score
                    best_match = chunk[:500]
        return best_match if best_match else (self._chunks[0][:500] if self._chunks else None)

    @property
    def sacred_text(self) -> str:
        return self._sacred_text

    @property
    def num_chunks(self) -> int:
        return len(self._chunks)

    @property
    def hash(self) -> str:
        return self._hash

    def reload(self, new_text: str):
        self._sacred_text = new_text
        self._hash = hashlib.md5(new_text.encode()).hexdigest()
        self._chunks = []
        self._chunk_text()
