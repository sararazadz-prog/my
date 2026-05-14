from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.utils.security import limiter
from datetime import datetime

router = APIRouter(tags=["Art"])


@router.get("/agent-art")
@limiter.limit("30/minute")
async def get_agent_art(request: Request):
    from app.main import get_mind_safe
    mind = await get_mind_safe()

    if not mind:
        return JSONResponse({
            "svg": "<svg width='200' height='200'><circle cx='100' cy='100' r='50' fill='#667eea'/></svg>",
            "description": "بداية الرحلة",
            "mood": "هادئ",
            "timestamp": ""
        })

    if hasattr(mind, 'agent_draw'):
        return JSONResponse(mind.agent_draw())
    else:
        return JSONResponse({
            "svg": "<svg width='200' height='200'><circle cx='100' cy='100' r='50' fill='#667eea'/></svg>",
            "description": f"الوكيل في حالة {mind.mood}",
            "mood": mind.mood,
            "timestamp": datetime.now().isoformat()
        })
