# ============================================================
# المراقب الصامت – النسخة النهائية الكاملة
# ============================================================
# تشمل:
# 1. الكود الأصلي الناجح (الدستور، التطور، البوابة، الذاكرة)
# 2. إخفاء زر الرفع بعد أول رفع ناجح للدستور
# 3. الواجهة المتغيرة حسب مزاج الوكيل (ألوان، أشكال)
# 4. قراءة الكتب كمدخلات إضافية (حتى 1 ميجابايت)
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
import gc
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sqlite3

# ============================================================
# إعداد التسجيل
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# متغيرات البيئة
# ============================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
PERSISTENT_DIR = os.environ.get("PERSISTENT_DIR", "/data")
os.makedirs(PERSISTENT_DIR, exist_ok=True)

CONSTITUTION_FILE = f"{PERSISTENT_DIR}/constitution.txt"
DB_PATH = f"{PERSISTENT_DIR}/constitution.db"
FLAG_FILE = f"{PERSISTENT_DIR}/constitution_uploaded.flag"
DESIGN_FILE = f"{PERSISTENT_DIR}/design.json"
BOOKS_DIR = f"{PERSISTENT_DIR}/books"
CURRENT_BOOK_FILE = f"{PERSISTENT_DIR}/current_book.txt"

os.makedirs(BOOKS_DIR, exist_ok=True)

# ============================================================
# إدارة قاعدة البيانات (المصححة)
# ============================================================

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self._connect()
    
    def _connect(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_tables()
        logger.info(f"✅ قاعدة البيانات متصلة: {self.db_path}")
    
    def _init_tables(self):
        cursor = self.conn.cursor()
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
                gate_reason TEXT
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
                created_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                user_message TEXT,
                agent_response TEXT,
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
        self.conn.commit()
        cursor.close()
    
    def execute(self, query: str, params: tuple = ()):
        cursor = self.conn.cursor()
        try:
            cursor.execute(query, params)
            self.conn.commit()
            return cursor.rowcount
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def fetch_all(self, query: str, params: tuple = ()):
        cursor = self.conn.cursor()
        try:
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            cursor.close()
    
    def fetch_one(self, query: str, params: tuple = ()):
        cursor = self.conn.cursor()
        try:
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            cursor.close()
    
    def close(self):
        if self.conn:
            self.conn.close()


# ============================================================
# قارئ الدستور (الأصلي)
# ============================================================

class SacredReader:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._sacred_text = ""
        self.chunks = []
        self._load()
    
    def _load(self):
        if not self.file_path.exists():
            return
        
        file_size = self.file_path.stat().st_size
        logger.info(f"📖 تحميل الدستور: {file_size:,} بايت")
        
        if file_size > 1024 * 1024:
            self._load_large_file()
        else:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self._sacred_text = f.read()
            self._chunk_text()
        
        logger.info(f"✅ تم تحميل الدستور: {len(self._sacred_text):,} حرفاً، {len(self.chunks)} مقطعاً")
    
    def _load_large_file(self):
        self._sacred_text = ""
        current_chunk = ""
        
        with open(self.file_path, 'r', encoding='utf-8') as f:
            while True:
                data = f.read(8192)
                if not data:
                    break
                self._sacred_text += data
                current_chunk += data
                
                if len(current_chunk) > 50000:
                    self.chunks.append(current_chunk)
                    current_chunk = ""
                    gc.collect()
        
        if current_chunk:
            self.chunks.append(current_chunk)
    
    def _chunk_text(self, chunk_size: int = 500):
        if not self._sacred_text:
            return
        words = self._sacred_text.split()
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size])
            self.chunks.append(chunk)
    
    def get_chunk(self, index: int) -> str:
        if not self.chunks:
            return ""
        return self.chunks[index % len(self.chunks)]
    
    def find_article(self, keyword: str) -> Optional[str]:
        if not self.chunks:
            return None
        for chunk in self.chunks:
            if keyword in chunk:
                return chunk[:500]
        return None
    
    @property
    def sacred_text(self) -> str:
        return self._sacred_text
    
    @property
    def num_chunks(self) -> int:
        return len(self.chunks)
    
    def reload(self, new_text: str):
        self._sacred_text = new_text
        self.chunks = []
        self._chunk_text()


# ============================================================
# قارئ الكتب (جديد – مدخلات إضافية)
# ============================================================

