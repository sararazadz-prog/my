import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.config import (
    GROQ_API_KEY, GITHUB_TOKEN, PERSISTENT_DIR, QURAN_URL,
    CONSTITUTION_FILE, DB_PATH, LEARNING_INTERVAL, CURIOSITY_INTERVAL,
    EVOLUTION_CHECK_INTERVAL, BOOKS_DIR, BASELINE_FILE
)

from app.utils.logging import log_requests_middleware, logger
from app.utils.security import setup_rate_limiting, limiter
from app.utils.benchmarking import BenchmarkRunner
from app.database.db_manager import DatabaseManager
from app.git_backup.backup import restore_agent_state, backup_agent_state
from app.agent.living_mind import LivingMind
from app.agent.book_reader import BookReader
from app.agent.memory import ConstitutionalMemory

from app.api.chat import router as chat_router
from app.api.books import router as books_router
from app.api.status import router as status_router
from app.api.art import router as art_router

_mind: Optional[LivingMind] = None
_db: Optional[DatabaseManager] = None
_book_reader: Optional[BookReader] = None
_background_thread: Optional[threading.Thread] = None
_background_running: bool = True

_mind_lock = asyncio.Lock()
_db_lock = asyncio.Lock()
_book_reader_lock = asyncio.Lock()


async def set_mind(mind_instance: Optional[LivingMind]) -> None:
    global _mind
    async with _mind_lock:
        _mind = mind_instance


async def get_mind_safe() -> Optional[LivingMind]:
    async with _mind_lock:
        return _mind


async def set_db(db_instance: Optional[DatabaseManager]) -> None:
    global _db
    async with _db_lock:
        _db = db_instance


async def get_db_safe() -> Optional[DatabaseManager]:
    async with _db_lock:
        return _db


async def set_book_reader(reader_instance: Optional[BookReader]) -> None:
    global _book_reader
    async with _book_reader_lock:
        _book_reader = reader_instance


async def get_book_reader_safe() -> Optional[BookReader]:
    async with _book_reader_lock:
        return _book_reader


def set_background_running(value: bool) -> None:
    global _background_running
    _background_running = value


def is_background_running() -> bool:
    return _background_running


def background_loop():
    logger.info("بدء حلقة الخلفية")
    time.sleep(15)

    last_learn = time.time()
    last_curiosity = time.time()
    last_evolution_check = time.time()

    while is_background_running():
        current_mind = None
        try:
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
            if time.time() - last_learn > LEARNING_INTERVAL:
                if hasattr(current_mind, 'auto_learn_from_book'):
                    current_mind.auto_learn_from_book()
                last_learn = time.time()

            if time.time() - last_curiosity > CURIOSITY_INTERVAL:
                if hasattr(current_mind, 'auto_curiosity'):
                    current_mind.auto_curiosity()
                last_curiosity = time.time()

            if time.time() - last_evolution_check > EVOLUTION_CHECK_INTERVAL:
                if hasattr(current_mind, 'check_evolution_needs'):
                    need = current_mind.check_evolution_needs()
                    if need and hasattr(current_mind, 'question_manager'):
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

    logger.info("توقفت حلقة الخلفية")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _background_thread

    logger.info("=" * 70)
    logger.info("تشغيل الحارس الصامت - النسخة النخبوية 5.3.0")
    logger.info("=" * 70)

    os.makedirs(PERSISTENT_DIR, exist_ok=True)
    os.makedirs(BOOKS_DIR, exist_ok=True)
    os.makedirs("app/templates", exist_ok=True)

    restore_agent_state()

    db_instance = None
    try:
        db_instance = DatabaseManager(DB_PATH)
        await set_db(db_instance)
        logger.info("قاعدة البيانات جاهزة")
    except Exception as e:
        logger.error(f"فشل قاعدة البيانات: {e}")
        return

    reader_instance = BookReader()
    await set_book_reader(reader_instance)
    logger.info("قارئ الكتب جاهز")

    memory = ConstitutionalMemory(db_instance)

    constitution_text = ""

    row = db_instance.fetch_one("SELECT text FROM constitution_cache WHERE id = 1")
    if row and row[0]:
        constitution_text = row[0]
        logger.info(f"الدستور من قاعدة البيانات: {len(constitution_text):,} حرفاً")

    if not constitution_text:
        logger.info(f"تحميل القرآن من {QURAN_URL}")
        try:
            response = requests.get(QURAN_URL, timeout=30)
            response.raise_for_status()
            quran_data = response.json()

            for sura in quran_data:
                for verse in sura["verses"]:
                    constitution_text += verse["text"] + "\n"

            logger.info(f"تم تحميل القرآن: {len(constitution_text):,} حرفاً")
            text_hash = hashlib.md5(constitution_text.encode()).hexdigest()
            db_instance.execute(
                "INSERT OR REPLACE INTO constitution_cache (id, text, hash, updated_at) VALUES (1, ?, ?, ?)",
                (constitution_text, text_hash, datetime.now().isoformat())
            )
        except Exception as e:
            logger.error(f"فشل تحميل القرآن: {e}")

    if constitution_text:
        with open(CONSTITUTION_FILE, 'w', encoding='utf-8') as f:
            f.write(constitution_text)

    try:
        mind_instance = LivingMind(
            constitution_text=constitution_text,
            db=db_instance,
            book_reader=reader_instance,
            verbose=True
        )
        mind_instance.memory = memory
        await set_mind(mind_instance)
        logger.info("الوكيل جاهز")
    except Exception as e:
        logger.error(f"فشل إنشاء الوكيل: {e}")
        return

    try:
        benchmark = BenchmarkRunner(BASELINE_FILE, mind_instance)
        baseline = benchmark.run_baseline()
        logger.info(f"Baseline محفوظ: نسبة الهلوسة = {baseline['aggregated_metrics']['hallucination_rate']}")
    except Exception as e:
        logger.warning(f"فشل تشغيل baseline: {e}")

    _background_thread = threading.Thread(target=background_loop, daemon=True)
    _background_thread.start()

    backup_agent_state("startup")

    logger.info("=" * 70)
    logger.info("الحارس الصامت يعمل الآن - بنسخة نخبوية")
    logger.info("=" * 70)

    yield

    logger.info("إيقاف الحارس الصامت...")
    set_background_running(False)

    if _background_thread:
        _background_thread.join(timeout=5)

    mind_instance = await get_mind_safe()
    if mind_instance and hasattr(mind_instance, 'close'):
        mind_instance.close()

    db_instance = await get_db_safe()
    if db_instance:
        db_instance.close()

    backup_agent_state("shutdown")
    logger.info("تم إيقاف الحارس الصامت")


