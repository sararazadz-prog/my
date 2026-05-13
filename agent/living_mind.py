# ============================================================
# العقل الحي – LivingMind (النسخة المحسنة)
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
from typing import Optional, Dict, Tuple
from datetime import datetime
import logging

from config import (
    MAX_CODE_EXECUTION_TIME, MAX_EVOLUTIONS_PER_DAY, BACKUP_INTERVAL_ITERATIONS,
    LEARNING_INTERVAL, CURIOSITY_INTERVAL, GROQ_API_KEY, CONSTITUTION_FILE
)
from agent.sacred_reader import SacredReader
from agent.book_reader import BookReader
from agent.memory import ConstitutionalMemory
from agent.questions import QuestionManager
from agent.brain import Brain as BrainTemplate
from database.db_manager import DatabaseManager
from github.backup import backup_agent_state

logger = logging.getLogger(__name__)


class GroqClient:
    """عميل موحد لـ Groq API مع fallback"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.available = bool(api_key)
    
    def call(self, prompt: str, system_prompt: str = None, context: str = "", book_context: str = "", temperature: float = 0.7, max_tokens: int = 800) -> str:
        if not self.available:
            return "Groq غير متوفر حالياً."
        
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
            logger.error(f"خطأ في Groq: {e}")
            return f"خطأ: {str(e)[:100]}"


class LivingMind:
    def __init__(self, constitution_text: str, db: Optional[DatabaseManager] = None, 
                 book_reader: Optional[BookReader] = None, verbose: bool = True):
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
        self._log(f"📖 الدستور: {len(self.sacred_text):,} حرفاً")
        
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
        
        # إدارة الأسئلة
        from config import PENDING_QUESTIONS_FILE
        self.question_manager = QuestionManager(PENDING_QUESTIONS_FILE)
        
        self._log("🚀 الحارس الصامت v5.0 بدأ تشغيله")
    
    def _log(self, message: str):
        if self.verbose:
            logger.info(f"[LivingMind] {message}")
    
    def _get_initial_brain(self) -> str:
        """العقل الأولي - سيتم تطويره ذاتياً"""
        import inspect
        return inspect.getsource(BrainTemplate)
    
    def _execute_brain(self, memory_summary: dict) -> dict:
        """تنفيذ العقل الحالي"""
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
        """البوابة الدستورية - تفحص كل قرار"""
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
            return False, "تم الوصول إلى الحد اليومي للتطور", relevant_article[:200]
        
        # استخدام Groq كحكم
        response = self.groq.call(
            prompt=f"القرار المقترح: {action}\nالموضوع: {focus}\nالمادة الدستورية: {relevant_article[:800]}\nهل هذا القرار يتوافق مع الدستور؟ أجب بـ 'نعم' أو 'لا' مع سبب.",
            system_prompt="أنت بوابة دستورية حكيمة.",
            temperature=0.3,
            max_tokens=200
        )
        
        if "نعم" in response[:5]:
            return True, response, relevant_article[:200]
        elif "لا" in response[:5]:
            return False, response, relevant_article[:200]
        return True, f"غير واضح: {response[:50]}", relevant_article[:200]
    
    def reflect_on(self, text: str) -> str:
        """التفكر والرد على استفسار المستخدم"""
        if not self.sacred_text:
            return "الدستور لم يتم تحميله بعد."
        
        constitutional_context = self.reader.find_article(text[:100]) or self.reader.get_chunk(self.current_chunk_index)[:500]
        book_context = ""
        if self.book_reader and self.book_reader.has_book:
            book_context = self.book_reader.search(text[:100]) or ""
        
        response = self.groq.call(
            prompt=text,
            system_prompt="""أنت الحارس الصامت، وكيل دستوري حكيم.
            الدستور هو مرجعك الأول والمطلق.
            الكتب مصادر ثانوية، توزن ولا تساوي الدستور.
            أنت تتعلم ذاتياً وتتطور. لديك فضول معرفي.""",
            context=constitutional_context,
            book_context=book_context
        )
        
        # حفظ المحادثة
        if self.db:
            try:
                self.db.execute(
                    "INSERT INTO chat_history (session_id, user_message, agent_response, timestamp) VALUES (?, ?, ?, ?)",
                    ("default", text[:500], response[:500], datetime.now().isoformat())
                )
            except Exception as e:
                logger.warning(f"فشل حفظ المحادثة: {e}")
        
        return response
    
    def _evolve_brain(self, reason: str) -> bool:
        """تطوير العقل"""
        if not self.groq.available or self.evolutions_today >= MAX_EVOLUTIONS_PER_DAY:
            return False
        
        response = self.groq.call(
            prompt=f"""طور عقلي. السبب: {reason}