class BookReader:
    def __init__(self, books_dir: str):
        self.books_dir = Path(books_dir)
        self.current_book_text = ""
        self.current_book_name = ""
        self.chunks = []
        self._load_current_book()
    
    def _load_current_book(self):
        current_book_path = Path(CURRENT_BOOK_FILE)
        if current_book_path.exists():
            with open(current_book_path, 'r', encoding='utf-8') as f:
                self.current_book_name = f.read().strip()
            
            book_file = self.books_dir / self.current_book_name
            if book_file.exists():
                with open(book_file, 'r', encoding='utf-8') as f:
                    self.current_book_text = f.read()
                self._chunk_text()
                logger.info(f"📚 تم تحميل الكتاب الحالي: {self.current_book_name} ({len(self.current_book_text):,} حرفاً)")
    
    def _chunk_text(self, chunk_size: int = 500):
        if not self.current_book_text:
            return
        words = self.current_book_text.split()
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size])
            self.chunks.append(chunk)
    
    def search(self, keyword: str) -> Optional[str]:
        if not self.chunks:
            return None
        for chunk in self.chunks:
            if keyword in chunk:
                return chunk[:500]
        return None
    
    def load_book(self, filename: str, content: bytes):
        file_path = self.books_dir / filename
        with open(file_path, 'wb') as f:
            f.write(content)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            self.current_book_text = f.read()
        self.current_book_name = filename
        self.chunks = []
        self._chunk_text()
        
        with open(CURRENT_BOOK_FILE, 'w', encoding='utf-8') as f:
            f.write(filename)
        
        logger.info(f"✅ تم تحميل كتاب جديد: {filename} ({len(self.current_book_text):,} حرفاً)")
        return True
    
    def get_current_book(self) -> str:
        return self.current_book_name if self.current_book_name else "لا يوجد كتاب مفتوح"
    
    @property
    def has_book(self) -> bool:
        return bool(self.current_book_text)


# ============================================================
# الذاكرة الدستورية (الأصلية)
# ============================================================

class ConstitutionalMemory:
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    def store(self, concept: str, context: str, insights: str):
        try:
            self.db.execute(
                "INSERT INTO constitutional_memory (concept, context, insights, related_concepts, created_at) VALUES (?, ?, ?, ?, ?)",
                (concept[:100], context[:500], insights[:500], "[]", datetime.now().isoformat())
            )
        except Exception as e:
            logger.error(f"خطأ في تخزين الذاكرة: {e}")
    
    def recall(self, concept: str) -> List[Dict]:
        try:
            rows = self.db.fetch_all(
                "SELECT context, insights, created_at FROM constitutional_memory WHERE concept LIKE ? ORDER BY id DESC LIMIT 5",
                (f"%{concept}%",)
            )
            return [{"context": r[0], "insights": r[1], "created_at": r[2]} for r in rows]
        except Exception as e:
            logger.error(f"خطأ في استدعاء الذاكرة: {e}")
            return []
    
    def get_summary(self) -> str:
        try:
            row = self.db.fetch_one("SELECT COUNT(*) FROM constitutional_memory")
            count = row[0] if row else 0
            if count == 0:
                return "الذاكرة فارغة."
            rows = self.db.fetch_all("SELECT concept FROM constitutional_memory ORDER BY id DESC LIMIT 5")
            recent = [r[0] for r in rows]
            return f"{count} مفهوماً. آخرها: {', '.join(recent)}"
        except:
            return "الذاكرة غير متاحة"


