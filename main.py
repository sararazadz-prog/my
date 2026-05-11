# ============================================================
# المراقب الصامت – النسخة النهائية المصححة
# تعالج جميع العيوب الخمسة:
# 1. self.memory موجود ومربوط بشكل صحيح
# 2. _get_memory_summary تتحمل غياب قاعدة البيانات
# 3. background_loop تنتظر حتى يكتمل الوكيل
# 4. اختبار Groq عند بدء التشغيل
# 5. DatabaseManager يعيد البيانات مباشرة (لا closed cursor)
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
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime

# ============================================================
# FastAPI
# ============================================================
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ============================================================
# قاعدة البيانات (PostgreSQL أو SQLite)
# ============================================================
import sqlite3
import psycopg2

# ============================================================
# إعداد التسجيل (logging)
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
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///constitution_memory.db")
CONSTITUTION_PATH = os.environ.get("CONSTITUTION_PATH", "/data/constitution.txt")
PERSISTENT_DIR = os.environ.get("PERSISTENT_DIR", "/data")

os.makedirs(PERSISTENT_DIR, exist_ok=True)

# ============================================================
# إدارة قاعدة البيانات (المصححة – لا closed cursor)
# ============================================================

class DatabaseManager:
    """مدير قاعدة بيانات – يعيد البيانات مباشرة، لا يعيد cursor"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.conn = None
        self.is_postgres = False
        self._connect()
    
    def _connect(self):
        if self.database_url and self.database_url.startswith("postgres"):
            self.conn = psycopg2.connect(self.database_url)
            self.is_postgres = True
            logger.info("✅ PostgreSQL connected")
        else:
            db_path = self.database_url.replace("sqlite:///", "") if self.database_url else "constitution_memory.db"
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.is_postgres = False
            logger.info(f"✅ SQLite connected: {db_path}")
        self._init_tables()
    
    def _init_tables(self):
        cursor = self.conn.cursor()
        
        if self.is_postgres:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    id SERIAL PRIMARY KEY,
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
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT,
                    reason TEXT,
                    old_brain_hash TEXT,
                    new_brain_hash TEXT,
                    success BOOLEAN
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS constitutional_memory (
                    id SERIAL PRIMARY KEY,
                    concept TEXT,
                    context TEXT,
                    insights TEXT,
                    related_concepts TEXT,
                    created_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT,
                    user_message TEXT,
                    agent_response TEXT,
                    timestamp TEXT
                )
            """)
        else:
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
        
        self.conn.commit()
        cursor.close()
    
    def execute(self, query: str, params: tuple = ()):
        """تنفيذ استعلام INSERT/UPDATE/DELETE – تعيد عدد الصفوف المتأثرة"""
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
        """تنفيذ استعلام SELECT – تعيد جميع الصفوف"""
        cursor = self.conn.cursor()
        try:
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            cursor.close()
    
    def fetch_one(self, query: str, params: tuple = ()):
        """تنفيذ استعلام SELECT – تعيد صفاً واحداً"""
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
# قارئ الدستور المقدس
# ============================================================

