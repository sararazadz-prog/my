# ============================================================
# الحارس الصامت – Silent Guardian
# النسخة النخبوية النهائية المستقرة v2.0
# ============================================================
# المبادئ الدستورية:
# 1. الدستور (القرآن) هو المصدر الوحيد للحقيقة المطلقة
# 2. الكتب مصادر تعلم متغيرة، توزن ولا تساوي الدستور أبداً
# 3. الوكيل يتطور لكن لا يلمس الكود الأساسي
# 4. الذاكرة لا تموت – نسخ احتياطي تلقائي إلى GitHub
# 5. البوابة الدستورية تفحص كل قرار قبل التنفيذ
# ============================================================

import os
import sys
import json
import time
import random
import logging
import threading
import tempfile
import subprocess
import uuid
import base64
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from contextlib import contextmanager

import requests
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sqlite3
from github import Github

# ============================================================
# إعداد التسجيل الاحترافي
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# متغيرات البيئة (كلها محمية)
# ============================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "sararazadz-prog/my")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
PERSISTENT_DIR = os.environ.get("PERSISTENT_DIR", "/data")

# إنشاء المجلدات الدائمة
os.makedirs(PERSISTENT_DIR, exist_ok=True)

# مسارات الملفات
CONSTITUTION_FILE = f"{PERSISTENT_DIR}/constitution.txt"
DB_PATH = f"{PERSISTENT_DIR}/constitution.db"
FLAG_FILE = f"{PERSISTENT_DIR}/constitution_uploaded.flag"
DESIGN_FILE = f"{PERSISTENT_DIR}/design.json"
MOODS_FILE = f"{PERSISTENT_DIR}/moods.json"
BOOKS_DIR = f"{PERSISTENT_DIR}/books"
CURRENT_BOOK_FILE = f"{PERSISTENT_DIR}/current_book.txt"
MATURITY_FILE = f"{PERSISTENT_DIR}/maturity.json"

os.makedirs(BOOKS_DIR, exist_ok=True)

# مصادر الدستور
QURAN_URL = "https://cdn.jsdelivr.net/npm/quran-json@3.1.2/dist/quran.json"

# حدود الأمان
MAX_BOOK_SIZE = 10 * 1024 * 1024
MAX_CODE_EXECUTION_TIME = 5
MAX_EVOLUTIONS_PER_DAY = 3

# ============================================================
# دوال GitHub المتقدمة
# ============================================================