# ============================================================
# العقل الحي (الأصلي + إدارة المزاج للواجهة)
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
        
        # قارئ الدستور
        self.reader = SacredReader(CONSTITUTION_FILE)
        if constitution_text:
            self.reader.reload(constitution_text)
        self.sacred_text = self.reader.sacred_text
        self._log("INFO", f"تم قراءة الدستور: {len(self.sacred_text):,} حرفاً، {self.reader.num_chunks} مقطعاً")
        
        # Groq
        self.groq_api_key = groq_api_key
        self.groq_available = bool(groq_api_key)
        self._log("INFO", f"Groq API: {'متوفر' if self.groq_available else 'غير متوفر'}")
        
        # العقل
        self.brain_code = self._get_initial_brain()
        
        # الحالة
        self.is_alive = True
        self.iteration = 0
        self.start_time = datetime.now()
        self.current_chunk_index = 0
        self.evolutions_today = 0
        self.last_evolution_day = datetime.now().date()
        self.mood = "فضولي"  # يتغير بناءً على القرارات
        self._lock = threading.Lock()
        
        self._log("INFO", "🚀 العقل الحي بدأ تشغيله")
    
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
    
    def _extract_concept(self) -> str:
        words = self.context.split()[:20]
        return " ".join(words) if words else "العدل"
    
    def think(self) -> dict:
        actions_count = self.memory.get("actions_count", 0)
        avg_score = self.memory.get("avg_score", 0.5)
        
        if actions_count > 50:
            if random.random() < 0.7:
                return {"action": "silence", "reason": "في الصمت حكمة.", "focus": self.concept}
        
        if actions_count < 5:
            return {"action": "deep_reflection", "reason": f"جديد. لدي {actions_count} خبرة.", "focus": self.concept}
        
        if avg_score < 0.6 and actions_count < 30:
            evolutions_today = self.memory.get("evolutions_today", 0)
            if evolutions_today < 3:
                return {"action": "evolve", "reason": f"أدائي {avg_score:.2f}. أحتاج للتطور.", "focus": self.concept}
        
        if random.random() < 0.15 and actions_count > 10:
            return {"action": "curiosity", "reason": "فضول متواضع.", "focus": self.concept}
        
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py') as f:
            f.write(full_code)
            f.flush()
            try:
                output = subprocess.run(
                    [sys.executable, f.name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if output.returncode == 0 and output.stdout.strip():
                    return json.loads(output.stdout)
                return {"action": "silence", "reason": f"خطأ: {output.stderr[:100]}"}
            except Exception as e:
                return {"action": "silence", "reason": f"استثناء: {str(e)[:100]}"}
    
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
            "evolutions_today": self.evolutions_today
        }
    
    def _constitutional_gate(self, decision: dict) -> Tuple[bool, str, str]:
        action = decision.get("action", "silence")
        focus = decision.get("focus", "")
        
        relevant_article = self.reader.find_article(focus[:50]) if focus else None
        if not relevant_article:
            relevant_article = self.reader.get_chunk(self.current_chunk_index - 1)[:500]
        
        always_allowed = ["silence", "evolve"]
        if action in always_allowed:
            return True, "قرار داخلي مسموح", relevant_article
        
        if self.groq_available:
            try:
                from groq import Groq
                client = Groq(api_key=self.groq_api_key)
                prompt = f"""
القرار: {action}
التركيز: {focus}

المادة الدستورية:
{relevant_article}

هل هذا القرار يتوافق مع روح المادة؟ أجب بـ "نعم" أو "لا" مع سبب موجز.
"""
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=200
                )
                answer = response.choices[0].message.content
                
                if "نعم" in answer[:10]:
                    return True, answer, relevant_article[:200]
                elif "لا" in answer[:10]:
                    return False, answer, relevant_article[:200]
                else:
                    return True, f"غير واضح: {answer[:50]}", relevant_article[:200]
            except Exception as e:
                self._log("WARNING", f"خطأ في البوابة: {e}")
                return True, f"خطأ: {e}", relevant_article[:200]
        
        return True, "قواعد بسيطة: مسموح", relevant_article[:200]
    
    def _use_groq(self, prompt: str, context: str = "", book_context: str = "") -> str:
        if not self.groq_available:
            return "[Groq غير متوفر]"
        
        try:
            from groq import Groq
            client = Groq(api_key=self.groq_api_key)
            
            full_prompt = prompt
            if context:
                full_prompt = f"{prompt}\n\nالنص الدستوري:\n{context[:1000]}"
            if book_context:
                full_prompt = f"{full_prompt}\n\nمن الكتاب الحالي:\n{book_context[:500]}"
            
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "أنت عقل دستوري حكيم. الدستور هو مرجعك الأول. الكتاب مجرد مدخل إضافي."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content
        except Exception as e:
            self._log("ERROR", f"خطأ في Groq: {e}")
            return f"[خطأ: {str(e)}]"
    
    def _act(self, decision: dict) -> dict:
        action = decision.get("action", "silence")
        focus = decision.get("focus", "")
        
        allowed, gate_reason, article = self._constitutional_gate(decision)
        
        if not allowed:
            return {"status": "rejected", "message": f"🚫 {gate_reason[:100]}"}
        
        context = self.reader.get_chunk(self.current_chunk_index - 1)[:500]
        
        if action == "silence":
            self.mood = "هادئ"
            return {"status": "silent", "message": "🤫 صامت"}
        
        elif action == "deep_reflection":
            result = self._use_groq(f"تأمل عميق في: {focus}", context)
            if self.memory:
                self.memory.store(focus[:50], context, result)
            self.mood = "فلسفي"
            return {"status": "reflected", "reflection": result}
        
        elif action == "evolve":
            success = self._evolve_brain(decision.get("reason", "تحسين"))
            self.mood = "نشيط" if success else "محبط"
            return {"status": "evolved" if success else "failed"}
        
        elif action == "curiosity":
            book_info = ""
            if self.book_reader and self.book_reader.has_book:
                book_info = self.book_reader.search(focus[:50]) or ""
            result = self._use_groq(f"أسئلة عميقة حول: {focus}", context, book_info)
            self.mood = "فضولي"
            return {"status": "curious", "questions": result}
        
        return {"status": "unknown"}
    
    def _evolve_brain(self, reason: str) -> bool:
        if not self.groq_available:
            return False
        
        if self.evolutions_today >= 3:
            self._log("INFO", "⏸ حد 3 تطورات يومياً")
            return False
        
        prompt = f"""
أطور عقلي. السبب: {reason}

العقل الحالي:
{self.brain_code}

أعد كتابة class Brain فقط (__init__, think). حافظ على التواقيع.
"""
        
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
                    try:
                        self.db.execute(
                            "INSERT INTO evolutions (timestamp, reason, old_brain_hash, new_brain_hash, success) VALUES (?, ?, ?, ?, ?)",
                            (datetime.now().isoformat(), reason[:200], "old", "new", True)
                        )
                    except Exception as e:
                        logger.warning(f"لم يسجل التطور: {e}")
                
                self._log("INFO", "✅ تطور ناجح!")
                return True
            else:
                self._log("WARNING", "❌ فشل اختبار العقل الجديد")
                return False
        except Exception as e:
            self._log("ERROR", f"❌ خطأ في التطور: {e}")
            return False
    
    def _test_brain(self, brain_code: str) -> bool:
        test_code = f"""
{brain_code}
brain = Brain("نص اختبار", {{"actions_count": 5, "avg_score": 0.6}})
result = brain.think()
assert isinstance(result, dict)
assert "action" in result
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py') as f:
            f.write(test_code)
            f.flush()
            try:
                subprocess.run([sys.executable, f.name], timeout=5, check=True, capture_output=True)
                return True
            except Exception:
                return False
    
    def _self_evaluate(self, decision: dict, result: dict, gate_passed: bool) -> float:
        action = decision.get("action", "silence")
        score = 0.0
        criteria = 0
        
        if gate_passed:
            score += 0.3
            criteria += 1
        else:
            return 0.0
        
        if action in ["deep_reflection", "curiosity"]:
            output = result.get("reflection") or result.get("questions") or ""
            if len(output) > 50 and self.db:
                try:
                    row = self.db.fetch_one(
                        "SELECT COUNT(*) FROM decisions WHERE reflection LIKE ? AND iteration < ?",
                        (f"%{output[:50]}%", self.iteration)
                    )
                    duplicate_count = row[0] if row else 0
                    if duplicate_count == 0:
                        score += 0.3
                    else:
                        score += 0.1
                    criteria += 1
                except Exception:
                    score += 0.2
                    criteria += 1
        
        actions_count = self._get_memory_summary().get("actions_count", 0)
        
        if action == "silence":
            if actions_count > 30:
                score += 0.2
            else:
                score += 0.05
            criteria += 1
        elif action in ["deep_reflection", "curiosity"] and actions_count > 5:
            score += 0.2
            criteria += 1
        elif action == "evolve":
            if self.evolutions_today <= 2:
                score += 0.15
                criteria += 1
            else:
                score -= 0.1
        
        if action == "evolve" and result.get("status") == "evolved":
            score += 0.2
            criteria += 1
        elif action == "deep_reflection" and len(result.get("reflection", "")) > 200:
            score += 0.15
            criteria += 1
        elif action == "curiosity" and len(result.get("questions", "")) > 100:
            score += 0.1
            criteria += 1
        
        if criteria > 0:
            return max(0.0, min(1.0, score / criteria))
        return 0.3
    
    def _save_decision(self, action: str, focus: str, context: str, reflection: str,
                       score: float, gate_passed: bool, gate_reason: str):
        if not self.db:
            return
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
            action = decision.get("action", "silence")
            focus = decision.get("focus", "")
            
            allowed, gate_reason, article = self._constitutional_gate(decision)
            result = self._act(decision)
            score = self._self_evaluate(decision, result, allowed)
            
            context = self.reader.get_chunk(self.current_chunk_index - 1)[:300]
            reflection = result.get("reflection", result.get("questions", ""))
            
            self._save_decision(action, focus, context, reflection, score, allowed, gate_reason)
            
            return {
                "iteration": self.iteration,
                "action": action,
                "score": score,
                "gate_passed": allowed
            }
    
    def reflect_on(self, text: str) -> str:
        if not self.sacred_text:
            return "⚠️ لم يتم رفع دستور بعد. يرجى رفع الدستور أولاً."
        
        context = self.reader.find_article(text[:50]) or self.reader.get_chunk(self.current_chunk_index)[:500]
        
        book_info = ""
        if self.book_reader and self.book_reader.has_book:
            book_info = self.book_reader.search(text[:50]) or ""
            if book_info:
                self._log("INFO", f"📚 تم الاستعانة بالكتاب الحالي: {self.book_reader.get_current_book()}")
        
        result = self._use_groq(f"أجب على هذا السؤال: {text}", context, book_info)
        
        if self.memory:
            self.memory.store(text[:50], context, result)
        
        if self.db:
            try:
                self.db.execute(
                    "INSERT INTO chat_history (session_id, user_message, agent_response, timestamp) VALUES (?, ?, ?, ?)",
                    ("default", text[:500], result[:500], datetime.now().isoformat())
                )
            except Exception as e:
                logger.warning(f"فشل حفظ المحادثة: {e}")
        
        return result
    
    def update_constitution(self, new_text: str):
        if self.is_updating:
            self._log("WARNING", "تحديث الدستور قيد التشغيل بالفعل")
            return
        
        self.is_updating = True
        self._log("INFO", f"بدء تحديث الدستور: {len(new_text):,} حرفاً")
        
        def _update():
            try:
                with open(CONSTITUTION_FILE, 'w', encoding='utf-8') as f:
                    chunk_size = 8192
                    for i in range(0, len(new_text), chunk_size):
                        f.write(new_text[i:i+chunk_size])
                
                self.reader.reload(new_text)
                self.sacred_text = new_text
                
                self._log("INFO", f"✅ تم تحديث الدستور: {len(self.sacred_text):,} حرفاً")
            except Exception as e:
                self._log("ERROR", f"فشل تحديث الدستور: {e}", exc_info=True)
            finally:
                self.is_updating = False
        
        thread = threading.Thread(target=_update)
        thread.daemon = True
        thread.start()
    
    def get_design_suggestion(self) -> dict:
        """اقتراح تصميم الواجهة بناءً على المزاج الحالي"""
        mood_styles = {
            "هادئ": {
                "background": "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
                "header": "linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%)",
                "bubble_user": "linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%)",
                "bubble_agent": "white",
                "text_color": "#333",
                "theme": "داكن هادئ"
            },
            "نشيط": {
                "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                "header": "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)",
                "bubble_user": "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)",
                "bubble_agent": "white",
                "text_color": "#333",
                "theme": "زاهي نشيط"
            },
            "فضولي": {
                "background": "linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%)",
                "header": "linear-gradient(135deg, #11998e 0%, #38ef7d 100%)",
                "bubble_user": "linear-gradient(135deg, #11998e 0%, #38ef7d 100%)",
                "bubble_agent": "white",
                "text_color": "#333",
                "theme": "منعش فضولي"
            },
            "فلسفي": {
                "background": "linear-gradient(135deg, #3a1c71 0%, #d76d77 0%, #ffaf7b 100%)",
                "header": "linear-gradient(135deg, #4b6cb7 0%, #182848 100%)",
                "bubble_user": "linear-gradient(135deg, #4b6cb7 0%, #182848 100%)",
                "bubble_agent": "#f0e6d3",
                "text_color": "#4a3728",
                "theme": "عميق فلسفي"
            },
            "محبط": {
                "background": "linear-gradient(135deg, #4b6cb7 0%, #182848 100%)",
                "header": "linear-gradient(135deg, #2c3e50 0%, #1a1a2e 100%)",
                "bubble_user": "linear-gradient(135deg, #5a5a5a 0%, #3a3a3a 100%)",
                "bubble_agent": "#e0e0e0",
                "text_color": "#555",
                "theme": "هادئ متواضع"
            }
        }
        
        style = mood_styles.get(self.mood, mood_styles["فضولي"])
        style["mood"] = self.mood
        style["updated_at"] = datetime.now().isoformat()
        
        # حفظ في ملف التصميم
        with open(DESIGN_FILE, 'w', encoding='utf-8') as f:
            json.dump(style, f, ensure_ascii=False, indent=2)
        
        return style
    
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
                "is_updating": self.is_updating,
                "mood": self.mood,
                "current_book": self.book_reader.get_current_book() if self.book_reader else "لا يوجد"
            }
    
    def close(self):
        self.is_alive = False


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(title="المراقب الصامت")

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
    logger.info("🟢 بدء حلقة الخلفية (بعد انتظار 10 ثوانٍ)")
    time.sleep(10)
    
    while background_running and mind:
        try:
            result = mind.live_step()
            if result and result["iteration"] % 10 == 0:
                logger.info(f"📊 الخلفية: {result['iteration']}, {result['action']}, {result['score']:.2f}, مزاج: {mind.mood}")
            time.sleep(random.uniform(60, 120))
        except Exception as e:
            logger.error(f"خطأ في حلقة الخلفية: {e}", exc_info=True)
            time.sleep(60)
    
    logger.info("🔴 توقفت حلقة الخلفية")

@app.on_event("startup")
async def startup_event():
    global mind, db, book_reader, background_thread
    
    logger.info("=" * 60)
    logger.info("🚀 تشغيل المراقب الصامت – النسخة النهائية الكاملة")
    logger.info("=" * 60)
    
    try:
        db = DatabaseManager(DB_PATH)
        logger.info("✅ قاعدة البيانات جاهزة")
    except Exception as e:
        logger.error(f"❌ فشل قاعدة البيانات: {e}")
        return
    
    # تحميل الكتب
    book_reader = BookReader(BOOKS_DIR)
    logger.info(f"✅ قارئ الكتب جاهز. الكتاب الحالي: {book_reader.get_current_book()}")
    
    memory = ConstitutionalMemory(db)
    
    constitution_text = ""
    if os.path.exists(CONSTITUTION_FILE):
        try:
            with open(CONSTITUTION_FILE, 'r', encoding='utf-8') as f:
                constitution_text = f.read()
            logger.info(f"✅ تم تحميل الدستور المحفوظ: {len(constitution_text):,} حرفاً")
        except Exception as e:
            logger.error(f"❌ فشل تحميل الدستور المحفوظ: {e}")
    
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
    
    if GROQ_API_KEY:
        try:
            test_response = mind._use_groq("قل فقط: 'Groq يعمل'", "")
            logger.info(f"✅ اختبار Groq: {test_response[:50]}")
        except Exception as e:
            logger.error(f"❌ فشل اختبار Groq: {e}")
    
    background_thread = threading.Thread(target=background_loop, daemon=True)
    background_thread.start()
    logger.info("✅ حلقة الخلفية قيد التشغيل")

@app.on_event("shutdown")
async def shutdown_event():
    global background_running, mind, db
    background_running = False
    if mind:
        mind.close()
    if db:
        db.close()
    logger.info("🛑 إيقاف المراقب الصامت")

# ============================================================
# نقاط النهاية (API)
# ============================================================

class ChatRequest(BaseModel):
    message: str

def get_design_css():
    """قراءة التصميم الحالي من الملف"""
    if os.path.exists(DESIGN_FILE):
        with open(DESIGN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "background": "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
        "header": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        "bubble_user": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        "bubble_agent": "white",
        "text_color": "#333",
        "theme": "داكن",
        "mood": "فضولي"
    }

@app.get("/", response_class=HTMLResponse)
async def chat_page():
    constitution_uploaded = os.path.exists(FLAG_FILE)
    constitution_status = "مرتفع" if (mind and mind.sacred_text) else "غير مرتفع"
    length = len(mind.sacred_text) if (mind and mind.sacred_text) else 0
    length_display = f"{length:,}" if length > 0 else "0"
    
    # تحديث التصميم بناءً على مزاج الوكيل
    if mind:
        mind.get_design_suggestion()
    
    design = get_design_css()
    
    return HTMLResponse(f"""
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>المراقب الصامت</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: {design['background']};
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
            transition: all 0.5s ease;
        }}
        .chat-container {{
            width: 100%;
            max-width: 800px;
            background: rgba(255,255,255,0.95);
            border-radius: 25px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 85vh;
        }}
        .chat-header {{
            background: {design['header']};
            color: white;
            padding: 20px;
            text-align: center;
            transition: all 0.5s ease;
        }}
        .chat-header h1 {{ font-size: 1.5em; margin-bottom: 5px; }}
        .chat-header p {{ font-size: 0.8em; opacity: 0.9; }}
        .upload-area {{
            background: #f0f0f0;
            padding: 10px;
            text-align: center;
            border-bottom: 1px solid #ddd;
            font-size: 0.8em;
            display: {'none' if constitution_uploaded else 'flex'};
            justify-content: center;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .upload-area input {{ padding: 5px; }}
        .upload-area button {{
            background: #28a745;
            color: white;
            border: none;
            padding: 5px 15px;
            border-radius: 15px;
            cursor: pointer;
        }}
        .book-area {{
            background: #e8e8e8;
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
            background: {design['header']};
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-size: 1em;
        }}
        .status-bar {{
            padding: 8px 20px;
            background: #e8e8e8;
            font-size: 0.7em;
            color: #666;
            text-align: center;
        }}
        .typing {{ color: #888; font-style: italic; }}
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            <h1>🤖 المراقب الصامت</h1>
            <p>وكيل دستوري حي | يتطور ذاتياً | مزاج: {design.get('mood', 'فضولي')}</p>
        </div>
        <div class="upload-area" id="upload-area">
            📁 رفع الدستور (مرة واحدة فقط):
            <input type="file" id="constitutionFile" accept=".txt,.pdf">
            <button onclick="uploadConstitution()">رفع</button>
            <span id="uploadStatus"></span>
        </div>
        <div class="book-area">
            📚 رفع كتاب (مدخل إضافي):
            <input type="file" id="bookFile" accept=".txt,.pdf">
            <button onclick="uploadBook()">رفع</button>
            <span id="bookStatus"></span>
        </div>
        <div class="chat-messages" id="messages">
            <div class="message agent-message">
                <div class="message-bubble">
                    السلام عليكم. {'الدستور مرتفع (' + length_display + ' حرفاً). مزاجي: ' + design.get('mood', 'فضولي') + '. اسألني ما شئت.' if constitution_status == 'مرتفع' else 'يرجى رفع الدستور أولاً.'}
                </div>
            </div>
        </div>
        <div class="chat-input">
            <input type="text" id="question" placeholder="اكتب سؤالك هنا..." onkeypress="if(event.keyCode==13) sendMessage()">
            <button onclick="sendMessage()">إرسال</button>
        </div>
        <div class="status-bar" id="status">
            🟢 جاهز | Groq: {'متصل' if GROQ_API_KEY else 'غير متصل'} | مزاج: {design.get('mood', 'فضولي')} | كتاب: {mind.book_reader.get_current_book() if mind and mind.book_reader else 'لا يوجد'}
        </div>
    </div>
    <script>
        async function uploadConstitution() {{
            const fileInput = document.getElementById('constitutionFile');
            const file = fileInput.files[0];
            if (!file) {{ alert('الرجاء اختيار ملف أولاً'); return; }}
            const formData = new FormData();
            formData.append('file', file);
            document.getElementById('uploadStatus').innerText = 'جاري الرفع...';
            try {{
                const response = await fetch('/upload', {{ method: 'POST', body: formData }});
                const data = await response.json();
                if (data.status === 'success') {{
                    document.getElementById('uploadStatus').innerHTML = '✅ تم رفع: ' + data.filename;
                    document.getElementById('upload-area').style.display = 'none';
                    setTimeout(() => location.reload(), 2000);
                }} else {{
                    document.getElementById('uploadStatus').innerHTML = '❌ فشل الرفع: ' + (data.error || 'خطأ');
                }}
            }} catch(e) {{
                document.getElementById('uploadStatus').innerHTML = '❌ خطأ في الاتصال';
            }}
        }}

        async function uploadBook() {{
            const fileInput = document.getElementById('bookFile');
            const file = fileInput.files[0];
            if (!file) {{ alert('الرجاء اختيار ملف أولاً'); return; }}
            const formData = new FormData();
            formData.append('file', file);
            document.getElementById('bookStatus').innerText = 'جاري الرفع...';
            try {{
                const response = await fetch('/upload-book', {{ method: 'POST', body: formData }});
                const data = await response.json();
                if (data.status === 'success') {{
                    document.getElementById('bookStatus').innerHTML = '✅ تم رفع: ' + data.filename;
                    setTimeout(() => location.reload(), 1000);
                }} else {{
                    document.getElementById('bookStatus').innerHTML = '❌ فشل الرفع: ' + (data.error || 'خطأ');
                }}
            }} catch(e) {{
                document.getElementById('bookStatus').innerHTML = '❌ خطأ في الاتصال';
            }}
        }}

        const messagesDiv = document.getElementById('messages');
        const questionInput = document.getElementById('question');
        const statusDiv = document.getElementById('status');

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
            typingDiv.innerHTML = '<div class="message-bubble typing">يكتب...</div>';
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
            statusDiv.innerHTML = '🤔 الوكيل يفكر...';
            try {{
                const response = await fetch('/chat', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ message: question }})
                }});
                const data = await response.json();
                hideTyping();
                addMessage(data.response, false);
                statusDiv.innerHTML = '🟢 جاهز';
            }} catch (error) {{
                hideTyping();
                addMessage('عذراً، حدث خطأ. حاول مرة أخرى.', false);
                statusDiv.innerHTML = '🔴 خطأ';
            }}
        }}

        // تحديث التصميم كل 30 ثانية (للتغييرات التلقائية)
        async function updateDesign() {{
            try {{
                const response = await fetch('/status');
                const data = await response.json();
                if (data.mood) {{
                    statusDiv.innerHTML = `🟢 جاهز | Groq: متصل | مزاج: ${{data.mood}} | كتاب: ${{data.current_book || 'لا يوجد'}}`;
                }}
            }} catch(e) {{}}
        }}
        setInterval(updateDesign, 30000);
    </script>