class SacredReader:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._sacred_text = None
        self.chunks = []
        
        if not self.file_path.exists():
            self._create_sample_constitution()
    
    def _create_sample_constitution(self):
        sample = """المادة 1: لكل فرد الحق في الكرامة الإنسانية.
المادة 2: العدل أساس الملك.
المادة 3: العلم نور والجهل ظلام.
المادة 4: التعاون بين الناس واجب.
المادة 5: الحرية مسؤولية."""
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.write(sample)
        logger.info(f"تم إنشاء دستور تجريبي في {self.file_path}")
    
    def read(self) -> str:
        if self._sacred_text is not None:
            return self._sacred_text
        
        ext = self.file_path.suffix.lower()
        if ext == '.pdf':
            self._sacred_text = self._read_pdf()
        elif ext in ['.txt', '.md', '.json']:
            self._sacred_text = self._read_text()
        else:
            raise ValueError(f"امتداد غير مدعوم: {ext}")
        
        self._chunk_text()
        return self._sacred_text
    
    def _read_pdf(self) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("الرجاء تثبيت pypdf: pip install pypdf")
        
        reader = PdfReader(self.file_path)
        pages = []
        for page_num, page in enumerate(reader.pages, 1):
            try:
                text = page.extract_text()
                pages.append(text)
            except Exception as e:
                pages.append(f"[خطأ في الصفحة {page_num}: {e}]")
        return "\n".join(pages)
    
    def _read_text(self) -> str:
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _chunk_text(self, chunk_size: int = 500):
        if not self._sacred_text:
            self.read()
        words = self._sacred_text.split()
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size])
            self.chunks.append(chunk)
    
    def lock(self):
        pass
    
    @property
    def sacred_text(self) -> str:
        if self._sacred_text is None:
            self.read()
        return self._sacred_text
    
    def get_chunk(self, index: int) -> str:
        if not self.chunks:
            self.read()
        return self.chunks[index % len(self.chunks)]
    
    def find_article(self, keyword: str) -> Optional[str]:
        if not self.chunks:
            self.read()
        for chunk in self.chunks:
            if keyword in chunk:
                return chunk[:500]
        return None
    
    @property
    def num_chunks(self) -> int:
        return len(self.chunks)
    
    def reload(self, new_path: str):
        self.file_path = Path(new_path)
        self._sacred_text = None
        self.chunks = []
        self.read()
        logger.info(f"تم تحميل دستور جديد: {new_path}")


# ============================================================
# الذاكرة الدستورية التراكمية
# ============================================================

class ConstitutionalMemory:
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    def store(self, concept: str, context: str, insights: str):
        try:
            if self.db.is_postgres:
                self.db.execute(
                    "INSERT INTO constitutional_memory (concept, context, insights, related_concepts, created_at) VALUES (%s, %s, %s, %s, %s)",
                    (concept[:100], context[:500], insights[:500], "[]", datetime.now().isoformat())
                )
            else:
                self.db.execute(
                    "INSERT INTO constitutional_memory (concept, context, insights, related_concepts, created_at) VALUES (?, ?, ?, ?, ?)",
                    (concept[:100], context[:500], insights[:500], "[]", datetime.now().isoformat())
                )
        except Exception as e:
            logger.error(f"خطأ في تخزين الذاكرة: {e}")
    
    def recall(self, concept: str) -> List[Dict]:
        try:
            if self.db.is_postgres:
                rows = self.db.fetch_all(
                    "SELECT context, insights, created_at FROM constitutional_memory WHERE concept LIKE %s ORDER BY id DESC LIMIT 5",
                    (f"%{concept}%",)
                )
            else:
                rows = self.db.fetch_all(
                    "SELECT context, insights, created_at FROM constitutional_memory WHERE concept LIKE ? ORDER BY id DESC LIMIT 5",
                    (f"%{concept}%",)
                )
            
            results = []
            for row in rows:
                results.append({
                    "context": row[0],
                    "insights": row[1],
                    "created_at": row[2]
                })
            return results
        except Exception as e:
            logger.error(f"خطأ في استدعاء الذاكرة: {e}")
            return []
    
    def get_summary(self) -> str:
        try:
            row = self.db.fetch_one("SELECT COUNT(*) FROM constitutional_memory")
            count = row[0] if row else 0
            
            if count == 0:
                return "الذاكرة فارغة."
            
            if self.db.is_postgres:
                rows = self.db.fetch_all("SELECT concept FROM constitutional_memory ORDER BY id DESC LIMIT 5")
            else:
                rows = self.db.fetch_all("SELECT concept FROM constitutional_memory ORDER BY id DESC LIMIT 5")
            
            recent = [row[0] for row in rows]
            return f"{count} مفهوماً. آخرها: {', '.join(recent)}"
        except Exception as e:
            logger.error(f"خطأ في ملخص الذاكرة: {e}")
            return "الذاكرة غير متاحة حالياً"


# ============================================================
# العقل الحي (المصحح)
# ============================================================

