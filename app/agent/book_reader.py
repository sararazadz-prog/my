from pathlib import Path
from typing import Optional, List, Tuple
import uuid
import os
import random
import logging
from app.config import CURRENT_BOOK_FILE, BOOKS_DIR

logger = logging.getLogger(__name__)


class BookReader:
    def __init__(self):
        self.books_dir = Path(BOOKS_DIR)
        self.current_book_text = ""
        self.current_book_name = ""
        self._chunks = []
        self._load_current_book()

    def _load_current_book(self):
        current_book_path = Path(CURRENT_BOOK_FILE)
        if not current_book_path.exists():
            return
        with open(current_book_path, 'r', encoding='utf-8') as f:
            self.current_book_name = f.read().strip()
        book_file = self.books_dir / self.current_book_name
        if not book_file.exists():
            return
        try:
            with open(book_file, 'r', encoding='utf-8', errors='ignore') as f:
                self.current_book_text = f.read()
            self._chunk_text()
            logger.info(f"تم تحميل الكتاب: {self.current_book_name} ({len(self.current_book_text):,} حرفاً)")
        except Exception as e:
            logger.error(f"فشل تحميل الكتاب: {e}")

    def _chunk_text(self, chunk_size: int = 500):
        if not self.current_book_text:
            return
        words = self.current_book_text.split()
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size])
            self._chunks.append(chunk)

    def get_random_chunk(self) -> Optional[str]:
        if not self._chunks:
            return None
        return random.choice(self._chunks)

    def search(self, keyword: str) -> Optional[str]:
        if not self._chunks:
            return None
        keyword_lower = keyword.lower()
        for chunk in self._chunks:
            if keyword_lower in chunk.lower():
                return chunk[:500]
        return None

    def load_book_from_pdf(self, filename: str, content: bytes) -> Tuple[bool, str]:
        try:
            from pypdf import PdfReader
            temp_pdf = self.books_dir / f"temp_{uuid.uuid4().hex[:8]}.pdf"
            with open(temp_pdf, 'wb') as f:
                f.write(content)
            reader = PdfReader(temp_pdf)
            text_parts = []
            for page_num, page in enumerate(reader.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"[الصفحة {page_num}]\n{page_text}")
                except:
                    pass
            os.unlink(temp_pdf)
            if not text_parts:
                return False, "لم يتم استخراج أي نص من PDF"
            text = "\n\n".join(text_parts)
            txt_filename = filename.replace('.pdf', '.txt')
            txt_path = self.books_dir / txt_filename
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(text)
            self.current_book_text = text
            self.current_book_name = txt_filename
            self._chunks = []
            self._chunk_text()
            with open(CURRENT_BOOK_FILE, 'w', encoding='utf-8') as f:
                f.write(txt_filename)
            return True, f"تم تحميل PDF وتحويله إلى {len(text):,} حرفاً"
        except ImportError:
            return False, "مكتبة pypdf غير متوفرة"
        except Exception as e:
            return False, str(e)

    def load_book_from_txt(self, filename: str, content: bytes) -> Tuple[bool, str]:
        try:
            txt_path = self.books_dir / filename
            with open(txt_path, 'wb') as f:
                f.write(content)
            text_content = content.decode('utf-8', errors='ignore')
            self.current_book_text = text_content
            self.current_book_name = filename
            self._chunks = []
            self._chunk_text()
            with open(CURRENT_BOOK_FILE, 'w', encoding='utf-8') as f:
                f.write(filename)
            return True, f"تم تحميل {len(text_content):,} حرفاً"
        except Exception as e:
            return False, str(e)

    def get_current_book(self) -> str:
        return self.current_book_name if self.current_book_name else "لا يوجد كتاب مفتوح"

    def get_preview(self, length: int = 500) -> str:
        if not self.current_book_text:
            return ""
        return self.current_book_text[:length]

    @property
    def has_book(self) -> bool:
        return bool(self.current_book_text) and len(self.current_book_text) > 0

    @property
    def chunks(self) -> List[str]:
        return self._chunks.copy()
