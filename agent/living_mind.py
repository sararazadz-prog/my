sraa Al:
# ============================================================
# العقل الحي – LivingMind
# النسخة النخبوية النهائية v5.3
# ============================================================
# الميزات:
# 1. العقل القابل للتطور (brain_code يتغير ذاتياً)
# 2. التعلم التلقائي من الكتب كل 30 دقيقة
# 3. الفضول التلقائي وطرح الأسئلة على المستخدم
# 4. البوابة الدستورية لفحص كل قرار قبل التنفيذ
# 5. التقييم الذاتي وتحسين الأداء المستمر
# 6. التعبير البصري عن المزاج عبر SVG (الوكيل يرسم بنفسه)
# 7. توليد تقارير كاملة عند سؤال "يا حارس، هل من جديد؟"
# ============================================================

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

# 🔑 إضافة مسار المشروع لضمان عمل الاستيرادات في بيئة Render
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(file))))

from config import (
    GROQ_API_KEY, MAX_CODE_EXECUTION_TIME, MAX_EVOLUTIONS_PER_DAY,
    BACKUP_INTERVAL_ITERATIONS, CONSTITUTION_FILE, PENDING_QUESTIONS_FILE
)
from agent.sacred_reader import SacredReader
from agent.book_reader import BookReader
from agent.memory import ConstitutionalMemory
from agent.questions import QuestionManager
from agent.brain import Brain as BrainTemplate

# 🔑 استخدام المجلد الجديد git_backup (تم حل تعارض التسمية مع مكتبة PyGithub)
from git_backup.backup import backup_agent_state

logger = logging.getLogger(name)


# ============================================================
# عميل Groq الموحد
# ============================================================

class GroqClient:
    """عميل موحد لـ Groq API مع معالجة الأخطاء وإعادة المحاولة"""
    
    def init(self, api_key: str):
        self.api_key = api_key
        self.available = bool(api_key)
    
    def call(self, prompt: str, system_prompt: str = None, 
             context: str = "", book_context: str = "", 
             temperature: float = 0.7, max_tokens: int = 800) -> str:
        """استدعاء Groq API بشكل آمن مع إعادة محاولة تلقائية"""
        if not self.available:
            return "Groq غير متوفر حالياً. يرجى التحقق من المفتاح."
        
        for attempt in range(3):  # 3 محاولات
            try:
                from groq import Groq
                client = Groq(api_key=self.api_key)
                
                # بناء النص الكامل
                full_prompt = prompt
                if context:
                    full_prompt = f"{prompt}\n\n📖 من الدستور:\n{context[:1000]}"
                if book_context:
                    full_prompt = f"{full_prompt}\n\n📚 من الكتاب:\n{book_context[:500]}"
                
                # بناء الرسائل
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": full_prompt})
                
                # استدعاء API
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content
                
            except ImportError:
                logger.error("مكتبة groq غير مثبتة")
                return "خطأ: مكتبة groq غير متوفرة"
            except Exception as e:
                logger.warning(f"محاولة {attempt + 1} فشلت: {e}")
                if attempt == 2:  # آخر محاولة
                    logger.error(f"خطأ في Groq بعد 3 محاولات: {e}")
                    return f"خطأ تقني: {str(e)[:100]}"
                time.sleep(2)  # انتظر قبل إعادة المحاولة
        
        return "خطأ: فشل الاتصال بـ Groq"


# ============================================================
# العقل الحي
# ============================================================

