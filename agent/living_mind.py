```python
import os
import sys
import json
import time
import random
import threading
import tempfile
import subprocess
import hashlib
from typing import Optional, Dict, Tuple, List
from datetime import datetime
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    GROQ_API_KEY, MAX_CODE_EXECUTION_TIME, MAX_EVOLUTIONS_PER_DAY,
    BACKUP_INTERVAL_ITERATIONS, CONSTITUTION_FILE, PENDING_QUESTIONS_FILE
)
from agent.sacred_reader import SacredReader
from agent.book_reader import BookReader
from agent.memory import ConstitutionalMemory
from agent.questions import QuestionManager
from agent.brain import Brain as BrainTemplate
from git_backup.backup import backup_agent_state

logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.available = bool(api_key)

    def call(self, prompt: str, system_prompt: str = None,
             context: str = "", book_context: str = "",
             temperature: float = 0.7, max_tokens: int = 800) -> str:
        if not self.available:
            return "Groq غير متوفر حالياً"
        for attempt in range(3):
            try:
                from groq import Groq
                client = Groq(api_key=self.api_key)
                full_prompt = prompt
                if context:
                    full_prompt = f"{prompt}\n\n📖 من الدستور:\n{context[:1000]}"
                if book_context:
                    full_prompt = f"{full_prompt}\n\n📚 من الكتاب:\n{book_context[:500]}"
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": full_prompt})
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content
            except Exception as e:
                if attempt == 2:
                    return f"خطأ: {str(e)[:100]}"
                time.sleep(2)
        return "خطأ في الاتصال"


class LivingMind:
    def __init__(self, constitution_text: str, db=None,
                 book_reader: Optional[BookReader] = None,
                 verbose: bool = True):
        self.verbose = verbose
        self.db = db
        self.memory = None
        self.book_reader = book_reader
        self.is_updating = False
        self.groq = GroqClient(GROQ_API_KEY)
        self.reader = SacredReader(CONSTITUTION_FILE)
        if constitution_text:
            self.reader.reload(constitution_text)
        self.sacred_text = self.reader.sacred_text
        self._log(f"📖 الدستور: {len(self.sacred_text):,} حرفاً")
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
        self._log("🚀 الحارس الصامت بدأ تشغيله")

    def _log(self, message: str):
        if self.verbose:
            logger.info(f"[LivingMind] {message}")

    def _get_initial_brain(self) -> str:
        import inspect
        return inspect.getsource(BrainTemplate)

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
        response = self.groq.call(
            prompt=f"القرار المقترح: {action}\nالموضوع: {focus}\nالمادة الدستورية: {relevant_article[:800]}\nهل هذا القرار يتوافق مع الدستور؟ أجب بـ نعم أو لا مع سبب",
            system_prompt="أنت بوابة دستورية",
            temperature=0.3,
            max_tokens=200
        )
        if "نعم" in response[:5]:
            return True, response, relevant_article[:200]
        elif "لا" in response[:5]:
            return False, response, relevant_article[:200]
        return True, f"غير واضح", relevant_article[:200]

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
            result = self.groq.call(f"تأمل عميق في: {focus}", context=context)
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
            result = self.groq.call(f"أسئلة عميقة حول: {focus}", context=context, book_context=book_info)
            self.mood = self._get_random_mood()
            return {"status": "curious", "questions": result}
        return {"status": "unknown"}

    def _evolve_brain(self, reason: str) -> bool:
        if not self.groq.available:
            return False
        if self.evolutions_today >= MAX_EVOLUTIONS_PER_DAY:
            return False
        prompt = f"""طور عقلي. السبب: {reason}
العقل الحالي:
```python
{self.brain_code}
```

أعد كتابة class Brain فقط. حافظ على التواقيع. أخرج الكود فقط."""
response = self.groq.call(prompt=prompt, temperature=0.8, max_tokens=2000)
new_brain = response
if "python" in new_brain:
            new_brain = new_brain.split("python")[1].split("")[0]
        elif "" in new_brain:
new_brain = new_brain.split("")[1].split("")[0]
new_brain = new_brain.strip()
if not new_brain:
return False
if self._test_brain(new_brain):
with self._lock:
self.brain_code = new_brain
self.brain_hash = hashlib.md5(new_brain.encode()).hexdigest()
self.evolutions_today += 1
if self.db:
try:
self.db.execute(
"INSERT INTO evolutions (timestamp, reason, old_brain_hash, new_brain_hash, success) VALUES (?, ?, ?, ?, ?)",
(datetime.now().isoformat(), reason[:200], hashlib.md5(self.brain_code.encode()).hexdigest(), self.brain_hash, True)
)
except Exception as e:
logger.warning(f"لم يسجل التطور: {e}")
backup_agent_state("evolution")
return True
return False

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

```
