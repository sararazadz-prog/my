# ============================================================
# نقاط نهاية الحالة والإحصائيات
# ============================================================

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from utils.security import limiter

router = APIRouter(tags=["Status"])


@router.get("/status")
@limiter.limit("30/minute")
async def get_status(request: Request):
    from main import mind as global_mind
    mind = global_mind
    
    if not mind:
        return JSONResponse({"ready": False})
    return JSONResponse(mind.get_status())


@router.get("/maturity")
@limiter.limit("30/minute")
async def get_maturity(request: Request):
    from main import mind as global_mind
    mind = global_mind
    
    if not mind:
        return JSONResponse({"level": "unknown", "score": 0})
    return JSONResponse(mind.get_maturity_level())


@router.get("/current-book")
@limiter.limit("30/minute")
async def get_current_book(request: Request):
    from main import book_reader as global_book_reader
    book_reader = global_book_reader
    
    if not book_reader:
        return JSONResponse({"error": "قارئ الكتب غير جاهز"})
    return JSONResponse({
        "current_book": book_reader.get_current_book(),
        "has_book": book_reader.has_book,
        "text_length": len(book_reader.current_book_text),
        "chunks": len(book_reader.chunks)
    })


@router.get("/constitution-excerpt")
@limiter.limit("30/minute")
async def constitution_excerpt(request: Request):
    from main import mind as global_mind
    mind = global_mind
    
    if mind and mind.sacred_text:
        return JSONResponse({
            "exists": True,
            "length": len(mind.sacred_text),
            "hash": mind.reader.hash[:16] if hasattr(mind.reader, 'hash') else "unknown",
            "preview": mind.sacred_text[:500]
        })
    return JSONResponse({"exists": False})


@router.get("/learning-log")
@limiter.limit("30/minute")
async def get_learning_log(request: Request, limit: int = 20):
    from main import mind as global_mind
    mind = global_mind
    
    if not mind or not mind.db:
        return JSONResponse({"logs": []})
    rows = mind.db.fetch_all(
        "SELECT timestamp, concept, book_name, insight FROM auto_learning_log ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    return JSONResponse({
        "logs": [{"timestamp": r[0], "concept": r[1], "book": r[2], "insight": r[3]} for r in rows]
    })
