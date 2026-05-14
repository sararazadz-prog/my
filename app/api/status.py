from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.utils.security import limiter

router = APIRouter(tags=["Status"])


@router.get("/status")
@limiter.limit("30/minute")
async def get_status(request: Request):
    from app.main import get_mind_safe
    mind = await get_mind_safe()

    if not mind:
        return JSONResponse({"ready": False})
    return JSONResponse(mind.get_status())


@router.get("/maturity")
@limiter.limit("30/minute")
async def get_maturity(request: Request):
    from app.main import get_mind_safe
    mind = await get_mind_safe()

    if not mind:
        return JSONResponse({"level": "unknown", "score": 0})
    return JSONResponse(mind.get_maturity_level())


@router.get("/metrics")
@limiter.limit("30/minute")
async def get_metrics(request: Request):
    from app.main import get_mind_safe
    from app.config import BASELINE_FILE
    import json
    import os

    mind = await get_mind_safe()
    if not mind:
        return JSONResponse({"error": "الوكيل غير جاهز"})

    metrics = {
        "current": {
            "total_iterations": mind.iteration,
            "evolutions_today": mind.evolutions_today,
            "current_mood": mind.mood,
            "has_book": mind.book_reader.has_book if mind.book_reader else False
        },
        "database_stats": mind.db.get_maturity_stats() if mind.db else {},
        "baseline": None
    }

    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE, 'r', encoding='utf-8') as f:
            metrics["baseline"] = json.load(f)

    return JSONResponse(metrics)


@router.get("/current-book")
@limiter.limit("30/minute")
async def get_current_book(request: Request):
    from app.main import get_book_reader_safe
    book_reader = await get_book_reader_safe()

    if not book_reader:
        return JSONResponse({"error": "قارئ الكتب غير جاهز"})
    return JSONResponse({
        "current_book": book_reader.get_current_book(),
        "has_book": book_reader.has_book,
        "text_length": len(book_reader.current_book_text) if book_reader.current_book_text else 0,
        "chunks": len(book_reader.chunks) if hasattr(book_reader, 'chunks') else 0
    })