</body>
</html>
    """)

@app.post("/chat")
async def chat(req: ChatRequest):
    global mind
    if not mind:
        return JSONResponse({"response": "⚠️ الوكيل لا يزال يبدأ. حاول مرة أخرى خلال دقيقة."})
    
    if not mind.sacred_text:
        return JSONResponse({"response": "⚠️ يرجى رفع الدستور أولاً عبر زر 'رفع' في الأعلى."})
    
    try:
        logger.info(f"📨 سؤال: {req.message[:50]}...")
        response = mind.reflect_on(req.message)
        logger.info(f"✅ تم الرد: {response[:50]}...")
        return JSONResponse({"response": response})
    except Exception as e:
        logger.error(f"❌ خطأ في الشات: {e}", exc_info=True)
        return JSONResponse({"response": f"❌ خطأ: {str(e)[:100]}"})

@app.post("/upload")
async def upload_constitution(file: UploadFile = File(...)):
    global mind
    
    # التحقق من أن الدستور لم يُرفع من قبل
    if os.path.exists(FLAG_FILE):
        return JSONResponse({"error": "تم رفع الدستور بالفعل. لا يمكن تغييره."}, status_code=403)
    
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        return JSONResponse({"error": "الملف كبير جداً (حد أقصى 10MB)"}, status_code=400)
    
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.txt', '.pdf']:
        return JSONResponse({"error": "نوع ملف غير مدعوم"}, status_code=400)
    
    temp_id = str(uuid.uuid4())[:8]
    tmp_path = f"/tmp/constitution_{temp_id}{ext}"
    
    with open(tmp_path, 'wb') as f:
        f.write(content)
    
    try:
        if ext == '.pdf':
            try:
                from pypdf import PdfReader
                reader = PdfReader(tmp_path)
                text_parts = []
                for page_num, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    text_parts.append(page_text)
                    if page_num % 10 == 0:
                        gc.collect()
                text = "\n".join(text_parts)
            except ImportError:
                return JSONResponse({"error": "مكتبة PDF غير متوفرة"}, status_code=500)
        else:
            with open(tmp_path, 'r', encoding='utf-8') as f:
                text = f.read()
        
        with open(CONSTITUTION_FILE, 'w', encoding='utf-8') as f:
            chunk_size = 8192
            for i in range(0, len(text), chunk_size):
                f.write(text[i:i+chunk_size])
        
        with open(FLAG_FILE, 'w') as f:
            f.write(datetime.now().isoformat())
        
        if mind:
            def update():
                try:
                    mind.update_constitution(text)
                    logger.info("✅ تم تحديث الدستور في الوكيل")
                except Exception as e:
                    logger.error(f"فشل تحديث الدستور في الوكيل: {e}", exc_info=True)
            
            thread = threading.Thread(target=update)
            thread.daemon = True
            thread.start()
        
        os.unlink(tmp_path)
        
        logger.info(f"✅ تم رفع دستور جديد: {file.filename} ({len(text):,} حرفاً)")
        return JSONResponse({
            "status": "success",
            "filename": file.filename,
            "characters": len(text),
            "message": "تم الرفع بنجاح. جاري تحميل الدستور في الخلفية."
        })
        
    except Exception as e:
        logger.error(f"فشل رفع الدستور: {e}", exc_info=True)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return JSONResponse({"error": str(e)[:200]}, status_code=500)

@app.post("/upload-book")
async def upload_book(file: UploadFile = File(...)):
    global mind, book_reader
    
    content = await file.read()
    if len(content) > 1 * 1024 * 1024:
        return JSONResponse({"error": "الكتاب كبير جداً (حد أقصى 1MB حالياً)"}, status_code=400)
    
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.txt', '.pdf']:
        return JSONResponse({"error": "نوع ملف غير مدعوم"}, status_code=400)
    
    temp_id = str(uuid.uuid4())[:8]
    tmp_path = f"/tmp/book_{temp_id}{ext}"
    
    with open(tmp_path, 'wb') as f:
        f.write(content)
    
    try:
        if ext == '.pdf':
            try:
                from pypdf import PdfReader
                reader = PdfReader(tmp_path)
                text_parts = []
                for page in reader.pages:
                    text_parts.append(page.extract_text())
                text = "\n".join(text_parts)
            except ImportError:
                return JSONResponse({"error": "مكتبة PDF غير متوفرة"}, status_code=500)
        else:
            with open(tmp_path, 'r', encoding='utf-8') as f:
                text = f.read()
        
        if book_reader:
            book_reader.load_book(file.filename, content)
        
        os.unlink(tmp_path)
        
        logger.info(f"✅ تم رفع كتاب جديد: {file.filename} ({len(text):,} حرفاً)")
        return JSONResponse({
            "status": "success",
            "filename": file.filename,
            "characters": len(text)
        })
        
    except Exception as e:
        logger.error(f"فشل رفع الكتاب: {e}", exc_info=True)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return JSONResponse({"error": str(e)[:200]}, status_code=500)

@app.get("/health")
async def health():
    return JSONResponse({
        "status": "alive",
        "timestamp": datetime.now().isoformat(),
        "constitution_loaded": bool(mind and mind.sacred_text) if mind else False,
        "constitution_uploaded": os.path.exists(FLAG_FILE),
        "groq_configured": bool(GROQ_API_KEY),
        "mood": mind.mood if mind else "unknown",
        "current_book": mind.book_reader.get_current_book() if (mind and mind.book_reader) else "none"
    })

@app.get("/status")
async def get_status():
    global mind
    if not mind:
        return JSONResponse({"ready": False})
    try:
        return JSONResponse(mind.get_status())
    except Exception as e:
        logger.error(f"خطأ في /status: {e}", exc_info=True)
        return JSONResponse({"error": str(e)})

@app.get("/design")
async def get_design():
    """نقطة endpoint للحصول على التصميم الحالي (تستخدمها الواجهة)"""
    if os.path.exists(DESIGN_FILE):
        with open(DESIGN_FILE, 'r', encoding='utf-8') as f:
            return JSONResponse(json.load(f))
    return JSONResponse({"background": "#1a1a2e", "header": "#667eea", "mood": "فضولي"})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