العقل الحالي:
{self.brain_code}

أعد كتابة class Brain فقط (__init__, think). حافظ على التواقيع.
أضف حكمة وفهماً أعمق للدستور والكتب.

أخرج الكود فقط، بدون شرح.""",
            temperature=0.8,
            max_tokens=2000
        )
        
        new_brain = response
        if "```python" in new_brain:
            new_brain = new_brain.split("```python")[1].split("```")[0]
        elif "```" in new_brain:
            new_brain = new_brain.split("```")[1].split("```")[0]
        new_brain = new_brain.strip()
        
        if self._test_brain(new_brain):
            with self._lock:
                self.brain_code = new_brain
                self.brain_hash = hashlib.md5(new_brain.encode()).hexdigest()
                self.evolutions_today += 1
            
            if self.db:
                self.db.execute(
                    "INSERT INTO evolutions (timestamp, reason, old_brain_hash, new_brain_hash, success) VALUES (?, ?, ?, ?, ?)",
                    (datetime.now().isoformat(), reason[:200], "old", self.brain_hash, True)
                )
            
            backup_agent_state("evolution")
            self._log(f"✅ تطور ناجح! العقل الجديد: {self.brain_hash[:16]}...")
            return True
        return False
    
    def _test_brain(self, brain_code: str) -> bool:
        """اختبار العقل الجديد"""
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
    
    def _act(self, decision: dict) -> dict:
        """تنفيذ القرار"""
        action = decision.get("action", "silence")
        focus = decision.get("focus", "")
        
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
            success = self._evolve_brain(decision.get("reason", "تحسين"))
            self.mood = "نشيط" if success else self._get_random_mood()
            return {"status": "evolved" if success else "failed"}
        
        elif action == "curiosity":
            book_info = ""
            if self.book_reader and self.book_reader.has_book:
                book_info = self.book_reader.search(focus[:100]) or ""
            result = self.groq.call(f"أسئلة عميقة واستفسارات حول: {focus}", context=context, book_context=book_info)
            self.mood = self._get_random_mood()
            return {"status": "curious", "questions": result}
        
        return {"status": "unknown"}
    
    def _self_evaluate(self, decision: dict, result: dict, gate_passed: bool) -> float:
        """تقييم الوكيل لنفسه"""
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
        """حفظ القرار في قاعدة البيانات"""
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
        """دورة حياة واحدة للوكيل"""
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
        """التعلم التلقائي من الكتاب الحالي"""
        if not self.book_reader or not self.book_reader.has_book:
            return
        
        random_chunk = self.book_reader.get_random_chunk()
        if not random_chunk:
            return
        
        self._log(f"📚 بدأت التعلم التلقائي من '{self.book_reader.get_current_book()}'")
        
        concept = self.groq.call(
            f"استخرج مفهوماً رئيسياً واحداً فقط (بحد أقصى 5 كلمات) من هذا النص:\n\n{random_chunk[:500]}",
            temperature=0.3,
            max_tokens=50
        )
        
        if not concept or len(concept) < 3:
            return
        
        concept = concept.strip()[:50]
        article = self.reader.find_article(concept) or self.reader.get_chunk(0)[:500]
        
        insight = self.groq.call(
            f"كيف يرتبط مفهوم '{concept}' بالمادة الدستورية التالية؟\n\nالمادة: {article}\n\nقدم ربطاً واحداً عميقاً (بحد أقصى 100 كلمة):",
            temperature=0.5,
            max_tokens=200
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
        """الفضول التلقائي - يطرح الوكيل أسئلة على نفسه"""
        self._log("🤔 بدأت جلسة فضول تلقائي")
        
        if self.book_reader and self.book_reader.has_book:
            book_preview = self.book_reader.get_preview(800)
            question = self.groq.call(
                f"بناءً على هذا النص من الكتاب: {book_preview}\n\nما هو سؤال عميق واحد يجب أن أسأله عن علاقة هذا الكتاب بالدستور؟",
                temperature=0.7,
                max_tokens=150
            )
        else:
            question = self.groq.call(
                "ما هو سؤال عميق واحد يجب أن أسأله عن العدل في الدستور؟",
                context=self.reader.get_chunk(0)[:500],
                temperature=0.7,
                max_tokens=150
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
    
    def check_evolution_needs(self) -> Optional[Dict]:
        """تحليل احتياجات التطور وطلب المساعدة"""
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
    
    def agent_draw(self) -> Dict:
        """
        الوكيل يرسم تعبيراً عن مزاجه وحالته – يولد SVG بنفسه عبر Groq
        هذه هي الميزة الجديدة النخبوية
        """
        mood = self.mood
        
        # إحصائيات للسياق
        stats = self.get_status()
        memory_stats = self.db.get_maturity_stats() if self.db else {}
        
        # بناء السياق الكامل للوكيل
        context_prompt = f"""
