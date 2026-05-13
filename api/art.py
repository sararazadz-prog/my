# ============================================================
# نقاط نهاية الرسم والفن
# ============================================================

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from agent.living_mind import LivingMind
from utils.security import limiter

router = APIRouter(tags=["Art"])


@router.get("/agent-art")
@limiter.limit("30/minute")
async def get_agent_art(request: Request, mind: LivingMind):
    """الحصول على تعبير الوكيل البصري الحالي"""
    if not mind:
        return JSONResponse({
            "svg": "<svg width='200' height='200'><circle cx='100' cy='100' r='50' fill='#667eea'/></svg>",
            "description": "بداية الرحلة - تعبير بسيط",
            "mood": "هادئ",
            "timestamp": ""
        })
    
    return JSONResponse(mind.agent_draw())


@router.get("/art-history")
@limiter.limit("30/minute")
async def get_art_history(request: Request, mind: LivingMind, limit: int = 10):
    """سجل أعمال الوكيل الفنية"""
    if not mind or not mind.db:
        return JSONResponse({"artworks": []})
    
    rows = mind.db.fetch_all(
        "SELECT timestamp, mood, description, art_svg FROM agent_art ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    
    artworks = []
    for row in rows:
        artworks.append({
            "timestamp": row[0],
            "mood": row[1],
            "description": row[2],
            "svg": row[3][:500] + "..." if len(row[3]) > 500 else row[3]
        })
    
    return JSONResponse({"artworks": artworks})