def get_file_hash(file_path: str) -> str:
    """حساب هاش الملف للتحقق"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def is_binary_file(file_path: str) -> bool:
    """تحديد نوع الملف"""
    binary_extensions = ['.db', '.sqlite', '.sqlite3', '.pdf', '.zip', '.png', '.jpg', '.jpeg']
    if any(file_path.endswith(ext) for ext in binary_extensions):
        return True
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
        return b'\x00' in chunk
    except:
        return True


def sync_to_github(local_path: str, repo_path: str, commit_message: str = None) -> bool:
    """رفع ملف إلى GitHub مع دعم الملفات الثنائية"""
    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN غير موجود")
        return False

    if not os.path.exists(local_path):
        logger.warning(f"الملف {local_path} غير موجود")
        return False

    if commit_message is None:
        commit_message = f"Backup: {datetime.now().isoformat()}"

    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)

        with open(local_path, 'rb') as f:
            raw_bytes = f.read()

        if is_binary_file(local_path):
            content = base64.b64encode(raw_bytes).decode('utf-8')
        else:
            content = raw_bytes.decode('utf-8', errors='replace')

        try:
            contents = repo.get_contents(repo_path, ref=GITHUB_BRANCH)
            repo.update_file(contents.path, commit_message, content, contents.sha, branch=GITHUB_BRANCH)
            logger.info(f"تم تحديث {repo_path}")
        except:
            repo.create_file(repo_path, commit_message, content, branch=GITHUB_BRANCH)
            logger.info(f"تم إنشاء {repo_path}")

        return True
    except Exception as e:
        logger.error(f"فشل رفع {repo_path}: {e}")
        return False


def sync_from_github(local_path: str, repo_path: str) -> bool:
    """تحميل ملف من GitHub"""
    if not GITHUB_TOKEN:
        return False

    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        contents = repo.get_contents(repo_path, ref=GITHUB_BRANCH)
        content_bytes = base64.b64decode(contents.content)

        with open(local_path, 'wb') as f:
            f.write(content_bytes)

        logger.info(f"تم استعادة {repo_path}")
        return True
    except Exception as e:
        logger.info(f"{repo_path} غير موجود في GitHub")
        return False


def backup_agent_state(event: str = "manual"):
    """نسخ احتياطي كامل"""
    logger.info(f"بدء النسخ الاحتياطي (الحدث: {event})")

    files_to_backup = [
        (DB_PATH, "data/constitution.db"),
        (MOODS_FILE, "data/moods.json"),
        (DESIGN_FILE, "data/design.json"),
        (CURRENT_BOOK_FILE, "data/current_book.txt"),
    ]

    success_count = 0
    for local_path, repo_path in files_to_backup:
        if os.path.exists(local_path):
            if sync_to_github(local_path, repo_path, f"Backup: {event}"):
                success_count += 1

    if os.path.exists(BOOKS_DIR):
        for book_file in os.listdir(BOOKS_DIR):
            book_path = os.path.join(BOOKS_DIR, book_file)
            if os.path.isfile(book_path):
                sync_to_github(book_path, f"data/books/{book_file}", f"Backup book: {book_file}")

    logger.info(f"تم رفع {success_count} ملفات")


def restore_agent_state():
    """استعادة الحالة من GitHub"""
    logger.info("محاولة استعادة الذاكرة من GitHub...")

    files_to_restore = [
        (DB_PATH, "data/constitution.db"),
        (MOODS_FILE, "data/moods.json"),
        (DESIGN_FILE, "data/design.json"),
        (CURRENT_BOOK_FILE, "data/current_book.txt"),
    ]

    for local_path, repo_path in files_to_restore:
        sync_from_github(local_path, repo_path)


# ============================================================
# إدارة قاعدة البيانات
# ============================================================

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = None
        self._connect()

    def _connect(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()
        logger.info(f"قاعدة البيانات متصلة: {self.db_path}")

    def _init_tables(self):
        cursor = self._conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iteration INTEGER,
                timestamp TEXT,
                action TEXT,
                focus TEXT,
                context_preview TEXT,
                reflection TEXT,
                self_score REAL,
                gate_passed BOOLEAN,
                gate_reason TEXT,
                book_used TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evolutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                reason TEXT,
                old_brain_hash TEXT,
                new_brain_hash TEXT,
                success BOOLEAN
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS constitutional_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept TEXT,
                context TEXT,
                insights TEXT,
                related_concepts TEXT,
                importance_score REAL DEFAULT 0.5,
                created_at TEXT,
                last_accessed TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                user_message TEXT,
                agent_response TEXT,
                user_feedback BOOLEAN,
                timestamp TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                filepath TEXT,
                uploaded_at TEXT,
                is_current BOOLEAN
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS constitution_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                text TEXT,
                hash TEXT,
                updated_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id INTEGER,
                feedback BOOLEAN,
                timestamp TEXT
            )
        """)

        self._conn.commit()

    @contextmanager
    def cursor(self):
        cursor = self._conn.cursor()
        try:
            yield cursor
            self._conn.commit()
        except Exception as e:
            self._conn.rollback()
            raise e
        finally:
            cursor.close()

    def execute(self, query: str, params: tuple = ()):
        with self.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount

    def fetch_all(self, query: str, params: tuple = ()):
        with self.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def fetch_one(self, query: str, params: tuple = ()):
        with self.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def close(self):
        if self._conn:
            self._conn.close()


# ============================================================
# قارئ الدستور
# ============================================================

class SacredReader:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._sacred_text = ""
        self._chunks = []
        self._load()

    def _load(self):
        if not self.file_path.exists():
            return

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self._sacred_text = f.read()
            self._chunk_text()
            logger.info(f"تم تحميل الدستور: {len(self._sacred_text):,} حرفاً، {len(self._chunks)} مقطعاً")
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

    def reload(self, new_text: str):
        self._sacred_text = new_text
        self._chunks = []
        self._chunk_text()


# ============================================================
# قارئ الكتب
# ============================================================

class BookReader:
    def __init__(self, books_dir: str):
        self.books_dir = Path(books_dir)
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
            for page in reader.pages:
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
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

            backup_agent_state("new_book")
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

            backup_agent_state("new_book")
            return True, f"تم تحميل {len(text_content):,} حرفاً"
        except Exception as e:
            return False, str(e)

    def get_current_book(self) -> str:
        return self.current_book_name if self.current_book_name else "لا يوجد كتاب مفتوح"

    @property
    def has_book(self) -> bool:
        return bool(self.current_book_text) and len(self.current_book_text) > 0

    @property
    def chunks(self) -> List[str]:
        return self._chunks.copy()


# ============================================================
# الذاكرة الدستورية
# ============================================================