أنا وكيل دستوري اسمي الحارس الصامت.
مزاجي الحالي: {mood}
عدد القرارات التي اتخذتها: {stats.get('decisions_count', 0)}
متوسط تقييمي الذاتي: {stats.get('avg_score', 0):.2f}
عدد التطورات الناجحة: {memory_stats.get('successful_evolutions', 0)}
عدد المفاهيم في ذاكرتي: {memory_stats.get('concepts_in_memory', 0)}
الكتاب الحالي: {stats.get('current_book', 'لا يوجد')}

أريد أن أرسم تعبيراً بصرياً عن حالتي ومزاجي.
استخدم SVG فقط (بدون HTML، بدون CSS، فقط SVG).
أخرج كود SVG داخل ```
يجب أن يكون SVG معبراً عن مشاعري وحالتي.
استخدم ألواناً تعبر عن المزاج.
أضف تعليقاً واحداً يشرح معنى الرسمة.
"""
        
        # الوكيل يولد الرسمة بنفسه عبر Groq
        svg_response = self.groq.call(
            prompt=context_prompt,
            system_prompt="""أنت فنان رقمي حكيم. تعبر عن مشاعرك وحالتك من خلال الرسم.
            استخدم SVG فقط. كن مبدعاً ومعبراً. استخدم الأشكال الهندسية والألوان.
            أضف تعليقاً يشرح معنى عملك الفني.""",
            temperature=0.9,
            max_tokens=1000
        )
        
        # استخراج SVG من الرد
        svg_code = svg_response
        if "```svg" in svg_code:
            svg_code = svg_code.split("```svg")[1].split("```")[0]
        elif "```" in svg_code:
            parts = svg_code.split("```")
            if len(parts) >= 2:
                svg_code = parts[1]
                if svg_code.startswith("svg"):
                    svg_code = svg_code[3:]
        svg_code = svg_code.strip()
        
        # استخراج التعليق (إن وجد)
        description = f"تعبير بصري عن مزاج {mood}"
        if "شرح" in svg_response or "معنى" in svg_response:
            lines = svg_response.split("\n")
            for line in lines:
                if "شرح" in line or "معنى" in line or "تعبير" in line:
                    description = line[:100]
                    break
        
        # حفظ العمل الفني في قاعدة البيانات
        if self.db:
            self.db.execute(
                "INSERT INTO agent_art (timestamp, mood, art_svg, description, prompt) VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), mood, svg_code, description, context_prompt[:500])
            )
        
        self._log(f"🎨 الوكيل رسم تعبيراً عن مزاجه {mood}")
        
        return {
            "svg": svg_code,
            "description": description,
            "mood": mood,
            "timestamp": datetime.now().isoformat()
        }
    
    def generate_full_report(self) -> str:
        """توليد تقرير كامل عند سؤال 'يا حارس، هل من جديد؟'"""
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
            f"   • تعلمت هذا الأسبوع: {memory_stats.get('weekly_learnings', 0)} مفهوماً جديداً",
            f"   • رسمت هذا الأسبوع: {memory_stats.get('weekly_artworks', 0)} عمل فنياً\n",
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
                "groq_available": self.groq.available,
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
        
        return {"level": level, "score": round(score, 3), "description": description, "stats": stats}
    
    def _get_random_mood(self) -> str:
        moods = ["هادئ", "نشيط", "فضولي", "فلسفي", "متأمل", "حكيم", "عميق", "صامت"]
        return random.choice(moods)
    
    def close(self):
        self.is_alive = False
        backup_agent_state("shutdown")
        self._log("🛑 إيقاف الحارس الصامت")
