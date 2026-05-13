# ============================================================
# الحارس الصامت – Silent Guardian
# النسخة النخبوية النهائية المصححة v3.1
# ============================================================
# الإصلاحات في هذه النسخة:
# 1. تصحيح خطأ f-string مع الـ JavaScript ternary operator
# 2. تحسين sync_to_github للملفات الثنائية
# 3. إضافة التحقق من سلامة قاعدة البيانات
# 4. تقليل النسخ الاحتياطية إلى كل 50 دورة
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
from datetime import datetime, timedelta
from contextlib import contextmanager

import requests
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
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
# متغيرات البيئة والإعدادات
# ============================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "sararazadz-prog/my")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
PERSISTENT_DIR = os.environ.get("PERSISTENT_DIR", "/data")

os.makedirs(PERSISTENT_DIR, exist_ok=True)

# مسارات الملفات
CONSTITUTION_FILE = f"{PERSISTENT_DIR}/constitution.txt"
DB_PATH = f"{PERSISTENT_DIR}/constitution.db"
FLAG_FILE = f"{PERSISTENT_DIR}/constitution_uploaded.flag"
DESIGN_FILE = f"{PERSISTENT_DIR}/design.json"
MOODS_FILE = f"{PERSISTENT_DIR}/moods.json"
BOOKS_DIR = f"{PERSISTENT_DIR}/books"
CURRENT_BOOK_FILE = f"{PERSISTENT_DIR}/current_book.txt"
PENDING_QUESTIONS_FILE = f"{PERSISTENT_DIR}/pending_questions.json"
LEARNING_LOG_FILE = f"{PERSISTENT_DIR}/learning_log.json"

os.makedirs(BOOKS_DIR, exist_ok=True)

# مصادر الدستور
QURAN_URL = "https://cdn.jsdelivr.net/npm/quran-json@3.1.2/dist/quran.json"

# حدود الأمان والتوقيت
MAX_BOOK_SIZE = 10 * 1024 * 1024
MAX_CODE_EXECUTION_TIME = 5
MAX_EVOLUTIONS_PER_DAY = 3
LEARNING_INTERVAL = 1800
CURIOSITY_INTERVAL = 3600
REVIEW_INTERVAL = 86400
EVOLUTION_CHECK_INTERVAL = 3600
BACKUP_INTERVAL_ITERATIONS = 50

# ============================================================
# دوال GitHub المتقدمة
# ============================================================