app = FastAPI(title="الحارس الصامت", version="5.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(log_requests_middleware)
setup_rate_limiting(app)

templates = Jinja2Templates(directory="app/templates")


async def get_current_mind() -> LivingMind:
    mind_instance = await get_mind_safe()
    if not mind_instance:
        raise HTTPException(status_code=503, detail="الوكيل لا يزال يبدأ")
    return mind_instance


async def get_current_db() -> DatabaseManager:
    db_instance = await get_db_safe()
    if not db_instance:
        raise HTTPException(status_code=503, detail="قاعدة البيانات غير جاهزة")
    return db_instance


app.include_router(chat_router)
app.include_router(books_router)
app.include_router(status_router)
app.include_router(art_router)


@app.get("/", response_class=HTMLResponse)
@limiter.limit("30/minute")
async def chat_page(request: Request):
    mind_instance = await get_mind_safe()

    if not mind_instance:
        return HTMLResponse("<h1>جاري تشغيل الوكيل...</h1><p>يرجى الانتظار 30 ثانية</p>", status_code=503)

    status = mind_instance.get_status()
    maturity = mind_instance.get_maturity_level()

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
        "version": "5.3.0"
    }

    return templates.TemplateResponse("index.html", context)


@app.get("/health")
@limiter.limit("60/minute")
async def health(request: Request):
    mind_instance = await get_mind_safe()
    return {
        "status": "alive",
        "version": "5.3.0",
        "constitution_loaded": bool(mind_instance and mind_instance.sacred_text) if mind_instance else False,
        "groq_configured": bool(GROQ_API_KEY),
        "mood": mind_instance.mood if mind_instance else "unknown",
        "sandbox_ready": True
    }


@app.post("/manual-backup")
@limiter.limit("5/minute")
async def manual_backup(request: Request):
    backup_agent_state("manual")
    return {"status": "success"}


@app.post("/run-benchmark")
@limiter.limit("5/minute")
async def run_benchmark(request: Request):
    mind_instance = await get_mind_safe()
    if not mind_instance:
        return JSONResponse({"error": "الوكيل غير جاهز"}, status_code=503)

    benchmark = BenchmarkRunner(BASELINE_FILE, mind_instance)
    baseline = benchmark.run_baseline()

    return JSONResponse({
        "status": "success",
        "hallucination_rate": baseline['aggregated_metrics']['hallucination_rate'],
        "avg_response_time_ms": baseline['aggregated_metrics']['avg_response_time_ms']
    })


@app.get("/debug/importerrors")
async def debug_import_errors():
    import traceback
    errors = {}

    modules_to_test = [
        "app.config", "app.utils.logging", "app.utils.security", "app.utils.benchmarking",
        "app.database.db_manager", "app.git_backup.backup", "app.agent.living_mind",
        "app.agent.sacred_reader", "app.agent.book_reader", "app.agent.memory",
        "app.api.chat", "app.api.books", "app.api.status", "app.api.art",
        "docker_sandbox.sandbox_wrapper"
    ]

    for module_name in modules_to_test:
        try:
            __import__(module_name)
            errors[module_name] = "OK"
        except Exception as e:
            errors[module_name] = f"خطأ: {str(e)[:100]}"
            errors[f"{module_name}_traceback"] = traceback.format_exc()[:300]

    return {
        "python_path": sys.path,
        "current_directory": str(Path(__file__).parent),
        "modules": errors
    }


@app.get("/debug/variables")
async def debug_variables():
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
        "baseline_file": BASELINE_FILE,
        "github_token_configured": bool(GITHUB_TOKEN),
        "groq_configured": bool(GROQ_API_KEY),
        "sandbox_available": True
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
