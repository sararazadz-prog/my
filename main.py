# ============================================================
# الحارس الصامت – Silent Guardian
# النسخة النخبوية النهائية v5.2
# ============================================================
# التعديلات النخبوية في هذه النسخة:
# 1. تصحيح استيراد git_backup بدلاً من github (حل تعارض التسمية)
# 2. إضافة مسار المشروع إلى PYTHONPATH لضمان عمل الاستيرادات
# 3. استخدام asyncio.Lock للمتغيرات العامة (أمان في البيئة السحابية)
# 4. دالة get_mind_safe آمنة للاستخدام عبر الطلبات
# 5. تحسين إدارة الأخطاء في بدء التشغيل
# 6. توافق كامل مع Render وبيئة Docker
# ============================================================

import sys
from pathlib import Path

# 🔑 الإصلاح الأول: إضافة مجلد المشروع إلى مسار البحث عن الحزم
# هذا السطر يحل مشكلة "module not found" في بيئة Render
sys.path.insert(0, str(Path(__file__).parent))

import os
import time
import random
import threading
import asyncio
import requests
import hashlib
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

# ============================================================
# الاستيرادات الداخلية (بعد تعديل مسار PYTHONPATH)
# ============================================================
from config import (
    GROQ_API_KEY, GITHUB_TOKEN, PERSISTENT_DIR, QURAN_URL,
    CONSTITUTION_FILE, DB_PATH, LEARNING_INTERVAL, CURIOSITY_INTERVAL,
    EVOLUTION_CHECK_INTERVAL, BOOKS_DIR
)

from utils.logging import log_requests_middleware, logger
from utils.security import setup_rate_limiting, limiter
from database.db_manager import DatabaseManager

# 🔑 الإصلاح الثاني: استخدام المجلد الجديد git_backup بدلاً من github
from git_backup.backup import restore_agent_state, backup_agent_state

from agent.living_mind import LivingMind
from agent.book_reader import BookReader
from agent.memory import ConstitutionalMemory

# استيراد routers من مجلد api
from api.chat import router as chat_router
from api.books import router as books_router
from api.status import router as status_router
from api.art import router as art_router


# ============================================================
# إدارة المتغيرات العامة بشكل آمن (Thread-Safe)
# ============================================================

# المتغيرات العامة
_mind: Optional[LivingMind] = None
_db: Optional[DatabaseManager] = None
_book_reader: Optional[BookReader] = None
_background_thread: Optional[threading.Thread] = None
_background_running: bool = True

# قفل للتحكم في الوصول إلى المتغيرات (آمن في البيئة السحابية)
_mind_lock = asyncio.Lock()
_db_lock = asyncio.Lock()
_book_reader_lock = asyncio.Lock()


async def set_mind(mind_instance: Optional[LivingMind]) -> None:
    """تعيين الوكيل بشكل آمن"""
    global _mind
    async with _mind_lock:
        _mind = mind_instance


async def get_mind_safe() -> Optional[LivingMind]:
    """الحصول على الوكيل بشكل آمن"""
    async with _mind_lock:
        return _mind


async def set_db(db_instance: Optional[DatabaseManager]) -> None:
    """تعيين قاعدة البيانات بشكل آمن"""
    global _db
    async with _db_lock:
        _db = db_instance


async def get_db_safe() -> Optional[DatabaseManager]:
    """الحصول على قاعدة البيانات بشكل آمن"""
    async with _db_lock:
        return _db


async def set_book_reader(reader_instance: Optional[BookReader]) -> None:
    """تعيين قارئ الكتب بشكل آمن"""
    global _book_reader
    async with _book_reader_lock:
        _book_reader = reader_instance


async def get_book_reader_safe() -> Optional[BookReader]:
    """الحصول على قارئ الكتب بشكل آمن"""
    async with _book_reader_lock:
        return _book_reader


def set_background_running(value: bool) -> None:
    """تعيين حالة حلقة الخلفية"""
    global _background_running
    _background_running = value


def is_background_running() -> bool:
    """التحقق من حالة حلقة الخلفية"""
    return _background_running


# ============================================================
# حلقة الخلفية (تعمل في Thread منفصل)
# ============================================================