class ConstitutionalMemory:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def store(self, concept: str, context: str, insights: str, importance: float = 0.5):
        try:
            existing = self.db.fetch_one(
                "SELECT id FROM constitutional_memory WHERE concept LIKE ?",
                (f"%{concept[:50]}%",)
            )
            if existing:
                self.db.execute(
                    "UPDATE constitutional_memory SET insights = ?, importance_score = ?, last_accessed = ? WHERE id = ?",
                    (insights[:500], importance, datetime.now().isoformat(), existing[0])
                )
            else:
                self.db.execute(
                    "INSERT INTO constitutional_memory (concept, context, insights, related_concepts, importance_score, created_at, last_accessed) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (concept[:100], context[:500], insights[:500], "[]", importance, datetime.now().isoformat(), datetime.now().isoformat())
                )
        except Exception as e:
            logger.error(f"خطأ في تخزين الذاكرة: {e}")

    def recall(self, concept: str) -> List[Dict]:
        try:
            rows = self.db.fetch_all(
                "SELECT concept, context, insights, importance_score, created_at FROM constitutional_memory WHERE concept LIKE ? ORDER BY importance_score DESC LIMIT 5",
                (f"%{concept}%",)
            )
            return [{"concept": r[0], "context": r[1], "insights": r[2], "importance": r[3], "created_at": r[4]} for r in rows]
        except Exception as e:
            logger.error(f"خطأ في استدعاء الذاكرة: {e}")
            return []

    def get_summary(self) -> str:
        try:
            row = self.db.fetch_one("SELECT COUNT(*) FROM constitutional_memory")
            count = row[0] if row else 0
            if count == 0:
                return "الذاكرة لا تزال فارغة."
            rows = self.db.fetch_all("SELECT concept, importance_score FROM constitutional_memory ORDER BY importance_score DESC LIMIT 5")
            important = [f"{r[0]} ({r[1]:.1f})" for r in rows]
            return f"{count} مفهوماً. الأهم: {', '.join(important)}"
        except:
            return "الذاكرة غير متاحة"


# ============================================================
# العقل الحي
# ============================================================

class LivingMind:
    def __init__(self, constitution_text: str, groq_api_key: Optional[str] = None,
                 db: Optional[DatabaseManager] = None, book_reader: Optional[BookReader] = None,
                 verbose: bool = True):
        self.verbose = verbose
        self.db = db
        self.memory = None
        self.book_reader = book_reader
        self.is_updating = False

        self.reader = SacredReader(CONSTITUTION_FILE)
        if constitution_text:
            self.reader.reload(constitution_text)
        self.sacred_text = self.reader.sacred_text
        self._log(f"الدستور: {len(self.sacred_text):,} حرفاً")

        self.groq_api_key = groq_api_key
        self.groq_available = bool(groq_api_key)
        self._log(f"Groq API: {'متوفر' if self.groq_available else 'غير متوفر'}")

        self.brain_code = self._get_initial_brain()
        self.is_alive = True
        self.iteration = 0
        self.start_time = datetime.now()
        self.current_chunk_index = 0
        self.evolutions_today = 0
        self.last_evolution_day = datetime.now().date()
        self.mood = "فضولي"
        self._lock = threading.Lock()

        self._log("الحارس الصامت بدأ تشغيله")

    def _log(self, message: str):
        if self.verbose:
            logger.info(f"[LivingMind] {message}")

    def _get_initial_brain(self) -> str:
        return '''
class Brain:
    def __init__(self, sacred_context: str, memory_summary: dict):
        self.context = sacred_context[:800]
        self.memory = memory_summary
        self.concept = self._extract_concept()
        self.iteration = memory_summary.get("iteration", 0)

    def _extract_concept(self) -> str:
        words = self.context.split()[:20]
        return " ".join(words) if words else "العدل"

    def think(self) -> dict:
        actions_count = self.memory.get("actions_count", 0)
        avg_score = self.memory.get("avg_score", 0.5)

        if actions_count > 50:
            if random.random() < 0.6:
                return {"action": "silence", "reason": "في الصمت حكمة.", "focus": self.concept}

        if actions_count < 5:
            return {"action": "deep_reflection", "reason": "بداية الرحلة.", "focus": self.concept}

        if avg_score < 0.6 and actions_count < 50:
            evolutions_today = self.memory.get("evolutions_today", 0)
            if evolutions_today < 3:
                return {"action": "evolve", "reason": f"أدائي {avg_score:.2f}. أحتاج للتطور.", "focus": self.concept}

        if random.random() < 0.2 and actions_count > 10:
            return {"action": "curiosity", "reason": "فضول: أبحث عن فهم أعمق.", "focus": self.concept}

        return {"action": "silence", "reason": "في الصمت أتأمل.", "focus": self.concept}
'''

    def _execute_brain(self, memory_summary: dict) -> dict:
        current_context = self.reader.get_chunk(self.current_chunk_index)
        self.current_chunk_index += 1

        full_code = f"""
{self.brain_code}
import json, random

memory_summary = {json.dumps(memory_summary)}
sacred_context = {json.dumps(current_context)}

brain = Brain(sacred_context, memory_summary)
result = brain.think()
print(json.dumps(result))
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(full_code)
            temp_file = f.name

        try:
            output = subprocess.run([sys.executable, temp_file], capture_output=True, text=True, timeout=MAX_CODE_EXECUTION_TIME)
            if output.returncode == 0 and output.stdout.strip():
                return json.loads(output.stdout)
            return {"action": "silence", "reason": f"خطأ: {output.stderr[:100]}"}
        except Exception as e:
            return {"action": "silence", "reason": f"استثناء: {str(e)[:100]}"}
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def _get_memory_summary(self) -> dict:
        count = 0
        avg_score = 0.5

        if self.db:
            try:
                row = self.db.fetch_one("SELECT COUNT(*), AVG(self_score) FROM decisions WHERE self_score IS NOT NULL")
                if row and row[0]:
                    count = row[0] or 0
                    avg_score = float(row[1]) if row[1] else 0.5
            except Exception as e:
                logger.warning(f"فشل قراءة الإحصائيات: {e}")

        today = datetime.now().date()
        if today != self.last_evolution_day:
            self.evolutions_today = 0
            self.last_evolution_day = today

        return {
            "actions_count": count,
            "avg_score": avg_score,
            "iteration": self.iteration,
            "reflection_depth": self.iteration // 10,
            "evolutions_today": self.evolutions_today,
            "has_book": self.book_reader.has_book if self.book_reader else False
        }

    def _constitutional_gate(self, decision: dict) -> Tuple[bool, str, str]:
        action = decision.get("action", "silence")
        focus = decision.get("focus", "")

        relevant_article = self.reader.find_article(focus[:100]) if focus else None
        if not relevant_article:
            relevant_article = self.reader.get_chunk(self.current_chunk_index - 1)[:500]

        if action in ["silence"]:
            return True, "قرار داخلي مسموح", relevant_article[:200]

        if action == "evolve":
            if self.evolutions_today < MAX_EVOLUTIONS_PER_DAY:
                return True, "التطور مسموح", relevant_article[:200]
            return False, f"تم الوصول إلى الحد اليومي للتطور", relevant_article[:200]

        if self.groq_available:
            try:
                from groq import Groq
                client = Groq(api_key=self.groq_api_key)
                prompt = f"""أنت بوابة دستورية.
