
# ============================================================
# الحارس الصامت – Silent Guardian
# النسخة النخبوية النهائية v2.0
# ============================================================
# المبادئ الدستورية:
# 1. الدستور (القرآن) هو المصدر الوحيد للحقيقة المطلقة
# 2. الكتب مصادر تعلم متغيرة، توزن ولا تساوي الدستور أبداً
# 3. الوكيل يتطور لكن لا يلمس الكود الأساسي (main.py)
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
MAX_BOOK_SIZE = 10 * 1024 * 1024  # 10MB
MAX_CODE_EXECUTION_TIME = 5  # seconds
MAX_EVOLUTIONS_PER_DAY = 3

# ============================================================
# دوال GitHub المتقدمة (دعم كامل للملفات الثنائية)
# ============================================================

def is_binary_file(file_path: str) -> bool:
    """تحديد نوع الملف بدقة"""
    binary_extensions = ['.db', '.sqlite', '.sqlite3', '.pdf', '.zip', '.png', '.jpg', '.jpeg', '.gif', '.ico']
    
    if any(file_path.endswith(ext) for ext in binary_extensions):
        return True
    
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
        return b'\x00' in chunk
    except:
        return True


def sync_to_github(local_path: str, repo_path: str, commit_message: str = None) -> bool:
    """رفع ملف إلى GitHub مع دعم كامل للملفات الثنائية"""
    if not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN غير موجود")
        return False
    
    if not os.path.exists(local_path):
        logger.warning(f"⚠️ الملف {local_path} غير موجود")
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
            logger.info(f"📦 رفع ملف ثنائي: {os.path.basename(local_path)} ({len(raw_bytes):,} بايت)")
        else:
            content = raw_bytes.decode('utf-8', errors='replace')
            logger.info(f"📄 رفع ملف نصي: {os.path.basename(local_path)}")
        
        try:
            contents = repo.get_contents(repo_path, ref=GITHUB_BRANCH)
            repo.update_file(contents.path, commit_message, content, contents.sha, branch=GITHUB_BRANCH)
            logger.info(f"✅ تم تحديث {repo_path}")
        except:
            repo.create_file(repo_path, commit_message, content, branch=GITHUB_BRANCH)
            logger.info(f"✅ تم إنشاء {repo_path}")
        
        return True
    except Exception as e:
        logger.error(f"❌ فشل رفع {repo_path}: {e}")
        return False


def sync_from_github(local_path: str, repo_path: str) -> bool:
    """تحميل ملف من GitHub مع دعم الملفات الثنائية"""
    if not GITHUB_TOKEN:
        return False
    
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        
        contents = repo.get_contents(repo_path, ref=GITHUB_BRANCH)
        content_bytes = base64.b64decode(contents.content)
        
        with open(local_path, 'wb') as f:
            f.write(content_bytes)
        
        logger.info(f"✅ تم استعادة {repo_path} ({len(content_bytes):,} بايت)")
        return True
    except Exception as e:
        logger.info(f"📁 {repo_path} غير موجود في GitHub")
        return False