def background_loop():
    """حلقة الخلفية المتكاملة – قرارات + تعلم + فضول"""
    logger.info("🟢 بدء حلقة الخلفية المتكاملة v5.2")
    time.sleep(15)
    
    last_learn = time.time()
    last_curiosity = time.time()
    last_evolution_check = time.time()
    
    # حلقة لا نهائية
    while is_background_running():
        # الحصول على الوكيل الحالي (آمن)
        current_mind = None
        try:
            # لا يمكن استخدام await هنا، نستخدم حلقة حدث منفصلة
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            current_mind = loop.run_until_complete(get_mind_safe())
            loop.close()
        except Exception as e:
            logger.error(f"خطأ في الحصول على الوكيل: {e}")
            time.sleep(60)
            continue
        
        if not current_mind:
            time.sleep(10)
            continue
            
        try:
            # دورة حياة الوكيل
            result = current_mind.live_step()
            if result and result.get("iteration", 0) % 10 == 0:
                logger.info(f"📊 الدورة {result['iteration']} | {result['action']} | النتيجة {result['score']:.2f} | مزاج: {result['mood']}")

            # التعلم التلقائي من الكتب
            if time.time() - last_learn > LEARNING_INTERVAL:
                current_mind.auto_learn_from_book()
                last_learn = time.time()

            # الفضول التلقائي
            if time.time() - last_curiosity > CURIOSITY_INTERVAL:
                current_mind.auto_curiosity()
                last_curiosity = time.time()

            # فحص احتياجات التطور
            if time.time() - last_evolution_check > EVOLUTION_CHECK_INTERVAL:
                need = current_mind.check_evolution_needs()
                if need:
                    current_mind.question_manager.add_question(
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


# ============================================================
# إنشاء تطبيق FastAPI
# ============================================================

# استخدام lifespan لإدارة دورة حياة التطبيق (بديل عن on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    """إدارة بدء وإيقاف التطبيق"""
    global _background_thread
    
    logger.info("=" * 70)
    logger.info("🚀 تشغيل الحارس الصامت - النسخة النخبوية v5.2")
    logger.info("=" * 70)

    # إنشاء المجلدات
    os.makedirs(PERSISTENT_DIR, exist_ok=True)
    os.makedirs(BOOKS_DIR, exist_ok=True)
    os.makedirs("templates", exist_ok=True)

    # استعادة الحالة من GitHub
    restore_agent_state()

    # تهيئة قاعدة البيانات
    db_instance = None
    try:
        db_instance = DatabaseManager(DB_PATH)
        await set_db(db_instance)
        logger.info("✅ قاعدة البيانات جاهزة")
    except Exception as e:
        logger.error(f"❌ فشل قاعدة البيانات: {e}")
        return

    # تهيئة قارئ الكتب
    reader_instance = BookReader()
    await set_book_reader(reader_instance)
    logger.info("✅ قارئ الكتب جاهز")

    # تهيئة الذاكرة
    memory = ConstitutionalMemory(db_instance)

    # تحميل الدستور
    constitution_text = ""
    row = db_instance.fetch_one("SELECT text FROM constitution_cache WHERE id = 1")
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
            db_instance.execute(
                "INSERT OR REPLACE INTO constitution_cache (id, text, hash, updated_at) VALUES (1, ?, ?, ?)",
                (constitution_text, text_hash, datetime.now().isoformat())
            )
        except Exception as e:
            logger.error(f"❌ فشل تحميل القرآن: {e}")

    if constitution_text:
        with open(CONSTITUTION_FILE, 'w', encoding='utf-8') as f:
            f.write(constitution_text)

    # إنشاء الوكيل
    try:
        mind_instance = LivingMind(
            constitution_text=constitution_text,
            db=db_instance,
            book_reader=reader_instance,
            verbose=True
        )
        mind_instance.memory = memory
        await set_mind(mind_instance)
        logger.info("✅ الوكيل جاهز")
    except Exception as e:
        logger.error(f"❌ فشل إنشاء الوكيل: {e}")
        return

    # تشغيل حلقة الخلفية
    _background_thread = threading.Thread(target=background_loop, daemon=True)
    _background_thread.start()
    
    # نسخ احتياطي أولي
    backup_agent_state("startup")

    logger.info("=" * 70)
    logger.info("✨ الحارس الصامت v5.2 يعمل الآن")
    logger.info("   • يتعلم تلقائياً من الكتب")
    logger.info("   • فضول تلقائي ويسجل أسئلته")
    logger.info("   • يعبر عن نفسه بالرسم (SVG)")
    logger.info("   • ينسخ المحادثات كاملة")
    logger.info("   • يستخدم git_backup بدلاً من github (تم حل التعارض)")
    logger.info("=" * 70)
    
    yield  # هنا يعمل التطبيق
    
    # إيقاف التشغيل
    logger.info("🛑 إيقاف الحارس الصامت...")
    set_background_running(False)
    if _background_thread:
        _background_thread.join(timeout=5)
    
    mind_instance = await get_mind_safe()
    if mind_instance:
        mind_instance.close()
    
    db_instance = await get_db_safe()
    if db_instance:
        db_instance.close()
    
    backup_agent_state("shutdown")
    logger.info("✅ تم إيقاف الحارس الصامت")


# ============================================================
# إنشاء التطبيق مع lifespan
# ============================================================

app = FastAPI(
    title="الحارس الصامت - Silent Guardian",
    version="5.2.0",
    lifespan=lifespan
)

# إضافة CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# إضافة middleware لتسجيل الطلبات
app.middleware("http")(log_requests_middleware)

# إعداد Rate Limiting
setup_rate_limiting(app)

# قوالب Jinja2 للواجهة
templates = Jinja2Templates(directory="templates")


# ============================================================
# تبعية للحصول على الوكيل (للاستخدام في API routes)
# ============================================================

async def get_current_mind() -> LivingMind:
    """تبعية FastAPI للحصول على الوكيل الحالي"""
    mind_instance = await get_mind_safe()
    if not mind_instance:
        raise HTTPException(status_code=503, detail="الوكيل لا يزال يبدأ")
    return mind_instance


async def get_current_db() -> DatabaseManager:
    """تبعية FastAPI للحصول على قاعدة البيانات"""
    db_instance = await get_db_safe()
    if not db_instance:
        raise HTTPException(status_code=503, detail="قاعدة البيانات غير جاهزة")
    return db_instance


# ============================================================
# نقاط النهاية الرئيسية
# ============================================================

# تضمين الـ API routes
app.include_router(chat_router)
app.include_router(books_router)
app.include_router(status_router)
app.include_router(art_router)


@app.get("/", response_class=HTMLResponse)
@limiter.limit("30/minute")
async def chat_page(request: Request):
    """الواجهة الرئيسية - تعرض الشات واللوحة الفنية للوكيل"""
    mind_instance = await get_mind_safe()
    
    if not mind_instance:
        return HTMLResponse("<h1>⏳ جاري تشغيل الوكيل...</h1><p>يرجى الانتظار 30 ثانية</p>", status_code=503)
    
    status = mind_instance.get_status()
    maturity = mind_instance.get_maturity_level()
    
    # التحضير للواجهة
    context = {
        "request": request,
        "sacred_length": status.get('sacred_length', 0),
        "groq_available": status.get('groq_available', False),
        "mood": status.get('mood', 'هادئ'),
        "decisions_count": status.get('decisions_count', 0),
        "current_book": status.get('current_book', 'لا يوجد'),
        "pending_questions": status.get('pending_questions', 0),
        "maturity_level": maturity.get('level', 'جنين'),
        "maturity_score": maturity.get('score', 0) * 100,
        "iterations": status.get('iterations', 0),
        "version": "5.2.0"
    }
    
    return templates.TemplateResponse("index.html", context)


@app.get("/health")
@limiter.limit("60/minute")
async def health(request: Request):
    """فحص صحة الخدمة"""
    mind_instance = await get_mind_safe()
    return {
        "status": "alive",
        "version": "5.2.0",
        "constitution_loaded": bool(mind_instance and mind_instance.sacred_text) if mind_instance else False,
        "groq_configured": bool(GROQ_API_KEY),
        "mood": mind_instance.mood if mind_instance else "unknown"
    }


@app.post("/manual-backup")
@limiter.limit("5/minute")
async def manual_backup(request: Request):
    """نسخ احتياطي يدوي"""
    backup_agent_state("manual")
    return {"status": "success"}


# ============================================================
# نقاط نهاية للتصحيح (Debugging)
# ============================================================

@app.get("/debug/importerrors")
async def debug_import_errors():
    """نقطة نهاية لفحص أخطاء الاستيراد (للتصحيح فقط)"""
    import traceback
    errors = {}
    
    modules_to_test = [
        "config", "utils.logging", "utils.security", "database.db_manager",
        "git_backup.backup", "agent.living_mind", "agent.book_reader",
        "agent.memory", "api.chat", "api.books", "api.status", "api.art"
    ]
    
    for module_name in modules_to_test:
        try:
            __import__(module_name)
            errors[module_name] = "✅ OK"
        except Exception as e:
            errors[module_name] = f"❌ {str(e)[:100]}"
            errors[f"{module_name}_traceback"] = traceback.format_exc()[:300]
    
    return {
        "python_path": sys.path,
        "current_directory": str(Path(__file__).parent),
        "modules": errors
    }


@app.get("/debug/variables")
async def debug_variables():
    """نقطة نهاية لعرض المتغيرات العامة (للتصحيح فقط)"""
    mind_instance = await get_mind_safe()
    db_instance = await get_db_safe()
    reader_instance = await get_book_reader_safe()
    
    return {
        "mind_exists": mind_instance is not None,
        "db_exists": db_instance is not None,
        "book_reader_exists": reader_instance is not None,
        "background_running": is_background_running(),
        "persistent_dir": PERSISTENT_DIR,
        "db_path": DB_PATH,
        "github_token_configured": bool(GITHUB_TOKEN),
        "groq_configured": bool(GROQ_API_KEY)
    }


# ============================================================
# تشغيل التطبيق
# ============================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        workers=1
    )
