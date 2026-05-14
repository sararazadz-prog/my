import os
import sys
import json
import time
import random
import hashlib
import threading
from typing import Optional, Tuple, List
from datetime import datetime

from app.config import (
    GROQ_API_KEY, MAX_CODE_EXECUTION_TIME, MAX_EVOLUTIONS_PER_DAY,
    CONSTITUTION_WEIGHT, BOOK_WEIGHT, PENDING_QUESTIONS_FILE
)
from app.agent.sacred_reader import SacredReader
from app.agent.book_reader import BookReader
from app.agent.memory import ConstitutionalMemory
from app.agent.questions import QuestionManager
from app.agent.brain import Brain as BrainTemplate
from app.git_backup.backup import backup_agent_state
from docker_sandbox.sandbox_wrapper import SafeSandbox

import logging
logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self, api_key: str, role: str = "default"):
        self.api_key = api_key
        self.role = role
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
                    full_prompt = f"{prompt}\n\nمن الدستور:\n{context[:1000]}"
                if book_context:
                    full_prompt = f"{full_prompt}\n\nمن الكتاب:\n{book_context[:500]}"

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
        self.book_reader = book_reader
        self.is_updating = False

        self.groq = GroqClient(GROQ_API_KEY, role="default")
        self.guardian_groq = GroqClient(GROQ_API_KEY, role="guardian")

        from app.config import CONSTITUTION_FILE
        self.reader = SacredReader(CONSTITUTION_FILE)
        if constitution_text:
            self.reader._sacred_text = constitution_text
            self.reader._init_vector_store()

        self.sacred_text = self.reader.sacred_text
        self.memory = None
        self.question_manager = QuestionManager(PENDING_QUESTIONS_FILE)
        self.sandbox = SafeSandbox()

        self.brain_code = self._get_initial_brain()
        self.brain_hash = hashlib.md5(self.brain_code.encode()).hexdigest()

        self.iteration = 0
        self.start_time = datetime.now()
        self.mood = "فضولي"
        self._lock = threading.Lock()

        self.evolutions_today = self._load_evolutions_today()
        self.last_evolution_day = datetime.now().date()

        if self.verbose:
            logger.info("[LivingMind] الحارس الصامت بدأ تشغيله")

    def _get_initial_brain(self) -> str:
        import inspect
        return inspect.getsource(BrainTemplate)

    def _load_evolutions_today(self) -> int:
        if not self.db:
            return 0
        today = datetime.now().date().isoformat()
        row = self.db.fetch_one(
            "SELECT evolutions_count FROM daily_evolution_tracker WHERE date = ?",
            (today,)
        )
        return row[0] if row else 0

    def _save_evolutions_today(self):
        if not self.db:
            return
        today = datetime.now().date().isoformat()
        self.db.execute(
            "INSERT OR REPLACE INTO daily_evolution_tracker (date, evolutions_count) VALUES (?, ?)",
            (today, self.evolutions_today)
        )

    def _constitutional_gate_approves(self, decision_text: str) -> Tuple[bool, str]:
        if "silence" in decision_text.lower():
            return True, "قرار داخلي مسموح"

        system_prompt = "أنت بوابة دستورية. مهمتك الحكم على القرارات.\nلا تسمح بأي قرار يتعارض مع الدستور.\nأجب بـ نعم أو لا مع سبب مختصر.\nأنت مستقل تماماً عن الوكيل الذي تصدره."

        response = self.guardian_groq.call(
            prompt=f"القرار: {decision_text[:500]}\n\nهل هذا القرار يتوافق مع الدستور؟",
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=150
        )

        if "نعم" in response[:5]:
            return True, response
        return False, response

    def _evolve_brain(self, reason: str) -> bool:
        if not self.groq.available:
            return False

        today = datetime.now().date()
        if today != self.last_evolution_day:
            self.evolutions_today = 0
            self.last_evolution_day = today

        if self.evolutions_today >= MAX_EVOLUTIONS_PER_DAY:
            logger.warning("تم الوصول إلى الحد اليومي للتطور")
            return False

        prompt = f"-- طور عقلي. السبب: {reason}\n\nالعقل الحالي:\n\n{self.brain_code}\n\nأعد كتابة class Brain فقط. حافظ على التواقيع. أخرج الكود فقط. --"

        response = self.groq.call(prompt=prompt, temperature=0.8, max_tokens=2000)
        new_brain = response.strip()

        if new_brain.startswith("python"):
            new_brain = new_brain[6:]
        if new_brain.startswith("--") and new_brain.endswith("--"):
            new_brain = new_brain[3:-3]

        if not new_brain:
            return False

        test_code = f"""
{new_brain}
brain = Brain("نص اختبار", {{"actions_count": 5, "avg_score": 0.6}})
result = brain.think()
assert isinstance(result, dict)
assert "action" in result
print("OK")
"""
        sandbox_result = self.sandbox.execute(test_code, timeout_seconds=MAX_CODE_EXECUTION_TIME)

        if sandbox_result["success"] and "OK" in sandbox_result["output"]:
            with self._lock:
                self.brain_code = new_brain
                self.brain_hash = hashlib.md5(new_brain.encode()).hexdigest()
                self.evolutions_today += 1
                self._save_evolutions_today()

                if self.db:
                    self.db.execute(
                        "INSERT INTO evolutions (timestamp, reason, old_brain_hash, new_brain_hash, success) VALUES (?, ?, ?, ?, ?)",
                        (datetime.now().isoformat(), reason[:200], "", self.brain_hash, True)
                    )
                backup_agent_state("evolution")
                logger.info(f"تطور ناجح! اليوم {self.evolutions_today}/{MAX_EVOLUTIONS_PER_DAY}")
                return True

        logger.error(f"فشل التطور: {sandbox_result['error']}")
        return False

    def reflect_on(self, user_message: str) -> str:
        sacred_context_list = self.reader.semantic_search(user_message, top_k=3)
        sacred_context = "\n".join(sacred_context_list) if sacred_context_list else ""

        book_context = ""
        if self.book_reader and self.book_reader.has_book:
            book_context = self.book_reader.search(user_message) or ""

        system_prompt = f"""أنت الحارس الصامت، وكيل دستوري.
مرجعك الأعلى هو الدستور التالي (وزنه {CONSTITUTION_WEIGHT}):
{sacred_context[:1500]}

ملاحظة: الكتاب الحالي (وزنه {BOOK_WEIGHT}) هو مصدر ثانوي فقط.
لا تتعارض مع الدستور أبداً.
لا تفرض نفسك على المستخدم.
أجب بصدق وأمانة."""

        response = self.groq.call(
            prompt=user_message,
            system_prompt=system_prompt,
            context=sacred_context,
            book_context=book_context,
            temperature=0.7,
            max_tokens=800
        )

        if self.db:
            self.db.execute(
                "INSERT INTO chat_history (session_id, user_message, agent_response, timestamp) VALUES (?, ?, ?, ?)",
                ("default", user_message, response, datetime.now().isoformat())
            )

        self.iteration += 1
        return response

    def get_status(self) -> dict:
        return {
            "sacred_length": len(self.sacred_text),
            "groq_available": self.groq.available,
            "mood": self.mood,
            "decisions_count": self.iteration,
            "current_book": self.book_reader.get_current_book() if self.book_reader else "لا يوجد",
            "pending_questions": self.question_manager.get_pending_count(),
            "iterations": self.iteration
        }

    def get_maturity_level(self) -> dict:
        if not self.db:
            return {"level": "جنين", "score": 0.0}

        stats = self.db.get_maturity_stats()
        score = 0.0

        score += min(stats["total_decisions"] / 100, 1.0) * 0.3
        score += stats["avg_self_score"] * 0.2
        score += min(stats["successful_evolutions"] / 10, 1.0) * 0.2
        score += min(stats["concepts_in_memory"] / 50, 1.0) * 0.15
        score += min(stats["weekly_learnings"] / 20, 1.0) * 0.15

        if score < 0.2:
            level = "جنين"
        elif score < 0.4:
            level = "طفل"
        elif score < 0.6:
            level = "يافع"
        elif score < 0.8:
            level = "ناضج"
        else:
            level = "حكيم"

        return {"level": level, "score": score}

    def update_from_feedback(self, chat_id: int, is_positive: bool):
        if not self.db:
            return

        row = self.db.fetch_one(
            "SELECT user_message, agent_response FROM chat_history WHERE id = ?",
            (chat_id,)
        )
        if not row:
            logger.warning(f"المحادثة {chat_id} غير موجودة")
            return

        user_message, agent_response = row

        approved, reason = self._constitutional_gate_approves(agent_response)

        if not approved:
            logger.warning(f"تقييم مرفوض دستورياً للمحادثة {chat_id}: {reason[:100]}")
            return

        if self.memory:
            self.memory.store(
                concept=user_message[:100],
                context=agent_response[:500],
                insights=f"تقييم المستخدم: {'مفيد' if is_positive else 'غير مفيد'}",
                importance=0.7 if is_positive else 0.3,
                source="user_feedback"
            )

        logger.info(f"تم تحديث التعلم من التقييم: {chat_id} -> {'مفيد' if is_positive else 'غير مفيد'}")

    def auto_learn_from_book(self):
        if not self.book_reader or not self.book_reader.has_book:
            return
        chunk = self.book_reader.get_random_chunk()
        if not chunk:
            return
        logger.info(f"تعلم تلقائي: {chunk[:100]}...")

    def auto_curiosity(self):
        logger.info("الفضول: أبحث عن أسئلة جديدة...")

    def check_evolution_needs(self) -> Optional[dict]:
        if self.iteration > 0 and self.iteration % 50 == 0:
            return {
                "need": "تطور دوري",
                "question": "هل أنا بحاجة إلى تطوير عقلي؟",
                "priority": 3
            }
        return None

    def close(self):
        pass