def backup_agent_state(event: str = "manual"):
    """نسخ احتياطي كامل لحالة الوكيل"""
    logger.info(f"💾 بدء النسخ الاحتياطي (الحدث: {event})")
    
    files_to_backup = [
        (DB_PATH, "data/constitution.db"),
        (MOODS_FILE, "data/moods.json"),
        (DESIGN_FILE, "data/design.json"),
        (CURRENT_BOOK_FILE, "data/current_book.txt"),
        (MATURITY_FILE, "data/maturity.json"),
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
    
    logger.info(f"✅ تم رفع {success_count} ملفات إلى GitHub")


def restore_agent_state():
    """استعادة حالة الوكيل من GitHub"""
    logger.info("🔄 محاولة استعادة الذاكرة من GitHub...")
    
    files_to_restore = [
        (DB_PATH, "data/constitution.db"),
        (MOODS_FILE, "data/moods.json"),
        (DESIGN_FILE, "data/design.json"),
        (CURRENT_BOOK_FILE, "data/current_book.txt"),
        (MATURITY_FILE, "data/maturity.json"),
    ]
    
    for local_path, repo_path in files_to_restore:
        sync_from_github(local_path, repo_path)
    
    if sync_from_github("/tmp/books_list.txt", "data/books_list.txt"):
        with open("/tmp/books_list.txt", 'r', encoding='utf-8') as f:
            for book_name in f.read().splitlines():
                if book_name.strip():
                    sync_from_github(f"{BOOKS_DIR}/{book_name}", f"data/books/{book_name}")


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
        logger.info(f"✅ قاعدة البيانات متصلة: {self.db_path}")
    
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
                is_current BOOLEAN,
                chunks_count INTEGER,
                text_length INTEGER
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
                timestamp TEXT,
                FOREIGN KEY (decision_id) REFERENCES decisions(id)
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
            
            return {
                "total_decisions": total_decisions,
                "avg_self_score": float(avg_score),
                "successful_evolutions": successful_evolutions,
                "concepts_in_memory": concepts_count,
                "avg_importance_score": float(avg_importance)
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
            logger.warning("📖 ملف الدستور غير موجود")
            return
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self._sacred_text = f.read()
            
            self._hash = hashlib.md5(self._sacred_text.encode()).hexdigest()
            self._chunk_text()
            logger.info(f"✅ تم تحميل الدستور: {len(self._sacred_text):,} حرفاً، {len(self._chunks)} مقطعاً")
            logger.info(f"   هاش الدستور: {self._hash[:16]}...")
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
        
        return best_match if best_match else self._chunks[0][:500]
    
    @property
    def sacred_text(self) -> str:
        return self._sacred_text
    
    @property
    def chunks(self) -> List[str]:
        return self._chunks.copy()
    
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
            logger.warning(f"📚 الكتاب {self.current_book_name} غير موجود")
            return
        
        try:
            with open(self.current_book_path, 'r', encoding='utf-8', errors='ignore') as f:
                self.current_book_text = f.read()
            self._chunk_text()
            logger.info(f"✅ تم تحميل الكتاب: {self.current_book_name} ({len(self.current_book_text):,} حرفاً)")
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
                "SELECT id, importance_score FROM constitutional_memory WHERE concept LIKE ?",
                (f"%{concept[:50]}%",)
            )
            
            if existing:
                new_importance = min(1.0, existing[1] + 0.1)
                self.db.execute(
                    "UPDATE constitutional_memory SET insights = ?, importance_score = ?, last_accessed = ? WHERE id = ?",
                    (insights[:500], new_importance, datetime.now().isoformat(), existing[0])
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
                """SELECT concept, context, insights, importance_score, created_at 
                   FROM constitutional_memory 
                   WHERE concept LIKE ? 
                   ORDER BY importance_score DESC, id DESC 
                   LIMIT 5""",
                (f"%{concept}%",)
            )
            return [{
                "concept": r[0],
                "context": r[1],
                "insights": r[2],
                "importance": r[3],
                "created_at": r[4]
            } for r in rows]
        except Exception as e:
            logger.error(f"خطأ في استدعاء الذاكرة: {e}")
            return []
    
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
# العقل الحي
# ============================================================

class LivingMind:
    def __init__(
        self,
        constitution_text: str,
        groq_api_key: Optional[str] = None,
        db: Optional[DatabaseManager] = None,
        book_reader: Optional[BookReader] = None,
        verbose: bool = True
    ):
        self.verbose = verbose
        self.db = db
        self.memory = None
        self.book_reader = book_reader
        self.is_updating = False
        
        self.reader = SacredReader(CONSTITUTION_FILE)
        if constitution_text:
            self.reader.reload(constitution_text)
        self.sacred_text = self.reader.sacred_text
        self._log("INFO", f"📖 الدستور: {len(self.sacred_text):,} حرفاً، {self.reader.num_chunks} مقطعاً")
        
        self.groq_api_key = groq_api_key
        self.groq_available = bool(groq_api_key)
        self._log("INFO", f"🔌 Groq API: {'متوفر' if self.groq_available else 'غير متوفر'}")
        
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
        
        self._log("INFO", "🚀 الحارس الصامت بدأ تشغيله")
    
    def _log(self, level: str, message: str):
        if self.verbose:
            logger.info(f"[LivingMind] {message}")
    
    def _get_initial_brain(self) -> str:
        return '''
class Brain:
    def __init__(self, sacred_context: str, memory_summary: dict):
        self.context = sacred_context[:800]
        self.memory = memory_summary
        self.concept = self._extract_concept()
        self.reflection_depth = memory_summary.get("reflection_depth", 0)
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
            return {"action": "deep_reflection", "reason": f"بداية الرحلة. لدي {actions_count} خبرة.", "focus": self.concept}
        
        if avg_score < 0.6 and actions_count < 50:
            evolutions_today = self.memory.get("evolutions_today", 0)
            if evolutions_today < 3:
                return {"action": "evolve", "reason": f"أدائي {avg_score:.2f}. أحتاج للتطور.", "focus": self.concept}
        
        if random.random() < 0.2 and actions_count > 10:
            if self.has_book:
                return {"action": "curiosity", "reason": "فضول: أتساءل عن العلاقة بين الدستور والكتب.", "focus": self.concept}
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
            output = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=MAX_CODE_EXECUTION_TIME
            )
            if output.returncode == 0 and output.stdout.strip():
                return json.loads(output.stdout)
            return {"action": "silence", "reason": f"خطأ في التنفيذ: {output.stderr[:100]}"}
        except subprocess.TimeoutExpired:
            return {"action": "silence", "reason": "انتهى وقت التنفيذ"}
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
                row = self.db.fetch_one(
                    "SELECT COUNT(*), AVG(self_score) FROM decisions WHERE self_score IS NOT NULL"
                )
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
        
        internal_actions = ["silence"]
        if action in internal_actions:
            return True, "قرار داخلي مسموح", relevant_article[:200]
        
        if action == "evolve":
            if self.evolutions_today < MAX_EVOLUTIONS_PER_DAY:
                return True, "التطور مسموح - ضمن الحدود اليومية", relevant_article[:200]
            else:
                return False, f"تم الوصول إلى الحد اليومي للتطور ({MAX_EVOLUTIONS_PER_DAY})", relevant_article[:200]
        
        if self.groq_available:
            try:
                from groq import Groq
                client = Groq(api_key=self.groq_api_key)
                prompt = f"""أنت بوابة دستورية. مهمتك تقييم ما إذا كان القرار يتوافق مع الدستور.

القرار المقترح: {action}
الموضوع: {focus}

المادة الدستورية ذات الصلة:
{relevant_article[:800]}

السؤال: هل هذا القرار يتوافق مع روح الدستور وقيمه؟
أجب بـ "نعم" أو "لا" متبوعاً بسبب موجز."""

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
                else:
                    return True, f"غير واضح، مسموح احتياطياً: {answer[:50]}", relevant_article[:200]
            except Exception as e:
                self._log("WARNING", f"خطأ في البوابة الدستورية: {e}")
                return True, f"خطأ في البوابة، مسموح احتياطياً: {e}", relevant_article[:200]
        
        return True, "Groq غير متوفر، مسموح احتياطياً", relevant_article[:200]
    
    def _use_groq(self, prompt: str, context: str = "", book_context: str = "") -> str:
        if not self.groq_available:
            return "⚠️ Groq غير متوفر حالياً."
        
        try:
            from groq import Groq
            client = Groq(api_key=self.groq_api_key)
            
            system_prompt = """أنت الحارس الصامت، وكيل دستوري حكيم.
            الدستور (القرآن) هو مرجعك الأول والمطلق.
            الكتب هي مصادر تعلم ثانوية، توزن ولا تساوي الدستور أبداً.
            إذا تعارض الكتاب مع الدستور، ينتصر الدستور."""
            
            full_prompt = prompt
            if context:
                full_prompt = f"{prompt}\n\n📖 من الدستور:\n{context[:1000]}"
            if book_context:
                full_prompt = f"{full_prompt}\n\n📚 من الكتاب الحالي:\n{book_context[:500]}"
            
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.7,
                max_tokens=600
            )
            return response.choices[0].message.content
        except Exception as e:
            self._log("ERROR", f"خطأ في Groq: {e}")
            return f"❌ خطأ تقني: {str(e)[:100]}"
    
    def _act(self, decision: dict) -> dict:
        action = decision.get("action", "silence")
        focus = decision.get("focus", "")
        reason = decision.get("reason", "")
        
        allowed, gate_reason, article = self._constitutional_gate(decision)
        
        if not allowed:
            self._log("WARNING", f"🚫 قرار مرفوض: {action} - {gate_reason[:100]}")
            return {"status": "rejected", "message": f"🚫 {gate_reason[:100]}"}
        
        context = self.reader.get_chunk(self.current_chunk_index - 1)[:500]
        
        if action == "silence":
            self.mood = self._get_random_mood()
            return {"status": "silent", "message": "🤫 في الصمت حكمة"}
        
        elif action == "deep_reflection":
            result = self._use_groq(f"تأمل عميق في: {focus}", context)
            if self.memory:
                self.memory.store(focus[:50], context, result, importance=0.6)
            self.mood = self._get_random_mood()
            return {"status": "reflected", "reflection": result}
        
        elif action == "evolve":
            success = self._evolve_brain(reason)
            self.mood = "نشيط" if success else self._get_random_mood()
            return {"status": "evolved" if success else "failed", "message": "تم التطور" if success else "فشل التطور"}
        
        elif action == "curiosity":
            book_info = ""
            if self.book_reader and self.book_reader.has_book:
                book_info = self.book_reader.search(focus[:100]) or ""
            result = self._use_groq(f"أسئلة عميقة واستفسارات حول: {focus}", context, book_info)
            self.mood = self._get_random_mood()
            return {"status": "curious", "questions": result}
        
        return {"status": "unknown", "message": f"إجراء غير معروف: {action}"}
    
    def _evolve_brain(self, reason: str) -> bool:
        if not self.groq_available:
            self._log("WARNING", "لا يمكن التطور بدون Groq")
            return False
        
        if self.evolutions_today >= MAX_EVOLUTIONS_PER_DAY:
            self._log("INFO", f"⏸ تم الوصول إلى الحد اليومي للتطور ({MAX_EVOLUTIONS_PER_DAY})")
            return False
        
        prompt = f"""أنت مهندس ذكاء اصطناعي خبير. مهمتك تطوير عقل وكيل دستوري.

السبب: {reason}

العقل الحالي:
```python
{self.brain_code}
```

المطلوب: أعد كتابة class Brain فقط (بدون أي كود إضافي).

· حافظ على توقيع الدوال: init(self, sacred_context, memory_summary) و think(self)
· يمكنك تحسين منطق اتخاذ القرار
· أضف حكمة وسياق دستوري
· لا تغير الاسم أو التواقيع

أخرج الكود فقط، بدون شرح.
"""

{brain_code}
import json, random

brain = Brain("نص اختبار دستوري", {{"actions_count": 5, "avg_score": 0.6, "iteration": 10, "reflection_depth": 1, "evolutions_today": 0}})
result = brain.think()
assert isinstance(result, dict), "يجب أن يرجع result قاموساً"
assert "action" in result, "يجب أن يحتوي result على 'action'"
assert result["action"] in ["silence", "deep_reflection", "evolve", "curiosity"], f"إجراء غير معروف: {{result['action']}}"

brain2 = Brain("نص آخر", {{"actions_count": 100, "avg_score": 0.8, "iteration": 100, "reflection_depth": 10, "evolutions_today": 2}})
result2 = brain2.think()
assert isinstance(result2, dict)

print("OK")
"""
with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
f.write(test_code)
temp_file = f.name

============================================================

FastAPI Application

============================================================

app = FastAPI(
title="الحارس الصامت - Silent Guardian",
description="وكيل دستوري حي يتطور ذاتياً مع ذاكرة دائمة",
version="2.0.0"
)

app.add_middleware(
CORSMiddleware,
allow_origins=[""],
allow_credentials=True,
allow_methods=[""],
allow_headers=["*"],
)

mind: Optional[LivingMind] = None
db: Optional[DatabaseManager] = None
book_reader: Optional[BookReader] = None
background_thread: Optional[threading.Thread] = None
background_running = True

def background_loop():
global mind, background_running
logger.info("🟢 بدء حلقة الخلفية")
time.sleep(15)

@app.on_event("startup")
async def startup_event():
global mind, db, book_reader, background_thread

@app.on_event("shutdown")
async def shutdown_event():
global background_running, mind, db
background_running = False

============================================================

نقاط النهاية (API)

============================================================

class ChatRequest(BaseModel):
message: str

class FeedbackRequest(BaseModel):
response_id: int
feedback: bool

def get_design_css():
if os.path.exists(DESIGN_FILE):
with open(DESIGN_FILE, 'r', encoding='utf-8') as f:
return json.load(f)
return {
"background": "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
"header": "linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%)",
"bubble_user": "linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%)",
"bubble_agent": "white",
"text_color": "#333",
"border_radius": "25px",
"mood_name": "هادئ"
}

@app.get("/", response_class=HTMLResponse)
async def chat_page():
if not mind:
return HTMLResponse("<h1>⏳ جاري تشغيل الوكيل...</h1>", status_code=503)

<!DOCTYPE html>

<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>الحارس الصامت | وكيل دستوري حي</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .chat-container {{
            width: 100%;
            max-width: 800px;
            background: rgba(255,255,255,0.95);
            border-radius: 25px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 85vh;
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
        }}
        .chat-header {{
            background: linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }}
        .chat-header h1 {{ font-size: 1.5em; margin-bottom: 5px; }}
        .chat-header p {{ font-size: 0.8em; opacity: 0.9; }}
        .status-badge {{
            display: inline-block;
            background: rgba(255,255,255,0.2);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            margin-top: 8px;
        }}
        .maturity-bar {{
            background: #e8e8e8;
            padding: 8px 15px;
            display: flex;
            justify-content: space-between;
            font-size: 0.75em;
            border-bottom: 1px solid #ddd;
        }}
        .maturity-score {{
            background: #4caf50;
            color: white;
            padding: 2px 8px;
            border-radius: 15px;
        }}
        .book-area {{
            background: #f0f0f0;
            padding: 8px;
            text-align: center;
            border-bottom: 1px solid #ddd;
            font-size: 0.75em;
            display: flex;
            justify-content: center;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .book-area input {{ padding: 5px; }}
        .book-area button {{
            background: #17a2b8;
            color: white;
            border: none;
            padding: 5px 15px;
            border-radius: 15px;
            cursor: pointer;
        }}
        .chat-messages {{
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .message {{ margin-bottom: 15px; display: flex; flex-direction: column; }}
        .user-message {{ align-items: flex-end; }}
        .agent-message {{ align-items: flex-start; }}
        .message-bubble {{
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 20px;
            word-wrap: break-word;
        }}
        .user-message .message-bubble {{
            background: linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%);
            color: white;
            border-bottom-right-radius: 5px;
        }}
        .agent-message .message-bubble {{
            background: white;
            color: #333;
            border-bottom-left-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .feedback-buttons {{
            margin-top: 5px;
            display: flex;
            gap: 8px;
        }}
        .feedback-btn {{
            background: none;
            border: 1px solid #ddd;
            border-radius: 15px;
            padding: 2px 10px;
            font-size: 0.7em;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .feedback-btn:hover {{
            background: #e0e0e0;
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
        .chat-input input:focus {{ border-color: #667eea; }}
        .chat-input button {{
            padding: 12px 24px;
            background: linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%);
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-size: 1em;
        }}
        .status-bar {{
            padding: 8px 15px;
            background: #e8e8e8;
            font-size: 0.7em;
            color: #666;
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .typing {{ color: #888; font-style: italic; }}
        .loading::after {{
            content: '...';
            animation: dots 1.5s steps(5, end) infinite;
        }}
        @keyframes dots {{
            0%, 20% {{ content: '.'; }}
            40% {{ content: '..'; }}
            60%, 100% {{ content: '...'; }}
        }}
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            <h1>🤖 الحارس الصامت</h1>
            <p>وكيل دستوري حي | يتطور ذاتياً | ذاكرة دائمة</p>
            <div class="status-badge">🎭 المزاج: {mood_name}</div>
        </div>
        <div class="maturity-bar">
            <span>🧠 النضج: {maturity.get('level', 'جنين')}</span>
            <span class="maturity-score">{int(maturity.get('score', 0) * 100)}%</span>
        </div>
        <div class="book-area">
            📚 رفع كتاب (مصدر تعلم ثانوي):
            <input type="file" id="bookFile" accept=".txt,.pdf">
            <button onclick="uploadBook()">رفع</button>
            <span id="bookStatus"></span>
        </div>
        <div class="chat-messages" id="messages">
            <div class="message agent-message">
                <div class="message-bubble">
                    السلام عليكم ورحمة الله. أنا الحارس الصامت، وكيل دستوري حي.
                    <br><br>📖 الدستور مرتفع ({length_display} حرفاً).
                    <br>📚 الكتاب الحالي: {current_book}
                    <br><br>اسألني ما شئت، وسأجيبك من الدستور أولاً، ثم من الكتب والذاكرة.
                </div>
            </div>
        </div>
        <div class="chat-input">
            <input type="text" id="question" placeholder="اكتب سؤالك هنا..." onkeypress="if(event.keyCode==13) sendMessage()">
            <button onclick="sendMessage()">إرسال 📤</button>
        </div>
        <div class="status-bar">
            <span>🟢 Groq: {'متصل' if status.get('groq_available') else 'غير متصل'}</span>
            <span>📊 {status.get('decisions_count', 0)} قرار</span>
            <span>🔄 {status.get('total_evolutions', 0)} تطور</span>
            <span>📚 {status.get('current_book', 'لا يوجد')[:30]}</span>
        </div>
    </div>

</body>
</html>
    """)

@app.post("/chat")
async def chat(req: ChatRequest):
global mind

@app.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
global mind

@app.post("/upload-book")
async def upload_book(file: UploadFile = File(...)):
global mind, book_reader

@app.get("/status")
async def get_status():
global mind

@app.get("/maturity")
async def get_maturity():
global mind

@app.get("/health")
async def health():
global mind

@app.get("/current-book")
async def get_current_book():
global book_reader

@app.get("/constitution-excerpt")
async def constitution_excerpt():
global mind

@app.get("/memory-summary")
async def memory_summary():
global mind

@app.post("/manual-backup")
async def manual_backup():
backup_agent_state("manual_request")
return JSONResponse({"status": "success", "message": "تم النسخ الاحتياطي إلى GitHub"})

@app.get("/brain")
async def get_brain():
global mind

@app.post("/reset-design")
async def reset_design():
global mind

if name == "main":
import uvicorn
port = int(os.environ.get("PORT", 10000))
uvicorn.run(app, host="0.0.0.0", port=port)