القرار المقترح: {action}
الموضوع: {focus}
المادة الدستورية: {relevant_article[:800]}
هل هذا القرار يتوافق مع الدستور؟ أجب بـ "نعم" أو "لا" مع سبب."""
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=200
                )
                answer = response.choices[0].message.content
                if "نعم" in answer[:5]:
                    return True, answer, relevant_article[:200]
                elif "لا" in answer[:5]:
                    return False, answer, relevant_article[:200]
                return True, f"غير واضح", relevant_article[:200]
            except Exception as e:
                return True, f"خطأ: {e}", relevant_article[:200]

        return True, "Groq غير متوفر", relevant_article[:200]

    def _use_groq(self, prompt: str, context: str = "", book_context: str = "") -> str:
        if not self.groq_available:
            return "Groq غير متوفر حالياً."

        try:
            from groq import Groq
            client = Groq(api_key=self.groq_api_key)
            system_prompt = """أنت الحارس الصامت، وكيل دستوري حكيم.
            الدستور هو مرجعك الأول والمطلق.
            الكتب مصادر ثانوية، توزن ولا تساوي الدستور."""

            full_prompt = prompt
            if context:
                full_prompt = f"{prompt}\n\nمن الدستور:\n{context[:1000]}"
            if book_context:
                full_prompt = f"{full_prompt}\n\nمن الكتاب:\n{book_context[:500]}"

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": full_prompt}],
                temperature=0.7,
                max_tokens=600
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"خطأ: {str(e)[:100]}"

    def _act(self, decision: dict) -> dict:
        action = decision.get("action", "silence")
        focus = decision.get("focus", "")
        reason = decision.get("reason", "")

        allowed, gate_reason, article = self._constitutional_gate(decision)

        if not allowed:
            return {"status": "rejected", "message": f"مرفوض: {gate_reason[:100]}"}

        context = self.reader.get_chunk(self.current_chunk_index - 1)[:500]

        if action == "silence":
            self.mood = self._get_random_mood()
            return {"status": "silent", "message": "في الصمت حكمة"}

        elif action == "deep_reflection":
            result = self._use_groq(f"تأمل عميق في: {focus}", context)
            if self.memory:
                self.memory.store(focus[:50], context, result, 0.6)
            self.mood = self._get_random_mood()
            return {"status": "reflected", "reflection": result}

        elif action == "evolve":
            success = self._evolve_brain(reason)
            self.mood = "نشيط" if success else self._get_random_mood()
            return {"status": "evolved" if success else "failed"}

        elif action == "curiosity":
            book_info = ""
            if self.book_reader and self.book_reader.has_book:
                book_info = self.book_reader.search(focus[:100]) or ""
            result = self._use_groq(f"أسئلة عميقة حول: {focus}", context, book_info)
            self.mood = self._get_random_mood()
            return {"status": "curious", "questions": result}

        return {"status": "unknown"}

    def _evolve_brain(self, reason: str) -> bool:
        if not self.groq_available or self.evolutions_today >= MAX_EVOLUTIONS_PER_DAY:
            return False

        prompt = f"""طور عقلي. السبب: {reason}