class LivingMind:
    def __init__(
        self,
        constitution_path: str,
        groq_api_key: Optional[str] = None,
        db: Optional[DatabaseManager] = None,
        verbose: bool = True
    ):
        self.verbose = verbose
        self.db = db
        self.memory = None  # سيُربط لاحقاً
        
        # قارئ الدستور
        self.reader = SacredReader(constitution_path)
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
        """ملخص الذاكرة – تتحمل غياب قاعدة البيانات"""
        count = 0
        avg_score = 0.5
        
        if self.db:
            try:
                row = self.db.fetch_one("SELECT COUNT(*), AVG(self_score) FROM decisions WHERE self_score IS NOT NULL")
                if row and row[0]:
                    count = row[0] or 0
                    avg_score = float(row[1]) if row[1] else 0.5
            except Exception as e:
                logger.warning(f"فشل قراءة إحصائيات الذاكرة: {e}")
        
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
    
    def _use_groq(self, prompt: str, context: str = "") -> str:
        if not self.groq_available:
            return "[Groq غير متوفر]"
        
        try:
            from groq import Groq
            client = Groq(api_key=self.groq_api_key)
            
            full_prompt = prompt
            if context:
                full_prompt = f"{prompt}\n\nالنص الدستوري:\n{context[:1000]}"
            
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "أنت عقل دستوري حكيم. كن موجزاً وعميقاً."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.7,
                max_tokens=400
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
            return {"status": "silent", "message": "🤫 صامت"}
        
        elif action == "deep_reflection":
            result = self._use_groq(f"تأمل عميق في: {focus}", context)
            if self.memory:
                self.memory.store(focus[:50], context, result)
            return {"status": "reflected", "reflection": result}
        
        elif action == "evolve":
            success = self._evolve_brain(decision.get("reason", "تحسين"))
            return {"status": "evolved" if success else "failed"}
        
        elif action == "curiosity":
            result = self._use_groq(f"أسئلة عميقة حول: {focus}", context)
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
                        if self.db.is_postgres:
                            self.db.execute(
                                "INSERT INTO evolutions (timestamp, reason, old_brain_hash, new_brain_hash, success) VALUES (%s, %s, %s, %s, %s)",
                                (datetime.now().isoformat(), reason[:200], "old", "new", True)
                            )
                        else:
                            self.db.execute(
                                "INSERT INTO evolutions (timestamp, reason, old_brain_hash, new_brain_hash, success) VALUES (?, ?, ?, ?, ?)",
                                (datetime.now().isoformat(), reason[:200], "old", "new", True)
                            )
                    except Exception as e:
                        logger.warning(f"لم يسجل التطور في قاعدة البيانات: {e}")
                
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
                    if self.db.is_postgres:
                        row = self.db.fetch_one(
                            "SELECT COUNT(*) FROM decisions WHERE reflection LIKE %s AND iteration < %s",
                            (f"%{output[:50]}%", self.iteration)
                        )
                    else:
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
            if self.db.is_postgres:
                self.db.execute(
                    "INSERT INTO decisions (iteration, timestamp, action, focus, context_preview, reflection, self_score, gate_passed, gate_reason) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (self.iteration, datetime.now().isoformat(), action, focus[:100], context[:200], reflection[:500], score, gate_passed, gate_reason[:200])
                )
            else:
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
        context = self.reader.find_article(text[:50]) or self.reader.get_chunk(self.current_chunk_index)[:500]
        result = self._use_groq(f"تأمل عميق في: {text}", context)
        
        if self.memory:
            self.memory.store(text[:50], context, result)
        
        if self.db:
            try:
                if self.db.is_postgres:
                    self.db.execute(
                        "INSERT INTO chat_history (session_id, user_message, agent_response, timestamp) VALUES (%s, %s, %s, %s)",
                        ("default", text[:500], result[:500], datetime.now().isoformat())
                    )
                else:
                    self.db.execute(
                        "INSERT INTO chat_history (session_id, user_message, agent_response, timestamp) VALUES (?, ?, ?, ?)",
                        ("default", text[:500], result[:500], datetime.now().isoformat())
                    )
            except Exception as e:
                logger.warning(f"فشل حفظ المحادثة: {e}")
        
        return result
    
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
                "groq_available": self.groq_available
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
background_thread: Optional[threading.Thread] = None
background_running = True