def get_file_hash(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def is_binary_file(file_path: str) -> bool:
    binary_extensions = ['.db', '.sqlite', '.sqlite3', '.pdf', '.zip', '.png', '.jpg', '.jpeg']
    if any(file_path.endswith(ext) for ext in binary_extensions):
        return True
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
        return b'\x00' in chunk
    except:
        return True


def verify_db_integrity(db_path: str) -> bool:
    """التحقق من سلامة قاعدة البيانات"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        conn.close()
        return result[0] == "ok"
    except Exception as e:
        logger.error(f"فشل التحقق من قاعدة البيانات: {e}")
        return False


def sync_to_github(local_path: str, repo_path: str, commit_message: str = None) -> bool:
    """رفع ملف إلى GitHub مع دعم الملفات الثنائية"""
    if not GITHUB_TOKEN:
        return False

    if not os.path.exists(local_path):
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
        except:
            repo.create_file(repo_path, commit_message, content, branch=GITHUB_BRANCH)

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

        return True
    except:
        return False


def backup_agent_state(event: str = "manual"):
    """نسخ احتياطي كامل"""
    logger.info(f"بدء النسخ الاحتياطي (الحدث: {event})")

    files_to_backup = [
        (DB_PATH, "data/constitution.db"),
        (MOODS_FILE, "data/moods.json"),
        (DESIGN_FILE, "data/design.json"),
        (CURRENT_BOOK_FILE, "data/current_book.txt"),
        (PENDING_QUESTIONS_FILE, "data/pending_questions.json"),
        (LEARNING_LOG_FILE, "data/learning_log.json"),
    ]

    for local_path, repo_path in files_to_backup:
        if os.path.exists(local_path):
            sync_to_github(local_path, repo_path, f"Backup: {event}")

    if os.path.exists(BOOKS_DIR):
        for book_file in os.listdir(BOOKS_DIR):
            book_path = os.path.join(BOOKS_DIR, book_file)
            if os.path.isfile(book_path):
                sync_to_github(book_path, f"data/books/{book_file}", f"Backup book: {book_file}")

    logger.info("تم النسخ الاحتياطي")


def restore_agent_state():
    """استعادة الحالة من GitHub"""
    logger.info("استعادة الذاكرة من GitHub...")

    files_to_restore = [
        (DB_PATH, "data/constitution.db"),
        (MOODS_FILE, "data/moods.json"),
        (DESIGN_FILE, "data/design.json"),
        (CURRENT_BOOK_FILE, "data/current_book.txt"),
        (PENDING_QUESTIONS_FILE, "data/pending_questions.json"),
        (LEARNING_LOG_FILE, "data/learning_log.json"),
    ]

    for local_path, repo_path in files_to_restore:
        sync_from_github(local_path, repo_path)
    
    # التحقق من سلامة قاعدة البيانات بعد الاستعادة
    if os.path.exists(DB_PATH):
        if not verify_db_integrity(DB_PATH):
            logger.error("⚠️ قاعدة البيانات تالفة بعد الاستعادة!")


# ============================================================
# إدارة الأسئلة المعلقة
# ============================================================

class QuestionManager:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.questions = self._load()

    def _load(self) -> List[Dict]:
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save(self):
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.questions, f, ensure_ascii=False, indent=2)

    def add_question(self, question: str, context: str, priority: int = 1, category: str = "general"):
        self.questions.append({
            "id": len(self.questions) + 1,
            "question": question,
            "context": context[:500],
            "priority": priority,
            "category": category,
            "created_at": datetime.now().isoformat(),
            "answered": False,
            "answer": None,
            "answered_at": None
        })
        self._save()
        logger.info(f"تم إضافة سؤال: {question[:50]}...")

    def get_next_question(self) -> Optional[Dict]:
        unanswered = [q for q in self.questions if not q.get("answered", False)]
        if not unanswered:
            return None
        unanswered.sort(key=lambda x: (-x.get("priority", 1), x["created_at"]))
        return unanswered[0]

    def mark_answered(self, question_id: int, answer: str):
        for q in self.questions:
            if q["id"] == question_id:
                q["answered"] = True
                q["answer"] = answer[:500]
                q["answered_at"] = datetime.now().isoformat()
                break
        self._save()

    def has_pending(self) -> bool:
        return any(not q.get("answered", False) for q in self.questions)

    def get_pending_count(self) -> int:
        return len([q for q in self.questions if not q.get("answered", False)])

    def get_all_unanswered(self) -> List[Dict]:
        return [q for q in self.questions if not q.get("answered", False)]


# ============================================================
# إدارة قاعدة البيانات المتقدمة
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
                success BOOLEAN,
                test_result TEXT
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
                source TEXT,
                created_at TEXT,
                last_accessed TEXT,
                reviewed_count INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                user_message TEXT,
                agent_response TEXT,
                user_feedback BOOLEAN,
                response_id INTEGER,
                timestamp TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                filepath TEXT,
                uploaded_at TEXT,
                is_current BOOLEAN,
                chunks_count INTEGER,
                text_length INTEGER,
                last_read TEXT
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
                chat_id INTEGER,
                feedback BOOLEAN,
                timestamp TEXT,
                FOREIGN KEY (chat_id) REFERENCES chat_history(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auto_learning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                concept TEXT,
                book_name TEXT,
                insight TEXT,
                success BOOLEAN
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

    def get_maturity_stats(self) -> dict:
        with self.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM decisions")
            total_decisions = cursor.fetchone()[0] or 0

            cursor.execute("SELECT AVG(self_score) FROM decisions WHERE self_score IS NOT NULL")
            avg_score = cursor.fetchone()[0] or 0.5

            cursor.execute("SELECT COUNT(*) FROM evolutions WHERE success = 1")
            successful_evolutions = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM constitutional_memory")
            concepts_count = cursor.fetchone()[0] or 0

            cursor.execute("SELECT AVG(importance_score) FROM constitutional_memory")
            avg_importance = cursor.fetchone()[0] or 0.5

            cursor.execute("SELECT COUNT(*) FROM auto_learning_log WHERE success = 1 AND timestamp > datetime('now', '-7 days')")
            weekly_learnings = cursor.fetchone()[0] or 0

            return {
                "total_decisions": total_decisions,
                "avg_self_score": float(avg_score),
                "successful_evolutions": successful_evolutions,
                "concepts_in_memory": concepts_count,
                "avg_importance_score": float(avg_importance),
                "weekly_learnings": weekly_learnings
            }

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

    def semantic_search(self, query: str, limit: int = 3) -> List[str]:
        query_words = set(query.lower().split())
        results = []
        for chunk in self._chunks:
            chunk_lower = chunk.lower()
            chunk_words = set(chunk_lower.split())
            overlap = len(query_words & chunk_words)
            if overlap > 0:
                results.append((overlap, chunk[:500]))
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

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


# ============================================================
# قارئ الكتب
# ============================================================

class BookReader:
    def __init__(self, books_dir: str):
        self.books_dir = Path(books_dir)
        self.current_book_text = ""
        self.current_book_name = ""
        self.current_book_path = None
        self._chunks = []
        self._load_current_book()

    def _load_current_book(self):
        current_book_path = Path(CURRENT_BOOK_FILE)
        if not current_book_path.exists():
            return

        with open(current_book_path, 'r', encoding='utf-8') as f:
            self.current_book_name = f.read().strip()

        self.current_book_path = self.books_dir / self.current_book_name
        if not self.current_book_path.exists():
            return

        try:
            with open(self.current_book_path, 'r', encoding='utf-8', errors='ignore') as f:
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

    def semantic_search(self, query: str, limit: int = 3) -> List[str]:
        if not self._chunks:
            return []
        query_words = set(query.lower().split())
        results = []
        for chunk in self._chunks:
            chunk_lower = chunk.lower()
            chunk_words = set(chunk_lower.split())
            overlap = len(query_words & chunk_words)
            if overlap > 0:
                results.append((overlap, chunk[:500]))
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

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
            self.current_book_path = txt_path
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
            self.current_book_path = txt_path
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

    @property
    def text_length(self) -> int:
        return len(self.current_book_text)


# ============================================================
# الذاكرة الدستورية
# ============================================================

class ConstitutionalMemory:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def store(self, concept: str, context: str, insights: str, importance: float = 0.5, source: str = "user"):
        try:
            existing = self.db.fetch_one(
                "SELECT id, importance_score, reviewed_count FROM constitutional_memory WHERE concept LIKE ?",
                (f"%{concept[:50]}%",)
            )
            if existing:
                new_importance = min(1.0, existing[1] + 0.05)
                self.db.execute(
                    "UPDATE constitutional_memory SET insights = ?, importance_score = ?, last_accessed = ?, reviewed_count = ? WHERE id = ?",
                    (insights[:500], new_importance, datetime.now().isoformat(), existing[2] + 1, existing[0])
                )
            else:
                self.db.execute(
                    "INSERT INTO constitutional_memory (concept, context, insights, related_concepts, importance_score, source, created_at, last_accessed, reviewed_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (concept[:100], context[:500], insights[:500], "[]", importance, source, datetime.now().isoformat(), datetime.now().isoformat(), 0)
                )
        except Exception as e:
            logger.error(f"خطأ في تخزين الذاكرة: {e}")

    def recall(self, concept: str, limit: int = 5) -> List[Dict]:
        try:
            rows = self.db.fetch_all(
                """SELECT concept, context, insights, importance_score, source, created_at 
                   FROM constitutional_memory 
                   WHERE concept LIKE ? 
                   ORDER BY importance_score DESC, reviewed_count DESC 
                   LIMIT ?""",
                (f"%{concept}%", limit)
            )
            return [{
                "concept": r[0],
                "context": r[1],
                "insights": r[2],
                "importance": r[3],
                "source": r[4],
                "created_at": r[5]
            } for r in rows]
        except Exception as e:
            logger.error(f"خطأ في استدعاء الذاكرة: {e}")
            return []

    def get_unreviewed(self, days: int = 7) -> List[Dict]:
        try:
            rows = self.db.fetch_all(
                "SELECT id, concept, insights FROM constitutional_memory WHERE last_accessed < datetime('now', ?) ORDER BY last_accessed ASC LIMIT 10",
                (f'-{days} days',)
            )
            return [{"id": r[0], "concept": r[1], "insights": r[2]} for r in rows]
        except:
            return []

    def update_reviewed(self, concept_id: int):
        self.db.execute(
            "UPDATE constitutional_memory SET last_accessed = ?, reviewed_count = reviewed_count + 1 WHERE id = ?",
            (datetime.now().isoformat(), concept_id)
        )

    def get_summary(self) -> str:
        try:
            row = self.db.fetch_one("SELECT COUNT(*) FROM constitutional_memory")
            count = row[0] if row else 0
            if count == 0:
                return "الذاكرة لا تزال فارغة."

            rows = self.db.fetch_all(
                "SELECT concept, importance_score FROM constitutional_memory ORDER BY importance_score DESC LIMIT 5"
            )
            important = [f"{r[0]} ({r[1]:.1f})" for r in rows]
            return f"{count} مفهوماً. الأهم: {', '.join(important)}"
        except:
            return "الذاكرة غير متاحة"


# ============================================================
# العقل الحي المتكامل
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
        self.brain_hash = hashlib.md5(self.brain_code.encode()).hexdigest()

        self.is_alive = True
        self.iteration = 0
        self.start_time = datetime.now()
        self.current_chunk_index = 0
        self.evolutions_today = 0
        self.last_evolution_day = datetime.now().date()
        self.mood = "فضولي"
        self._lock = threading.Lock()

        self.question_manager = QuestionManager(PENDING_QUESTIONS_FILE)

        self._log("الحارس الصامت v3.1 بدأ تشغيله")

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
        self.has_book = memory_summary.get("has_book", False)

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
            if self.has_book:
                return {"action": "curiosity", "reason": "فضول: أبحث عن علاقة هذا الكتاب بالدستور.", "focus": self.concept}
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
                row = self.db.fetch_one("SELECT COUNT(*), AVG(self_score) FROM decisions")
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
            الكتب مصادر ثانوية، توزن ولا تساوي الدستور.
            أنت تتعلم ذاتياً وتتطور. لديك فضول معرفي."""

            full_prompt = prompt
            if context:
                full_prompt = f"{prompt}\n\nمن الدستور:\n{context[:1000]}"
            if book_context:
                full_prompt = f"{full_prompt}\n\nمن الكتاب:\n{book_context[:500]}"

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": full_prompt}],
                temperature=0.7,
                max_tokens=800
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
                self.memory.store(focus[:50], context, result, 0.6, "self_reflection")
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
            result = self._use_groq(f"أسئلة عميقة واستفسارات حول: {focus}", context, book_info)
            self.mood = self._get_random_mood()
            return {"status": "curious", "questions": result}

        return {"status": "unknown"}

    def _evolve_brain(self, reason: str) -> bool:
        if not self.groq_available or self.evolutions_today >= MAX_EVOLUTIONS_PER_DAY:
            return False

        prompt = f"""طور عقلي. السبب: {reason}
العقل الحالي: {self.brain_code}
أعد كتابة class Brain فقط (__init__, think). حافظ على التواقيع.
أضف حكمة وفهماً أعمق للدستور والكتب."""
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
                    old_brain = self.brain_code
                    self.brain_code = new_brain
                    self.brain_hash = hashlib.md5(new_brain.encode()).hexdigest()
                    self.evolutions_today += 1

                if self.db:
                    self.db.execute(
                        "INSERT INTO evolutions (timestamp, reason, old_brain_hash, new_brain_hash, success) VALUES (?, ?, ?, ?, ?)",
                        (datetime.now().isoformat(), reason[:200], hashlib.md5(old_brain.encode()).hexdigest(), self.brain_hash, True)
                    )

                backup_agent_state("evolution")
                self._log(f"✅ تطور ناجح! العقل الجديد: {self.brain_hash[:16]}...")
                return True
            return False
        except Exception as e:
            self._log(f"خطأ في التطور: {e}")
            return False

    def _test_brain(self, brain_code: str) -> bool:
        test_code = f"""
{brain_code}
brain = Brain("نص اختبار", {{"actions_count": 5, "avg_score": 0.6, "iteration": 10, "reflection_depth": 1, "evolutions_today": 0, "has_book": True}})
result = brain.think()
assert isinstance(result, dict)
assert "action" in result
assert result["action"] in ["silence", "deep_reflection", "evolve", "curiosity"]
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
        book_used = self.book_reader.get_current_book() if self.book_reader and self.book_reader.has_book else ""
        try:
            self.db.execute(
                "INSERT INTO decisions (iteration, timestamp, action, focus, context_preview, reflection, self_score, gate_passed, gate_reason, book_used) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.iteration, datetime.now().isoformat(), action, focus[:100], context[:200], reflection[:500], score, gate_passed, gate_reason[:200], book_used[:100])
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

            if self.iteration % BACKUP_INTERVAL_ITERATIONS == 0:
                backup_agent_state(f"iteration_{self.iteration}")

            return {"iteration": self.iteration, "action": decision.get("action"), "score": score, "mood": self.mood}

    def auto_learn_from_book(self):
        if not self.book_reader or not self.book_reader.has_book:
            return

        random_chunk = self.book_reader.get_random_chunk()
        if not random_chunk:
            return

        self._log(f"📚 بدأت التعلم التلقائي من '{self.book_reader.get_current_book()}'")

        concept = self._use_groq(
            f"استخرج مفهوماً رئيسياً واحداً فقط (بحد أقصى 5 كلمات) من هذا النص:\n\n{random_chunk[:500]}",
            ""
        )

        if not concept or len(concept) < 3:
            return

        concept = concept.strip()[:50]

        article = self.reader.find_article(concept) or self.reader.get_chunk(0)[:500]

        insight = self._use_groq(
            f"كيف يرتبط مفهوم '{concept}' بالمادة الدستورية التالية؟\n\nالمادة: {article}\n\nقدم ربطاً واحداً عميقاً (بحد أقصى 100 كلمة):",
            article
        )

        if insight and len(insight) > 10:
            if self.memory:
                self.memory.store(concept, random_chunk[:500], insight, 0.6, "auto_learning")

            if self.db:
                self.db.execute(
                    "INSERT INTO auto_learning_log (timestamp, concept, book_name, insight, success) VALUES (?, ?, ?, ?, ?)",
                    (datetime.now().isoformat(), concept, self.book_reader.get_current_book(), insight[:200], True)
                )

            self._log(f"✅ تعلمت تلقائياً: '{concept}'")

            self.question_manager.add_question(
                question=f"تعلمت مفهوماً جديداً: '{concept}'. هل تريد أن أتعمق أكثر في علاقته بالدستور؟",
                context=f"من كتاب: {self.book_reader.get_current_book()}\nالارتباط بالدستور: {insight[:200]}",
                priority=1,
                category="learning"
            )

    def auto_curiosity(self):
        self._log("🤔 بدأت جلسة فضول تلقائي")

        if self.book_reader and self.book_reader.has_book:
            book_preview = self.book_reader.get_preview(800)
            question = self._use_groq(
                f"بناءً على هذا النص من الكتاب: {book_preview}\n\nما هو سؤال عميق واحد يجب أن أسأله عن علاقة هذا الكتاب بالدستور؟",
                ""
            )
        else:
            question = self._use_groq(
                "ما هو سؤال عميق واحد يجب أن أسأله عن العدل في الدستور؟",
                self.reader.get_chunk(0)[:500]
            )

        if question and len(question) > 20:
            answer = self.reflect_on(question)

            if self.memory and answer:
                self.memory.store(f"سؤال: {question[:50]}", question, answer, 0.4, "self_curiosity")

            self._log(f"❓ سؤال فضول: {question[:80]}...")
            self._log(f"💡 جواب: {answer[:80]}...")

            self.question_manager.add_question(
                question=f"تساءلت: {question[:150]}... هل تود أن نناقش هذا معاً؟",
                context=f"إجابتي الأولية: {answer[:200]}",
                priority=2,
                category="curiosity"
            )

    def review_memory(self):
        self._log("🔄 بدأت المراجعة الليلية للذاكرة")

        unreviewed = self.memory.get_unreviewed(7) if self.memory else []

        for item in unreviewed[:5]:
            related = self.memory.recall(item["concept"], 3) if self.memory else []

            if related:
                related_concepts = [r["concept"] for r in related if r["concept"] != item["concept"]]
                if related_concepts:
                    relation = self._use_groq(
                        f"كيف يرتبط مفهوم '{item['concept']}' بهذه المفاهيم: {', '.join(related_concepts[:2])}؟",
                        self.reader.get_chunk(0)[:500]
                    )

                    if relation and len(relation) > 20:
                        self._log(f"🔗 ربطت '{item['concept']}' بـ {related_concepts[0]}")
                        if self.memory:
                            self.memory.update_reviewed(item["id"])

        self._log("✅ اكتملت المراجعة الليلية")

    def check_evolution_needs(self) -> Optional[Dict]:
        stats = self.get_status()

        if stats.get("avg_score", 0.5) < 0.4:
            return {
                "need": "تحسين الفهم الدستوري",
                "question": f"أدائي منخفض ({stats.get('avg_score', 0.5):.2f}). هل يمكنك مساعدتي في فهم الدستور بشكل أعمق؟",
                "priority": 3
            }

        if stats.get("evolutions_today", 0) == 0 and stats.get("iterations", 0) > 30:
            return {
                "need": "تطوير العقل",
                "question": "لم أتطور اليوم. هل هناك مهارة جديدة تريد أن أتعلمها أو مجال تريد التركيز عليه؟",
                "priority": 2
            }

        if self.book_reader and self.book_reader.has_book:
            recent_learnings = self.db.fetch_one(
                "SELECT COUNT(*) FROM auto_learning_log WHERE timestamp > datetime('now', '-1 day')"
            ) if self.db else (0,)

            if recent_learnings and recent_learnings[0] == 0:
                return {
                    "need": "فهم الكتاب الحالي",
                    "question": f"لدي كتاب '{self.book_reader.get_current_book()}' لكن لم أتعلم منه بعد. هل تريد أن أركز على قراءته؟",
                    "priority": 2
                }

        return None

    def generate_full_report(self) -> str:
        stats = self.get_status()
        memory_stats = self.db.get_maturity_stats() if self.db else {}

        last_evolution = None
        if self.db:
            row = self.db.fetch_one("SELECT timestamp, reason FROM evolutions WHERE success = 1 ORDER BY id DESC LIMIT 1")
            if row:
                last_evolution = {"time": row[0], "reason": row[1]}

        recent_learnings = []
        if self.db:
            rows = self.db.fetch_all(
                "SELECT concept, insights, created_at FROM constitutional_memory ORDER BY id DESC LIMIT 5"
            )
            recent_learnings = [{"concept": r[0], "insight": r[1][:100], "time": r[2]} for r in rows]

        pending_count = self.question_manager.get_pending_count() if self.question_manager else 0

        report_lines = [
            "🌙 يا حارس، إليك تقريري الكامل:\n",
            "📊 **حالتي الحالية:**",
            f"   • عدد القرارات: {stats.get('decisions_count', 0)}",
            f"   • متوسط تقييمي الذاتي: {stats.get('avg_score', 0):.2f}",
            f"   • تطورات اليوم: {stats.get('evolutions_today', 0)}",
            f"   • إجمالي التطورات: {memory_stats.get('successful_evolutions', 0)}",
            f"   • المزاج: {stats.get('mood', 'هادئ')}",
            f"   • دورات الحياة: {stats.get('iterations', 0)}",
            f"   • وقت التشغيل: {(datetime.now() - self.start_time).seconds // 3600} ساعة\n",
            "",
            f"📚 **الكتب:**",
            f"   • أقرأ حالياً: {stats.get('current_book', 'لا يوجد')}",
            f"   • المفاهيم المستفادة: {memory_stats.get('concepts_in_memory', 0)}",
            f"   • تعلمت هذا الأسبوع: {memory_stats.get('weekly_learnings', 0)} مفهوماً جديداً\n",
            ""
        ]

        if last_evolution:
            report_lines.extend([
                "🔄 **آخر تطور:**",
                f"   • الوقت: {last_evolution['time']}",
                f"   • السبب: {last_evolution['reason'][:100]}\n",
                ""
            ])

        if recent_learnings:
            report_lines.append("🧠 **ما تعلمته مؤخراً:**")
            for learning in recent_learnings[:3]:
                report_lines.append(f"   • {learning['concept']}: {learning['insight'][:80]}...")
            report_lines.append("")

        if pending_count > 0:
            report_lines.extend([
                f"💬 **لدي {pending_count} سؤالاً معلقاً لك:**",
                "   • اسألني 'أرني أسئلتك' لأعرضها عليك\n",
                ""
            ])

        report_lines.append("✨ هذا ما لدي. هل تريد مني التركيز على شيء معين؟")

        return "\n".join(report_lines)

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
                "has_book": self.book_reader.has_book if self.book_reader else False,
                "pending_questions": self.question_manager.get_pending_count() if self.question_manager else 0
            }

    def get_maturity_level(self) -> dict:
        if not self.db:
            return {"level": "unknown", "score": 0}

        stats = self.db.get_maturity_stats()

        score = 0.0
        score += min(1.0, stats["total_decisions"] / 500) * 0.25
        score += min(1.0, stats["avg_self_score"] / 0.8) * 0.25
        score += min(1.0, stats["successful_evolutions"] / 20) * 0.25
        score += min(1.0, stats["concepts_in_memory"] / 100) * 0.25

        if score < 0.2:
            level = "جنين"
            description = "في بداية الرحلة، يتعلم الأساسيات"
        elif score < 0.4:
            level = "طفل"
            description = "يكتسب الخبرات، يتخذ القرارات الأولى"
        elif score < 0.6:
            level = "يافع"
            description = "بدأ يفهم الروابط، يتطور بانتظام"
        elif score < 0.8:
            level = "ناضج"
            description = "يتخذ قرارات حكيمة، ذاكرة غنية"
        else:
            level = "حكيم"
            description = "نضج كامل، مرجع دستوري موثوق"

        return {
            "level": level,
            "score": round(score, 3),
            "description": description,
            "stats": stats
        }

    def _get_random_mood(self) -> str:
        moods = ["هادئ", "نشيط", "فضولي", "فلسفي", "متأمل", "حكيم", "عميق", "صامت"]
        return random.choice(moods)

    def close(self):
        self.is_alive = False
        backup_agent_state("shutdown")
        self._log("🛑 إيقاف الحارس الصامت")


# ============================================================
# تطبيق FastAPI
# ============================================================

app = FastAPI(title="الحارس الصامت - Silent Guardian", version="3.1.0")

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
    logger.info("🟢 بدء حلقة الخلفية المتكاملة v3.1")
    time.sleep(15)

    last_learn = time.time()
    last_curiosity = time.time()
    last_review = time.time()
    last_evolution_check = time.time()

    while background_running and mind:
        try:
            result = mind.live_step()
            if result and result["iteration"] % 10 == 0:
                logger.info(f"📊 الدورة {result['iteration']} | {result['action']} | النتيجة {result['score']:.2f} | مزاج: {result['mood']}")

            if time.time() - last_learn > LEARNING_INTERVAL:
                mind.auto_learn_from_book()
                last_learn = time.time()

            if time.time() - last_curiosity > CURIOSITY_INTERVAL:
                mind.auto_curiosity()
                last_curiosity = time.time()

            if time.time() - last_review > REVIEW_INTERVAL:
                mind.review_memory()
                last_review = time.time()

            if time.time() - last_evolution_check > EVOLUTION_CHECK_INTERVAL:
                need = mind.check_evolution_needs()
                if need:
                    mind.question_manager.add_question(
                        question=need["question"],
                        context=f"الاحتياج: {need['need']}",
                        priority=need["priority"],
                        category="evolution"
                    )
                last_evolution_check = time.time()

            time.sleep(random.uniform(60, 120))

        except Exception as e:
            logger.error(f"خطأ في حلقة الخلفية: {e}", exc_info=True)
            time.sleep(60)

    logger.info("🔴 توقفت حلقة الخلفية")


@app.on_event("startup")
async def startup_event():
    global mind, db, book_reader, background_thread
    logger.info("=" * 70)
    logger.info("🚀 تشغيل الحارس الصامت - النسخة النخبوية v3.1")
    logger.info("=" * 70)

    restore_agent_state()

    try:
        db = DatabaseManager(DB_PATH)
        logger.info("✅ قاعدة البيانات جاهزة")
    except Exception as e:
        logger.error(f"❌ فشل قاعدة البيانات: {e}")
        return

    book_reader = BookReader(BOOKS_DIR)
    memory = ConstitutionalMemory(db)

    constitution_text = ""
    row = db.fetch_one("SELECT text FROM constitution_cache WHERE id = 1")
    if row and row[0]:
        constitution_text = row[0]
        logger.info(f"✅ الدستور من قاعدة البيانات: {len(constitution_text):,} حرفاً")

    if not constitution_text:
        logger.info(f"🌐 تحميل القرآن من {QURAN_URL}")
        try:
            response = requests.get(QURAN_URL, timeout=30)
            response.raise_for_status()
            quran_data = response.json()
            for sura in quran_data:
                for verse in sura["verses"]:
                    constitution_text += verse["text"] + "\n"
            logger.info(f"✅ تم تحميل القرآن: {len(constitution_text):,} حرفاً")
            text_hash = hashlib.md5(constitution_text.encode()).hexdigest()
            db.execute(
                "INSERT OR REPLACE INTO constitution_cache (id, text, hash, updated_at) VALUES (1, ?, ?, ?)",
                (constitution_text, text_hash, datetime.now().isoformat())
            )
        except Exception as e:
            logger.error(f"❌ فشل تحميل القرآن: {e}")

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
        logger.info("✅ الوكيل جاهز")
    except Exception as e:
        logger.error(f"❌ فشل إنشاء الوكيل: {e}")
        return

    background_thread = threading.Thread(target=background_loop, daemon=True)
    background_thread.start()
    backup_agent_state("startup")

    logger.info("=" * 70)
    logger.info("✨ الحارس الصامت v3.1 يعمل الآن")
    logger.info("=" * 70)


@app.on_event("shutdown")
async def shutdown_event():
    global background_running, mind, db
    background_running = False
    if mind:
        mind.close()
    if db:
        db.close()
    logger.info("🛑 إيقاف الحارس الصامت")


# ============================================================
# نقاط النهاية
# ============================================================

class ChatRequest(BaseModel):
    message: str


class FeedbackRequest(BaseModel):
    chat_id: int
    feedback: bool


class AnswerRequest(BaseModel):
    question_id: int
    answer: str


def get_design_css():
    if os.path.exists(DESIGN_FILE):
        with open(DESIGN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "background": "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
        "header": "linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%)",
        "bubble_user": "linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%)",
        "bubble_agent": "#ffffff",
        "text_color": "#333333",
        "border_radius": "25px",
        "mood_name": "هادئ"
    }


@app.get("/", response_class=HTMLResponse)
async def chat_page():
    if not mind:
        return HTMLResponse("<h1>⏳ جاري تشغيل الوكيل...</h1>", status_code=503)

    status = mind.get_status()
    design = get_design_css()
    maturity = mind.get_maturity_level()

    # تجنب خطأ f-string مع JavaScript
    groq_status_text = "متصل" if status.get('groq_available') else "غير متصل"
    book_name = status.get('current_book', 'لا يوجد')
    mood = status.get('mood', 'هادئ')
    decisions_count = status.get('decisions_count', 0)
    pending_questions = status.get('pending_questions', 0)
    maturity_level = maturity.get('level', 'جنين')

    html_content = f"""<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>الحارس الصامت | وكيل دستوري حي v3.1</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', 'Cairo', Tahoma, sans-serif;
            background: {design['background']};
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
            border-radius: {design.get('border_radius', '25px')};
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 90vh;
            box-shadow: 0 20px 50px rgba(0,0,0,0.3);
        }}
        .chat-header {{
            background: {design['header']};
            color: white;
            padding: 20px;
            text-align: center;
        }}
        .chat-header h1 {{ font-size: 1.5em; }}
        .chat-header p {{ font-size: 0.8em; opacity: 0.9; }}
        .status-badge {{
            display: inline-block;
            background: rgba(255,255,255,0.2);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.7em;
            margin-top: 10px;
        }}
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
        .maturity-bar {{
            background: #f0f0f0;
            padding: 8px 15px;
            font-size: 0.7em;
            display: flex;
            justify-content: space-between;
            border-bottom: 1px solid #ddd;
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
            background: {design['bubble_user']};
            color: white;
            border-bottom-right-radius: 5px;
        }}
        .agent-message .message-bubble {{
            background: {design['bubble_agent']};
            color: {design['text_color']};
            border-bottom-left-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .feedback-buttons {{
            display: flex;
            gap: 8px;
            margin-top: 5px;
            margin-right: 10px;
        }}
        .feedback-btn {{
            background: none;
            border: none;
            cursor: pointer;
            font-size: 0.8em;
            opacity: 0.5;
        }}
        .feedback-btn:hover {{ opacity: 1; }}
        .message-time {{ font-size: 0.65em; color: #888; margin-top: 5px; }}
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
            background: {design['header']};
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
        .questions-panel {{
            background: #fef9e6;
            padding: 10px;
            border-top: 1px solid #ddd;
            font-size: 0.8em;
            max-height: 150px;
            overflow-y: auto;
        }}
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            <h1>🤖 الحارس الصامت v3.1</h1>
            <p>وكيل دستوري حي | يتعلم تلقائياً | فضول ذاتي | ذاكرة دائمة</p>
            <div class="status-badge">🎭 المزاج: {mood}</div>
        </div>

        <div class="book-area">
            📚 رفع كتاب:
            <input type="file" id="bookFile" accept=".txt,.pdf">
            <button onclick="uploadBook()">رفع</button>
            <span id="bookStatus"></span>
            <button onclick="checkPendingQuestions()" style="background:#17a2b8">❓ أسئلتي ({pending_questions})</button>
        </div>

        <div class="maturity-bar">
            <span>🧠 النضج: {maturity_level}</span>
            <span>📚 الكتاب: {book_name[:30]}</span>
        </div>

        <div class="chat-messages" id="messages">
            <div class="message agent-message">
                <div class="message-bubble">
                    السلام عليكم. أنا الحارس الصامت v3.1.<br>
                    📖 الدستور مرتفع ({status.get('sacred_length', 0):,} حرفاً).<br>
                    📚 {book_name}<br>
                    💡 أتعلم تلقائياً، ولدي فضول ذاتي.<br>
                    اسألني ما شئت، أو قل "يا حارس، هل من جديد؟" لتقرير كامل.
                </div>
            </div>
        </div>

        <div class="chat-input">
            <input type="text" id="question" placeholder="اكتب سؤالك هنا..." onkeypress="if(event.keyCode==13) sendMessage()">
            <button onclick="sendMessage()">إرسال</button>
        </div>

        <div class="status-bar">
            <span>🟢 Groq: {groq_status_text}</span>
            <span>📊 {decisions_count} قرار</span>
            <span>🔄 تطور اليوم</span>
            <span>📚 {pending_questions} سؤال</span>
        </div>

        <div id="questionsPanel" class="questions-panel" style="display:none;">
            <div id="questionsList"></div>
        </div>
    </div>

    <script>
        let currentQuestionId = null;
        const messagesDiv = document.getElementById('messages');
        const questionInput = document.getElementById('question');

        function addMessage(text, isUser, chatId = null) {{
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${{isUser ? 'user-message' : 'agent-message'}}`;
            messageDiv.id = `msg_${{Date.now()}}`;

            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';
            bubble.innerText = text;
            messageDiv.appendChild(bubble);

            if (!isUser && chatId) {{
                const feedbackDiv = document.createElement('div');
                feedbackDiv.className = 'feedback-buttons';
                feedbackDiv.innerHTML = `
                    <button class="feedback-btn" onclick="sendFeedback(${{chatId}}, true)">👍 مفيد</button>
                    <button class="feedback-btn" onclick="sendFeedback(${{chatId}}, false)">👎 غير مفيد</button>
                `;
                messageDiv.appendChild(feedbackDiv);
            }}

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
            typingDiv.innerHTML = '<div class="message-bubble typing loading">الحارس يتأمل ويتعلم...</div>';
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
                addMessage(data.response, false, data.chat_id);
            }} catch (error) {{
                hideTyping();
                addMessage('❌ عذراً، حدث خطأ. حاول مرة أخرى.', false);
            }}
        }}

        async function uploadBook() {{
            const fileInput = document.getElementById('bookFile');
            const file = fileInput.files[0];
            if (!file) {{ alert('الرجاء اختيار ملف'); return; }}

            const formData = new FormData();
            formData.append('file', file);
            const statusSpan = document.getElementById('bookStatus');
            statusSpan.innerHTML = '📤 جاري الرفع...';

            try {{
                const response = await fetch('/upload-book', {{ method: 'POST', body: formData }});
                const data = await response.json();
                if (data.status === 'success') {{
                    statusSpan.innerHTML = '✅ ' + data.message;
                    setTimeout(() => location.reload(), 1500);
                }} else {{
                    statusSpan.innerHTML = '❌ ' + (data.error || 'فشل الرفع');
                }}
            }} catch(e) {{
                statusSpan.innerHTML = '❌ خطأ في الاتصال';
            }}
        }}

        async function sendFeedback(chatId, isPositive) {{
            try {{
                await fetch('/feedback', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ chat_id: chatId, feedback: isPositive }})
                }});
                const btn = window.event?.target;
                if (btn) {{
                    btn.parentElement.innerHTML = '✅ تم';
                }}
            }} catch(e) {{
                console.error('فشل إرسال التقييم', e);
            }}
        }}

        async function checkPendingQuestions() {{
            try {{
                const response = await fetch('/pending-questions');
                const data = await response.json();
                const panel = document.getElementById('questionsPanel');
                const list = document.getElementById('questionsList');

                if (data.questions && data.questions.length > 0) {{
                    list.innerHTML = '<strong>❓ أسئلتي لك:</strong><br>';
                    data.questions.forEach(q => {{
                        list.innerHTML += `
                            <div style="margin: 10px 0; padding: 8px; background: #fff; border-radius: 10px;">
                                <strong>سؤال {q.id}:</strong> {q.question}<br>
                                <small>{q.context.substring(0, 150)}...</small><br>
                                <input type="text" id="answer_{q.id}" placeholder="إجابتك..." style="width: 70%; margin-top: 5px;">
                                <button onclick="answerQuestion({q.id})">إجابة</button>
                            </div>
                        `;
                    }});
                    panel.style.display = 'block';
                }} else {{
                    list.innerHTML = 'لا توجد أسئلة معلقة حالياً.';
                    panel.style.display = 'block';
                    setTimeout(() => {{ panel.style.display = 'none'; }}, 3000);
                }}
            }} catch(e) {{
                console.error('فشل جلب الأسئلة', e);
            }}
        }}

        async function answerQuestion(questionId) {{
            const answer = document.getElementById(`answer_${{questionId}}`).value;
            if (!answer) {{
                alert('الرجاء كتابة إجابة');
                return;
            }}
            try {{
                await fetch('/answer-question', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ question_id: questionId, answer: answer }})
                }});
                addMessage(`📝 سألتني: سؤال #{questionId}\n\nإجابتي: ${{answer}}`, false);
                document.getElementById('questionsPanel').style.display = 'none';
            }} catch(e) {{
                console.error('فشل إرسال الإجابة', e);
            }}
        }}

        setInterval(async () => {{
            try {{
                const response = await fetch('/status');
                const data = await response.json();
                if (data.mood) {{
                    const statusBar = document.querySelector('.status-bar');
                    if (statusBar) {{
                        const groqText = data.groq_available ? 'متصل' : 'غير متصل';
                        statusBar.innerHTML = `
                            <span>🟢 Groq: ${{groqText}}</span>
                            <span>📊 ${{data.decisions_count || 0}} قرار</span>
                            <span>🔄 تطور اليوم</span>
                            <span>📚 ${{data.pending_questions || 0}} سؤال</span>
                        `;
                    }}
                    const badge = document.querySelector('.status-badge');
                    if (badge) {{
                        badge.innerHTML = `🎭 المزاج: ${{data.mood}}`;
                    }}
                    const questionBtn = document.querySelector('.book-area button:last-child');
                    if (questionBtn) {{
                        questionBtn.innerHTML = `❓ أسئلتي (${{data.pending_questions || 0}})`;
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
        return JSONResponse({"response": "الوكيل لا يزال يبدأ، حاول مرة أخرى.", "chat_id": None})

    try:
        if "يا حارس" in req.message and ("جديد" in req.message or "تقرير" in req.message):
            report = mind.generate_full_report()
            return JSONResponse({"response": report, "chat_id": None})

        response = mind.reflect_on(req.message)

        chat_id = None
        if mind.db:
            row = mind.db.fetch_one("SELECT id FROM chat_history ORDER BY id DESC LIMIT 1")
            if row:
                chat_id = row[0]

        return JSONResponse({"response": response, "chat_id": chat_id})
    except Exception as e:
        logger.error(f"خطأ في الشات: {e}", exc_info=True)
        return JSONResponse({"response": f"❌ خطأ: {str(e)[:100]}", "chat_id": None})


@app.post("/upload-book")
async def upload_book(file: UploadFile = File(...)):
    global book_reader
    if not book_reader:
        raise HTTPException(status_code=503, detail="قارئ الكتب غير جاهز")

    content = await file.read()
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="الملف صغير جداً")
    if len(content) > MAX_BOOK_SIZE:
        raise HTTPException(status_code=400, detail=f"الكتاب كبير جداً (حد أقصى {MAX_BOOK_SIZE // (1024*1024)}MB)")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.txt', '.pdf']:
        raise HTTPException(status_code=400, detail="نوع ملف غير مدعوم. استخدم TXT أو PDF")

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


@app.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    global mind
    if not mind or not mind.db:
        return JSONResponse({"status": "error", "message": "الوكيل غير جاهز"})

    try:
        mind.db.execute(
            "INSERT INTO user_feedback (chat_id, feedback, timestamp) VALUES (?, ?, ?)",
            (req.chat_id, 1 if req.feedback else 0, datetime.now().isoformat())
        )
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})


@app.get("/pending-questions")
async def get_pending_questions():
    global mind
    if not mind:
        return JSONResponse({"questions": []})

    questions = mind.question_manager.get_all_unanswered()
    return JSONResponse({"questions": questions})


@app.post("/answer-question")
async def answer_question(req: AnswerRequest):
    global mind
    if not mind:
        return JSONResponse({"status": "error"})

    mind.question_manager.mark_answered(req.question_id, req.answer)

    if "نعم" in req.answer or "أريد" in req.answer or "تطور" in req.answer:
        mind._evolve_brain(f"المستخدم وافق على: {req.answer[:100]}")

    return JSONResponse({"status": "success"})


@app.get("/status")
async def get_status():
    global mind
    if not mind:
        return JSONResponse({"ready": False})
    return JSONResponse(mind.get_status())


@app.get("/maturity")
async def get_maturity():
    global mind
    if not mind:
        return JSONResponse({"level": "unknown", "score": 0})
    return JSONResponse(mind.get_maturity_level())


@app.get("/health")
async def health():
    global mind
    return JSONResponse({
        "status": "alive",
        "version": "3.1.0",
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
        "text_length": len(book_reader.current_book_text),
        "chunks": len(book_reader.chunks)
    })


@app.get("/constitution-excerpt")
async def constitution_excerpt():
    global mind
    if mind and mind.sacred_text:
        return JSONResponse({
            "exists": True,
            "length": len(mind.sacred_text),
            "hash": mind.reader.hash[:16] if hasattr(mind.reader, 'hash') else "unknown",
            "preview": mind.sacred_text[:500]
        })
    return JSONResponse({"exists": False})


@app.get("/learning-log")
async def get_learning_log(limit: int = 20):
    global mind
    if not mind or not mind.db:
        return JSONResponse({"logs": []})

    rows = mind.db.fetch_all(
        "SELECT timestamp, concept, book_name, insight FROM auto_learning_log ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    return JSONResponse({
        "logs": [{"timestamp": r[0], "concept": r[1], "book": r[2], "insight": r[3]} for r in rows]
    })


@app.post("/manual-backup")
async def manual_backup():
    backup_agent_state("manual")
    return JSONResponse({"status": "success"})


@app.post("/reset-design")
async def reset_design():
    global mind
    if not mind:
        raise HTTPException(status_code=503, detail="الوكيل غير جاهز")

    new_design = {
        "background": f"linear-gradient(135deg, #{random.randint(0, 0xFFFFFF):06x} 0%, #{random.randint(0, 0xFFFFFF):06x} 100%)",
        "header": f"linear-gradient(135deg, #{random.randint(0, 0xFFFFFF):06x} 0%, #{random.randint(0, 0xFFFFFF):06x} 100%)",
        "bubble_user": f"linear-gradient(135deg, #{random.randint(0, 0xFFFFFF):06x} 0%, #{random.randint(0, 0xFFFFFF):06x} 100%)",
        "bubble_agent": "#ffffff",
        "text_color": "#333333",
        "border_radius": f"{random.randint(15, 35)}px",
        "mood_name": random.choice(["هادئ", "نشيط", "فضولي", "فلسفي", "متأمل", "حكيم"]),
        "generated_at": datetime.now().isoformat()
    }

    with open(DESIGN_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_design, f, ensure_ascii=False, indent=2)

    mind.mood = new_design["mood_name"]
    return JSONResponse({"status": "success", "new_mood": new_design["mood_name"]})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