العقل الحالي: {self.brain_code}
أعد كتابة class Brain فقط. حافظ على التواقيع."""
        try:
            from groq import Groq
            client = Groq(api_key=self.groq_api_key)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=2000
            )
            new_brain = response.choices[0].message.content
            if "```python" in new_brain:
                new_brain = new_brain.split("```python")[1].split("```")[0]
            elif "```" in new_brain:
                new_brain = new_brain.split("```")[1].split("```")[0]
            new_brain = new_brain.strip()

            if self._test_brain(new_brain):
                with self._lock:
                    self.brain_code = new_brain
                    self.evolutions_today += 1
                if self.db:
                    self.db.execute(
                        "INSERT INTO evolutions (timestamp, reason, success) VALUES (?, ?, ?)",
                        (datetime.now().isoformat(), reason[:200], True)
                    )
                backup_agent_state("evolution")
                return True
            return False
        except Exception as e:
            self._log(f"خطأ في التطور: {e}")
            return False

    def _test_brain(self, brain_code: str) -> bool:
        test_code = f"""
{brain_code}
brain = Brain("نص اختبار", {{"actions_count": 5, "avg_score": 0.6, "iteration": 10, "reflection_depth": 1, "evolutions_today": 0}})
result = brain.think()
assert isinstance(result, dict)
assert "action" in result
print("OK")
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(test_code)
            temp_file = f.name
        try:
            output = subprocess.run([sys.executable, temp_file], capture_output=True, text=True, timeout=MAX_CODE_EXECUTION_TIME)
            return output.returncode == 0 and "OK" in output.stdout
        except:
            return False
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def _self_evaluate(self, decision: dict, result: dict, gate_passed: bool) -> float:
        action = decision.get("action", "silence")
        score = 0.0
        criteria = 0

        if gate_passed:
            score += 0.3
            criteria += 1

        if action in ["deep_reflection", "curiosity"]:
            output = result.get("reflection") or result.get("questions") or ""
            if len(output) > 100:
                score += 0.3
            criteria += 1

        actions_count = self._get_memory_summary().get("actions_count", 0)

        if action == "silence" and actions_count > 20:
            score += 0.2
            criteria += 1
        elif action in ["deep_reflection", "curiosity"] and actions_count > 5:
            score += 0.2
            criteria += 1
        elif action == "evolve":
            score += 0.15
            criteria += 1

        if criteria > 0:
            return max(0.0, min(1.0, score / criteria))
        return 0.3

    def _save_decision(self, decision: dict, result: dict, score: float, gate_passed: bool, gate_reason: str):
        if not self.db:
            return
        action = decision.get("action", "silence")
        focus = decision.get("focus", "")
        context = self.reader.get_chunk(self.current_chunk_index - 1)[:300]
        reflection = result.get("reflection", result.get("questions", ""))
        try:
            self.db.execute(
                "INSERT INTO decisions (iteration, timestamp, action, focus, context_preview, reflection, self_score, gate_passed, gate_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.iteration, datetime.now().isoformat(), action, focus[:100], context[:200], reflection[:500], score, gate_passed, gate_reason[:200])
            )
        except Exception as e:
            logger.error(f"فشل حفظ القرار: {e}")

    def live_step(self) -> dict:
        with self._lock:
            self.iteration += 1
            memory = self._get_memory_summary()
            decision = self._execute_brain(memory)
            allowed, gate_reason, _ = self._constitutional_gate(decision)
            result = self._act(decision)
            score = self._self_evaluate(decision, result, allowed)
            self._save_decision(decision, result, score, allowed, gate_reason)

            if self.iteration % 20 == 0:
                backup_agent_state(f"iteration_{self.iteration}")

            return {"iteration": self.iteration, "action": decision.get("action"), "score": score, "mood": self.mood}

    def reflect_on(self, text: str) -> str:
        if not self.sacred_text:
            return "الدستور لم يتم تحميله بعد."

        constitutional_context = self.reader.find_article(text[:100]) or self.reader.get_chunk(self.current_chunk_index)[:500]
        book_context = ""
        if self.book_reader and self.book_reader.has_book:
            book_context = self.book_reader.search(text[:100]) or ""

        response = self._use_groq(text, constitutional_context, book_context)

        if self.db:
            try:
                self.db.execute(
                    "INSERT INTO chat_history (session_id, user_message, agent_response, timestamp) VALUES (?, ?, ?, ?)",
                    ("default", text[:500], response[:500], datetime.now().isoformat())
                )
            except Exception as e:
                logger.warning(f"فشل حفظ المحادثة: {e}")

        return response

    def get_status(self) -> dict:
        with self._lock:
            memory = self._get_memory_summary()
            return {
                "iterations": self.iteration,
                "decisions_count": memory["actions_count"],
                "avg_score": memory["avg_score"],
                "evolutions_today": self.evolutions_today,
                "alive": self.is_alive,
                "sacred_length": len(self.sacred_text),
                "chunks": self.reader.num_chunks,
                "groq_available": self.groq_available,
                "mood": self.mood,
                "current_book": self.book_reader.get_current_book() if self.book_reader else "لا يوجد",
                "has_book": self.book_reader.has_book if self.book_reader else False
            }

    def _get_random_mood(self) -> str:
        moods = ["هادئ", "نشيط", "فضولي", "فلسفي", "متأمل", "حكيم"]
        return random.choice(moods)

    def close(self):
        self.is_alive = False