def background_loop():
    """حلقة الخلفية – تنتظر 10 ثوانٍ حتى يكتمل الوكيل"""
    global mind, background_running
    logger.info("🟢 بدء حلقة الخلفية (بعد انتظار 10 ثوانٍ)")
    time.sleep(10)
    
    while background_running and mind:
        try:
            result = mind.live_step()
            if result and result["iteration"] % 10 == 0:
                logger.info(f"📊 الخلفية: الدورة {result['iteration']}, القرار: {result['action']}, التقييم: {result['score']:.2f}")
            time.sleep(random.uniform(60, 120))
        except Exception as e:
            logger.error(f"خطأ في حلقة الخلفية: {e}", exc_info=True)
            time.sleep(60)
    
    logger.info("🔴 توقفت حلقة الخلفية")

@app.on_event("startup")
async def startup_event():
    global mind, db, background_thread
    
    logger.info("=" * 60)
    logger.info("🚀 تشغيل المراقب الصامت على Render")
    logger.info("=" * 60)
    
    # 1. قاعدة البيانات
    try:
        db = DatabaseManager(DATABASE_URL)
        logger.info(f"✅ قاعدة البيانات: {'PostgreSQL' if db.is_postgres else 'SQLite'}")
    except Exception as e:
        logger.error(f"❌ فشل اتصال قاعدة البيانات: {e}")
        return
    
    # 2. الذاكرة التراكمية
    try:
        memory = ConstitutionalMemory(db)
        logger.info("✅ الذاكرة التراكمية جاهزة")
    except Exception as e:
        logger.error(f"❌ فشل إنشاء الذاكرة: {e}")
        return
    
    # 3. الوكيل
    try:
        mind = LivingMind(
            constitution_path=CONSTITUTION_PATH,
            groq_api_key=GROQ_API_KEY if GROQ_API_KEY else None,
            db=db,
            verbose=True
        )
        mind.memory = memory
        logger.info(f"✅ الوكيل جاهز: {len(mind.sacred_text):,} حرفاً")
    except Exception as e:
        logger.error(f"❌ فشل إنشاء الوكيل: {e}")
        return
    
    # 4. اختبار Groq
    if GROQ_API_KEY:
        try:
            test_response = mind._use_groq("قل فقط: 'Groq يعمل بنجاح'", "")
            logger.info(f"✅ اختبار Groq: {test_response[:100]}")
        except Exception as e:
            logger.error(f"❌ فشل اختبار Groq: {e}")
    else:
        logger.warning("⚠️ لم يتم توفير مفتاح Groq API")
    
    # 5. تشغيل الخلفية
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

