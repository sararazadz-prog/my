from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime
from app.utils.security import limiter

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    message: str


class FeedbackRequest(BaseModel):
    chat_id: int
    feedback: bool


@router.post("/chat")
@limiter.limit("10/minute")
async def chat(request: Request, req: ChatRequest):
    from app.main import get_mind_safe
    mind = await get_mind_safe()

    if not mind or not mind.sacred_text:
        return JSONResponse({"response": "الوكيل لا يزال يبدأ، حاول مرة أخرى.", "chat_id": None})

    try:
        response = mind.reflect_on(req.message)

        chat_id = None
        if mind.db:
            row = mind.db.fetch_one("SELECT id FROM chat_history ORDER BY id DESC LIMIT 1")
            if row:
                chat_id = row[0]

        return JSONResponse({"response": response, "chat_id": chat_id})
    except Exception as e:
        return JSONResponse({"response": f"خطأ: {str(e)[:100]}", "chat_id": None})


@router.post("/feedback")
@limiter.limit("20/minute")
async def submit_feedback(request: Request, req: FeedbackRequest):
    from app.main import get_mind_safe
    mind = await get_mind_safe()

    if not mind or not mind.db:
        return JSONResponse({"status": "error", "message": "الوكيل غير جاهز"})

    try:
        mind.db.execute(
            "INSERT INTO user_feedback (chat_id, feedback, timestamp) VALUES (?, ?, ?)",
            (req.chat_id, 1 if req.feedback else 0, datetime.now().isoformat())
        )

        mind.update_from_feedback(req.chat_id, req.feedback)

        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})


@router.get("/pending-questions")
@limiter.limit("20/minute")
async def get_pending_questions(request: Request):
    from app.main import get_mind_safe
    mind = await get_mind_safe()

    if not mind:
        return JSONResponse({"questions": []})
    questions = mind.question_manager.get_all_unanswered()
    return JSONResponse({"questions": questions})