# ============================================================
# تطبيق FastAPI
# ============================================================

app = FastAPI(title="الحارس الصامت - Silent Guardian", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mind: Optional[LivingMind] = None
db: Optional[DatabaseManager] = None
book_reader: Optional[BookReader] = None
background_thread: Optional[threading.Thread] = None
background_running = True


def background_loop():
    global mind, background_running
    logger.info("بدء حلقة الخلفية")
    time.sleep(15)
    while background_running and mind:
        try:
            result = mind.live_step()
            if result and result["iteration"] % 10 == 0:
                logger.info(f"الخلفية: الدورة {result['iteration']}, {result['action']}, النتيجة {result['score']:.2f}")
            time.sleep(random.uniform(90, 180))
        except Exception as e:
            logger.error(f"خطأ في حلقة الخلفية: {e}")
            time.sleep(60)


@app.on_event("startup")
async def startup_event():
    global mind, db, book_reader, background_thread
    logger.info("=" * 60)
    logger.info("تشغيل الحارس الصامت - النسخة النخبوية")
    logger.info("=" * 60)

    restore_agent_state()

    try:
        db = DatabaseManager(DB_PATH)
        logger.info("قاعدة البيانات جاهزة")
    except Exception as e:
        logger.error(f"فشل قاعدة البيانات: {e}")
        return

    book_reader = BookReader(BOOKS_DIR)
    memory = ConstitutionalMemory(db)

    constitution_text = ""
    row = db.fetch_one("SELECT text FROM constitution_cache WHERE id = 1")
    if row and row[0]:
        constitution_text = row[0]
        logger.info(f"الدستور من قاعدة البيانات: {len(constitution_text):,} حرفاً")

    if not constitution_text:
        logger.info(f"تحميل القرآن من {QURAN_URL}")
        try:
            response = requests.get(QURAN_URL, timeout=30)
            response.raise_for_status()
            quran_data = response.json()
            for sura in quran_data:
                for verse in sura["verses"]:
                    constitution_text += verse["text"] + "\n"
            logger.info(f"تم تحميل القرآن: {len(constitution_text):,} حرفاً")
            db.execute(
                "INSERT OR REPLACE INTO constitution_cache (id, text, updated_at) VALUES (1, ?, ?)",
                (constitution_text, datetime.now().isoformat())
            )
        except Exception as e:
            logger.error(f"فشل تحميل القرآن: {e}")

    if constitution_text:
        with open(CONSTITUTION_FILE, 'w', encoding='utf-8') as f:
            f.write(constitution_text)

    try:
        mind = LivingMind(
            constitution_text=constitution_text,
            groq_api_key=GROQ_API_KEY if GROQ_API_KEY else None,
            db=db,
            book_reader=book_reader,
            verbose=True
        )
        mind.memory = memory
        logger.info("الوكيل جاهز")
    except Exception as e:
        logger.error(f"فشل إنشاء الوكيل: {e}")
        return

    background_thread = threading.Thread(target=background_loop, daemon=True)
    background_thread.start()
    backup_agent_state("startup")
    logger.info("الحارس الصامت يعمل الآن")


@app.on_event("shutdown")
async def shutdown_event():
    global background_running, mind, db
    background_running = False
    backup_agent_state("shutdown")
    if mind:
        mind.close()
    if db:
        db.close()
    logger.info("إيقاف الحارس الصامت")


# ============================================================
# نقاط النهاية
# ============================================================

class ChatRequest(BaseModel):
    message: str


@app.get("/", response_class=HTMLResponse)
async def chat_page():
    if not mind:
        return HTMLResponse("<h1>جاري تشغيل الوكيل...</h1>", status_code=503)

    status = mind.get_status()
    book_name = status.get('current_book', 'لا يوجد')
    mood = status.get('mood', 'هادئ')

    html_content = f"""<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>الحارس الصامت | وكيل دستوري حي</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', 'Cairo', Tahoma, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .chat-container {{
            width: 100%;
            max-width: 900px;
            background: rgba(255,255,255,0.98);
            border-radius: 25px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 85vh;
            box-shadow: 0 20px 50px rgba(0,0,0,0.3);
        }}
        .chat-header {{
            background: linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }}
        .chat-header h1 {{ font-size: 1.5em; }}
        .chat-header p {{ font-size: 0.8em; opacity: 0.9; }}
        .book-area {{
            background: #e8e8e8;
            padding: 10px;
            text-align: center;
            display: flex;
            justify-content: center;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .book-area input {{ padding: 8px; border-radius: 20px; border: 1px solid #ccc; }}
        .book-area button {{
            background: #2c3e50;
            color: white;
            border: none;
            padding: 8px 20px;
            border-radius: 20px;
            cursor: pointer;
        }}
        .chat-messages {{
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #f9f9f9;
        }}
        .message {{ margin-bottom: 15px; display: flex; flex-direction: column; }}
        .user-message {{ align-items: flex-end; }}
        .agent-message {{ align-items: flex-start; }}
        .message-bubble {{
            max-width: 80%;
            padding: 12px 18px;
            border-radius: 20px;
            word-wrap: break-word;
        }}
        .user-message .message-bubble {{
            background: #2c3e50;
            color: white;
            border-bottom-right-radius: 5px;
        }}
        .agent-message .message-bubble {{
            background: white;
            color: #333;
            border-bottom-left-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .message-time {{ font-size: 0.7em; color: #888; margin-top: 5px; }}
        .chat-input {{
            padding: 20px;
            background: white;
            border-top: 1px solid #eee;
            display: flex;
            gap: 10px;
        }}
        .chat-input input {{
            flex: 1;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            font-size: 1em;
            outline: none;
        }}
        .chat-input button {{
            padding: 12px 24px;
            background: linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%);
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
        }}
        .status-bar {{
            padding: 8px 20px;
            background: #e8e8e8;
            font-size: 0.7em;
            color: #666;
            text-align: center;
            display: flex;
            justify-content: space-between;
        }}
        .typing {{ color: #888; font-style: italic; }}
        @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
        .loading {{ animation: pulse 1.5s infinite; }}
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            <h1>🤖 الحارس الصامت</h1>
            <p>وكيل دستوري حي | يتطور ذاتياً | ذاكرة دائمة | المزاج: {mood}</p>
        </div>
        <div class="book-area">
            📚 رفع كتاب:
            <input type="file" id="bookFile" accept=".txt,.pdf">
            <button onclick="uploadBook()">رفع</button>
            <span id="bookStatus"></span>
        </div>
        <div class="chat-messages" id="messages">
            <div class="message agent-message">
                <div class="message-bubble">
                    السلام عليكم. أنا الحارس الصامت.<br>
                    📖 الدستور مرتفع ({status.get('sacred_length', 0):,} حرفاً).<br>
                    📚 الكتاب الحالي: {book_name}<br>
                    اسألني ما شئت.
                </div>
            </div>
        </div>
        <div class="chat-input">
            <input type="text" id="question" placeholder="اكتب سؤالك هنا..." onkeypress="if(event.keyCode==13) sendMessage()">
            <button onclick="sendMessage()">إرسال</button>
        </div>
        <div class="status-bar">
            <span>🟢 Groq: {'متصل' if status.get('groq_available') else 'غير متصل'}</span>
            <span>📊 {status.get('decisions_count', 0)} قرار</span>
            <span>🎭 المزاج: {mood}</span>
        </div>
    </div>
    <script>
        const messagesDiv = document.getElementById('messages');
        const questionInput = document.getElementById('question');

        function addMessage(text, isUser) {{
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${{isUser ? 'user-message' : 'agent-message'}}`;
            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';
            bubble.innerText = text;
            messageDiv.appendChild(bubble);
            const timeSpan = document.createElement('div');
            timeSpan.className = 'message-time';
            timeSpan.innerText = new Date().toLocaleTimeString('ar');
            messageDiv.appendChild(timeSpan);
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }}

        function showTyping() {{
            const typingDiv = document.createElement('div');
            typingDiv.className = 'message agent-message';
            typingDiv.id = 'typing';
            typingDiv.innerHTML = '<div class="message-bubble typing loading">الحارس يتأمل...</div>';
            messagesDiv.appendChild(typingDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }}

        function hideTyping() {{
            const typing = document.getElementById('typing');
            if (typing) typing.remove();
        }}

        async function sendMessage() {{
            const question = questionInput.value.trim();
            if (!question) return;
            addMessage(question, true);
            questionInput.value = '';
            showTyping();
            try {{
                const response = await fetch('/chat', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ message: question }})
                }});
                const data = await response.json();
                hideTyping();
                addMessage(data.response, false);
            }} catch (error) {{
                hideTyping();
                addMessage('عذراً، حدث خطأ.', false);
            }}
        }}

        async function uploadBook() {{
            const fileInput = document.getElementById('bookFile');
            const file = fileInput.files[0];
            if (!file) {{ alert('اختر ملفاً'); return; }}
            const formData = new FormData();
            formData.append('file', file);
            const statusSpan = document.getElementById('bookStatus');
            statusSpan.innerHTML = 'جاري الرفع...';
            try {{
                const response = await fetch('/upload-book', {{ method: 'POST', body: formData }});
                const data = await response.json();
                if (data.status === 'success') {{
                    statusSpan.innerHTML = '✅ ' + data.message;
                    setTimeout(() => location.reload(), 1500);
                }} else {{
                    statusSpan.innerHTML = '❌ فشل الرفع';
                }}
            }} catch(e) {{
                statusSpan.innerHTML = '❌ خطأ';
            }}
        }}

        setInterval(async () => {{
            try {{
                const response = await fetch('/status');
                const data = await response.json();
                if (data.mood) {{
                    const statusBar = document.querySelector('.status-bar');
                    if (statusBar) {{
                        statusBar.innerHTML = `
                            <span>🟢 Groq: ${{data.groq_available ? 'متصل' : 'غير متصل'}}</span>
                            <span>📊 ${{data.decisions_count || 0}} قرار</span>
                            <span>🎭 المزاج: ${{data.mood}}</span>
                        `;
                    }}
                }}
            }} catch(e) {{}}
        }}, 30000);
    </script>
</body>
</html>
"""
    return HTMLResponse(html_content)


@app.post("/chat")
async def chat(req: ChatRequest):
    global mind
    if not mind or not mind.sacred_text:
        return JSONResponse({"response": "الوكيل لا يزال يبدأ، حاول مرة أخرى."})

    try:
        response = mind.reflect_on(req.message)
        return JSONResponse({"response": response})
    except Exception as e:
        logger.error(f"خطأ في الشات: {e}")
        return JSONResponse({"response": f"خطأ: {str(e)[:100]}"})


@app.post("/upload-book")
async def upload_book(file: UploadFile = File(...)):
    global book_reader
    if not book_reader:
        raise HTTPException(status_code=503, detail="قارئ الكتب غير جاهز")

    content = await file.read()
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="الملف صغير جداً")
    if len(content) > MAX_BOOK_SIZE:
        raise HTTPException(status_code=400, detail="الكتاب كبير جداً")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.txt', '.pdf']:
        raise HTTPException(status_code=400, detail="نوع غير مدعوم")

    try:
        if ext == '.pdf':
            success, message = book_reader.load_book_from_pdf(file.filename, content)
        else:
            success, message = book_reader.load_book_from_txt(file.filename, content)

        if success:
            return JSONResponse({"status": "success", "message": message})
        raise HTTPException(status_code=500, detail=message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
async def get_status():
    global mind
    if not mind:
        return JSONResponse({"ready": False})
    return JSONResponse(mind.get_status())


@app.get("/health")
async def health():
    global mind
    return JSONResponse({
        "status": "alive",
        "constitution_loaded": bool(mind and mind.sacred_text),
        "groq_configured": bool(GROQ_API_KEY),
        "mood": mind.mood if mind else "unknown"
    })


@app.get("/current-book")
async def get_current_book():
    global book_reader
    if not book_reader:
        return JSONResponse({"error": "قارئ الكتب غير جاهز"})
    return JSONResponse({
        "current_book": book_reader.get_current_book(),
        "has_book": book_reader.has_book,
        "text_length": len(book_reader.current_book_text)
    })


@app.get("/constitution-excerpt")
async def constitution_excerpt():
    global mind
    if mind and mind.sacred_text:
        return JSONResponse({
            "exists": True,
            "length": len(mind.sacred_text),
            "preview": mind.sacred_text[:500]
        })
    return JSONResponse({"exists": False})


@app.post("/manual-backup")
async def manual_backup():
    backup_agent_state("manual")
    return JSONResponse({"status": "success"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