@app.get("/", response_class=HTMLResponse)
async def chat_page():
    return HTMLResponse("""
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>المراقب الصامت</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .chat-container {
            width: 100%;
            max-width: 800px;
            background: rgba(255,255,255,0.95);
            border-radius: 25px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 85vh;
        }
        .chat-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }
        .chat-header h1 { font-size: 1.5em; margin-bottom: 5px; }
        .chat-header p { font-size: 0.8em; opacity: 0.9; }
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .message { margin-bottom: 15px; display: flex; flex-direction: column; }
        .user-message { align-items: flex-end; }
        .agent-message { align-items: flex-start; }
        .message-bubble {
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 20px;
            word-wrap: break-word;
        }
        .user-message .message-bubble {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-bottom-right-radius: 5px;
        }
        .agent-message .message-bubble {
            background: white;
            color: #333;
            border-bottom-left-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .message-time { font-size: 0.7em; color: #888; margin-top: 5px; }
        .chat-input {
            padding: 20px;
            background: white;
            border-top: 1px solid #eee;
            display: flex;
            gap: 10px;
        }
        .chat-input input {
            flex: 1;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            font-size: 1em;
            outline: none;
        }
        .chat-input input:focus { border-color: #667eea; }
        .chat-input button {
            padding: 12px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-size: 1em;
        }
        .status-bar {
            padding: 8px 20px;
            background: #e8e8e8;
            font-size: 0.7em;
            color: #666;
            text-align: center;
        }
        .typing { color: #888; font-style: italic; }
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            <h1>🤖 المراقب الصامت</h1>
            <p>وكيل دستوري حي | يتطور ذاتياً | يعيش 24 ساعة</p>
        </div>
        <div class="chat-messages" id="messages">
            <div class="message agent-message">
                <div class="message-bubble">
                    السلام عليكم. أنا المراقب الصامت. أسألني عن الدستور، وسأجيبك بتأمل عميق.
                </div>
            </div>
        </div>
        <div class="chat-input">
            <input type="text" id="question" placeholder="اكتب سؤالك هنا..." onkeypress="if(event.keyCode==13) sendMessage()">
            <button onclick="sendMessage()">إرسال</button>
        </div>
        <div class="status-bar" id="status">🟢 يتطور ذاتياً في الخلفية</div>
    </div>
    <script>
        const messagesDiv = document.getElementById('messages');
        const questionInput = document.getElementById('question');
        const statusDiv = document.getElementById('status');
        
        function addMessage(text, isUser) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user-message' : 'agent-message'}`;
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
        }
        
        function showTyping() {
            const typingDiv = document.createElement('div');
            typingDiv.className = 'message agent-message';
            typingDiv.id = 'typing';
            typingDiv.innerHTML = '<div class="message-bubble typing">يكتب...</div>';
            messagesDiv.appendChild(typingDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        function hideTyping() {
            const typing = document.getElementById('typing');
            if (typing) typing.remove();
        }
        
        async function sendMessage() {
            const question = questionInput.value.trim();
            if (!question) return;
            addMessage(question, true);
            questionInput.value = '';
            showTyping();
            statusDiv.innerHTML = '🤔 الوكيل يفكر...';
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: question })
                });
                const data = await response.json();
                hideTyping();
                addMessage(data.response, false);
                statusDiv.innerHTML = '🟢 يتطور ذاتياً في الخلفية';
            } catch (error) {
                hideTyping();
                addMessage('عذراً، حدث خطأ. حاول مرة أخرى.', false);
                statusDiv.innerHTML = '🔴 خطأ في الاتصال';
            }
        }
        
        async function updateStatus() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
                statusDiv.innerHTML = `🟢 ${data.decisions_count} قرار | ${data.evolutions_today}/3 تطور اليوم | ${data.iterations} دورة`;
            } catch(e) {}
        }
        setInterval(updateStatus, 30000);
        updateStatus();
    </script>
</body>
</html>
    """)

@app.post("/chat")
async def chat(req: ChatRequest):
    global mind
    if not mind:
        return JSONResponse({"response": "الوكيل لا يزال يبدأ. حاول مرة أخرى خلال دقيقة."}, status_code=503)
    
    try:
        logger.info(f"📨 سؤال وارد: {req.message[:50]}...")
        response = mind.reflect_on(req.message)
        
        if not response or response.strip() == "":
            logger.error("الوكيل أعاد رداً فارغاً")
            return JSONResponse({"response": "عذراً، لم أستطع توليد رد هذه المرة."})
        
        logger.info(f"✅ تم الرد: {response[:50]}...")
        return JSONResponse({"response": response})
    except Exception as e:
        logger.error(f"❌ خطأ في الشات: {e}", exc_info=True)
        return JSONResponse({"response": f"حدث خطأ: {str(e)[:100]}، حاول مرة أخرى."}, status_code=500)

@app.get("/status")
async def get_status():
    global mind
    if not mind:
        return JSONResponse({"ready": False, "error": "الوكيل لم يبدأ بعد"})
    try:
        return JSONResponse(mind.get_status())
    except Exception as e:
        logger.error(f"خطأ في /status: {e}")
        return JSONResponse({"error": str(e)})

@app.get("/health")
async def health():
    return JSONResponse({"status": "alive", "timestamp": datetime.now().isoformat()})

@app.post("/upload")
async def upload_constitution(file: UploadFile = File(...)):
    global mind
    file_path = f"{PERSISTENT_DIR}/{file.filename}"
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    
    if mind:
        mind.reader.reload(file_path)
        mind.sacred_text = mind.reader.sacred_text
    
    logger.info(f"تم رفع دستور جديد: {file_path}")
    return JSONResponse({"status": "success", "path": file_path})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