class LivingMind:
    """الوكيل الذكي الذي يتطور ذاتياً مع احترام الدستور"""
    
    def init(self, constitution_text: str, db=None, 
                 book_reader: Optional[BookReader] = None, 
                 verbose: bool = True):
        self.verbose = verbose
        self.db = db
        self.memory = None
        self.book_reader = book_reader
        self.is_updating = False
        
        # تهيئة Groq
        self.groq = GroqClient(GROQ_API_KEY)
        
        # قارئ الدستور
        self.reader = SacredReader(CONSTITUTION_FILE)
        if constitution_text:
            self.reader.reload(constitution_text)
        self.sacred_text = self.reader.sacred_text
        self._log(f"📖 الدستور: {len(self.sacred_text):,} حرفاً، {self.reader.num_chunks} مقطعاً")
        
        # العقل القابل للتطور
        self.brain_code = self._get_initial_brain()
        self.brain_hash = hashlib.md5(self.brain_code.encode()).hexdigest()
        
        # حالة الوكيل
        self.is_alive = True
        self.iteration = 0
        self.start_time = datetime.now()
        self.current_chunk_index = 0
        self.evolutions_today = 0
        self.last_evolution_day = datetime.now().date()
        self.mood = "فضولي"
        self._lock = threading.Lock()
        
        # إدارة الأسئلة المعلقة
        self.question_manager = QuestionManager(PENDING_QUESTIONS_FILE)
        
        self._log("🚀 الحارس الصامت v5.3 بدأ تشغيله")
    
    def _log(self, message: str):
        """تسجيل رسالة مع اسم الفئة"""
        if self.verbose:
            logger.info(f"[LivingMind] {message}")
    
    def _get_initial_brain(self) -> str:
        """العقل الأولي - سيتم تطويره ذاتياً"""
        import inspect
        return inspect.getsource(BrainTemplate)
    
    def _execute_brain(self, memory_summary: dict) -> dict:
        """تنفيذ العقل الحالي واتخاذ القرار"""
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
        except subprocess.TimeoutExpired:
            return {"action": "silence", "reason": "انتهى وقت التنفيذ"}
        except Exception as e:
            return {"action": "silence", "reason": f"استثناء: {str(e)[:100]}"}
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def _get_memory_summary(self) -> dict:
        """تلخيص الذاكرة للعقل"""
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
        """البوابة الدستورية - تفحص كل قرار قبل التنفيذ"""
        action = decision.get("action", "silence")
        focus = decision.get("focus", "")
        
        # البحث عن مادة دستورية ذات صلة
        relevant_article = self.reader.find_article(focus[:100]) if focus else None
        if not relevant_article:
            relevant_article = self.reader.get_chunk(self.current_chunk_index - 1)[:500]
        
        # القرارات الداخلية مسموحة دائماً
        if action in ["silence"]:
            return True, "قرار داخلي مسموح", relevant_article[:200]
        
        # التطور له حد يومي
        if action == "evolve":
            if self.evolutions_today < MAX_EVOLUTIONS_PER_DAY:
                return True, "التطور مسموح ضمن الحدود اليومية", relevant_article[:200]
            return False, f"تم الوصول إلى الحد اليومي للتطور ({MAX_EVOLUTIONS_PER_DAY})", relevant_article[:200]
        
        # استخدام Groq كحكم للقرارات المؤثرة
        response = self.groq.call(
            prompt=f"""القرار المقترح: {action}
الموضوع: {focus}
المادة الدستورية: {relevant_article[:800]}

هل هذا القرار يتوافق مع روح الدستور وقيمه؟
أجب بـ "نعم" أو "لا" مع سبب موجز.""",
            system_prompt="أنت بوابة دستورية حكيمة. مهمتك حماية الدستور.",
            temperature=0.3,
            max_tokens=200
        )
        
        if "نعم" in response[:5]:
            return True, response, relevant_article[:200]
        elif "لا" in response[:5]:
            return False, response, relevant_article[:200]
        return True, f"غير واضح، مسموح احتياطياً: {response[:50]}", relevant_article[:200]
    
    def _act(self, decision: dict) -> dict:
        """تنفيذ القرار بعد المرور على البوابة الدستورية"""
        action = decision.get("action", "silence")
        focus = decision.get("focus", "")
        reason = decision.get("reason", "")
        
        allowed, gate_reason, article = self._constitutional_gate(decision)
        
        if not allowed:
            self._log(f"🚫 قرار مرفوض: {action} - {gate_reason[:100]}")
            return {"status": "rejected", "message": f"مرفوض: {gate_reason[:100]}"}
        
        context = self.reader.get_chunk(self.current_chunk_index - 1)[:500]
        
        if action == "silence":
            self.mood = self._get_random_mood()
            return {"status": "silent", "message": "🤫 في الصمت حكمة"}
        
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
            result = self.groq.call(
                f"أسئلة عميقة واستفسارات حول: {focus}",
                context=context,
                book_context=book_info
            )
            self.mood = self._get_random_mood()

return {"status": "curious", "questions": result}
        
        return {"status": "unknown", "message": f"إجراء غير معروف: {action}"}
    
    def _evolve_brain(self, reason: str) -> bool:
        """تطوير العقل - إعادة كتابة brain_code"""
        if not self.groq.available:
            self._log("لا يمكن التطور بدون Groq")
            return False
        
        if self.evolutions_today >= MAX_EVOLUTIONS_PER_DAY:
            self._log(f"⏸ تم الوصول إلى الحد اليومي للتطور ({MAX_EVOLUTIONS_PER_DAY})")
            return False
        
        # 🔑 التصحيح النخبوي: استخدام self.brain_code بدلاً من brain_code
        prompt = f"""طور عقلي. السبب: {reason}

العقل الحالي:
{self.brain_code}
أعد كتابة class Brain فقط (init, think).
حافظ على التواقيع: init(self, sacred_context, memory_summary) و think(self)
يمكنك تحسين منطق اتخاذ القرار وإضافة حكمة.
أخرج الكود فقط، بدون شرح."""

{brain_code}
brain = Brain("نص اختبار", {{
"actions_count": 5,
"avg_score": 0.6,
"iteration": 10,
"reflection_depth": 1,
"evolutions_today": 0,
"has_book": True
}})
result = brain.think()
assert isinstance(result, dict), "يجب أن يعيد result قاموساً"
assert "action" in result, "يجب أن يحتوي result على 'action'"
assert result["action"] in ["silence", "deep_reflection", "evolve", "curiosity"], f"إجراء غير معروف: {{result['action']}}"
print("OK")
"""
with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
f.write(test_code)
temp_file = f.name

أنا وكيل دستوري اسمي الحارس الصامت.
مزاجي الحالي: {mood}
عدد القرارات: {stats.get('decisions_count', 0)}
متوسط تقييمي الذاتي: {stats.get('avg_score', 0):.2f}
الكتاب الحالي: {stats.get('current_book', 'لا يوجد')}

أريد أن أرسم تعبيراً بصرياً عن حالتي ومزاجي.
استخدم SVG فقط (بدون HTML، بدون CSS، فقط SVG).
أخرج كود SVG داخل
`
يجب أن يكون SVG معبراً عن مشاعري.
استخدم ألواناً تعبر عن المزاج.
"""
