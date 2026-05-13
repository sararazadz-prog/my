# ============================================================
# الحارس الصامت – Silent Guardian
# النسخة النخبوية النهائية v5.0
# ============================================================
# الميزات الجديدة:
# 1. إعادة هيكلة كاملة إلى وحدات (modules)
# 2. الوكيل يرسم SVG بنفسه عبر Groq (إبداع حقيقي)
# 3. Rate limiting للحماية من الطلبات المفرطة
# 4. Logging middleware لتسجيل كل الطلبات
# 5. فصل الواجهة إلى ملف HTML منفصل
# ============================================================

import os
import time
import random
import threading
import requests
import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

import sqlite3

# إعدادات
from config import (
    GROQ_API_KEY, GITHUB_TOKEN, PERSISTENT_DIR, QURAN_URL,
    CONSTITUTION_FILE, DB_PATH, LEARNING_INTERVAL, CURIOSITY_INTERVAL,
    EVOLUTION_CHECK_INTERVAL, BOOKS_DIR
)

# الأدوات
from utils.logging import log_requests_middleware, logger
from utils.security import setup_rate_limiting, limiter

# قاعدة البيانات
from database.db_manager import DatabaseManager

# GitHub
from github.backup import restore_agent_state, backup_agent_state

# الوكيل
from agent.living_mind import LivingMind
from agent.book_reader import BookReader
from agent.memory import ConstitutionalMemory

# API routes
from api.chat import router as chat_router
from api.books import router as books_router
from api.status import router as status_router
from api.art import router as art_router

# إنشاء التطبيق
app = FastAPI(title="الحارس الصامت - Silent Guardian", version="5.0.0")

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

# متغيرات عامة
mind: LivingMind = None
db: DatabaseManager = None
book_reader: BookReader = None
background_thread: threading.Thread = None
background_running = True


# ============================================================
# حلقة الخلفية
# ============================================================

def background_loop():
    global mind, background_running
    logger.info("🟢 بدء حلقة الخلفية المتكاملة v5.0")
    time.sleep(15)
    
    last_learn = time.time()
    last_curiosity = time.time()
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


# ============================================================
# تشغيل التطبيق
# ============================================================

@app.on_event("startup")
async def startup_event():
    global mind, db, book_reader, background_thread
    logger.info("=" * 70)
    logger.info("🚀 تشغيل الحارس الصامت - النسخة النخبوية v5.0")
    logger.info("=" * 70)

    # إنشاء المجلدات
    os.makedirs(PERSISTENT_DIR, exist_ok=True)
    os.makedirs(BOOKS_DIR, exist_ok=True)
    os.makedirs("templates", exist_ok=True)

    # استعادة الحالة من GitHub
    restore_agent_state()

    # تهيئة قاعدة البيانات
    try:
        db = DatabaseManager(DB_PATH)
        logger.info("✅ قاعدة البيانات جاهزة")
    except Exception as e:
        logger.error(f"❌ فشل قاعدة البيانات: {e}")
        return

    # تهيئة قارئ الكتب
    book_reader = BookReader()

    # تهيئة الذاكرة
    memory = ConstitutionalMemory(db)

    # تحميل الدستور
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

    # إنشاء الوكيل
    try:
        mind = LivingMind(
            constitution_text=constitution_text,
            db=db,
            book_reader=book_reader,
            verbose=True
        )
        mind.memory = memory
        logger.info("✅ الوكيل جاهز")
    except Exception as e:
        logger.error(f"❌ فشل إنشاء الوكيل: {e}")
        return

    # تشغيل حلقة الخلفية
    background_thread = threading.Thread(target=background_loop, daemon=True)
    background_thread.start()
    
    # نسخ احتياطي أولي
    backup_agent_state("startup")

    logger.info("=" * 70)
    logger.info("✨ الحارس الصامت v5.0 يعمل الآن")
    logger.info("   • يتعلم تلقائياً من الكتب")
    logger.info("   • فضول تلقائي ويسجل أسئلته")
    logger.info("   • يعبر عن نفسه بالرسم (SVG)")
    logger.info("   • ينسخ المحادثات كاملة")
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

# تضمين الـ API routes
app.include_router(chat_router)
app.include_router(books_router)
app.include_router(status_router)
app.include_router(art_router)


# تبعية للحصول على الـ mind
async def get_mind() -> LivingMind:
    if not mind:
        raise HTTPException(status_code=503, detail="الوكيل لا يزال يبدأ")
    return mind


@app.get("/", response_class=HTMLResponse)
@limiter.limit("30/minute")
async def chat_page(request: Request):
    """الواجهة الرئيسية - تعرض الشات واللوحة الفنية للوكيل"""
    global mind
    
    if not mind:
        return HTMLResponse("<h1>⏳ جاري تشغيل الوكيل...</h1>", status_code=503)
    
    status = mind.get_status()
    maturity = mind.get_maturity_level()
    
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
        "version": "5.0.0"
    }
    
    return templates.TemplateResponse("index.html", context)


# ============================================================
# نقاط نهاية إضافية
# ============================================================

@app.get("/health")
@limiter.limit("60/minute")
async def health(request: Request):
    global mind
    return {
        "status": "alive",
        "version": "5.0.0",
        "constitution_loaded": bool(mind and mind.sacred_text),
        "groq_configured": bool(GROQ_API_KEY),
        "mood": mind.mood if mind else "unknown"
    }


@app.post("/manual-backup")
@limiter.limit("5/minute")
async def manual_backup(request: Request):
    backup_agent_state("manual")
    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
