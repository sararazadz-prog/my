# ============================================================
# نقاط نهاية الشات
# ============================================================

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from agent.living_mind import LivingMind
from utils.security import limiter
from datetime import datetime

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    message: str


class FeedbackRequest(BaseModel):
    chat_id: int
    feedback: bool


class AnswerRequest(BaseModel):
    question_id: int
    answer: str


@router.post("/chat")
@limiter.limit("10/minute")
async def chat(request: Request, req: ChatRequest, mind: LivingMind = Depends(lambda: None)):
    """نقطة نهاية المحادثة الرئيسية"""
    # سيتم حقن mind من main.py
    from main import mind as global_mind
    mind = global_mind
    
    if not mind or not mind.sacred_text:
        return JSONResponse({"response": "الوكيل لا يزال يبدأ، حاول مرة أخرى.", "chat_id": None})

    try:
        if "يا حارس" in req.message and ("جديد" in req.message or "تقرير" in req.message):
            report = mind.generate_full_report()
            return JSONResponse({"response": report, "chat_id": None})

        response = mind.reflect_on(req.message)

        chat_id = None
        if mind.db:
            row = mind.db.fetch_one("SELECT id FROM chat_history ORDER BY id DESC LIMIT 1")
            if row:
                chat_id = row[0]

        return JSONResponse({"response": response, "chat_id": chat_id})
    except Exception as e:
        return JSONResponse({"response": f"❌ خطأ: {str(e)[:100]}", "chat_id": None})


@router.post("/feedback")
@limiter.limit("20/minute")
async def submit_feedback(request: Request, req: FeedbackRequest):
    from main import mind as global_mind
    mind = global_mind
    
    if not mind or not mind.db:
        return JSONResponse({"status": "error", "message": "الوكيل غير جاهز"})

    try:
        mind.db.execute(
            "INSERT INTO user_feedback (chat_id, feedback, timestamp) VALUES (?, ?, ?)",
            (req.chat_id, 1 if req.feedback else 0, datetime.now().isoformat())
        )
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})


@router.get("/pending-questions")
@limiter.limit("20/minute")
async def get_pending_questions(request: Request):
    from main import mind as global_mind
    mind = global_mind
    
    if not mind:
        return JSONResponse({"questions": []})
    questions = mind.question_manager.get_all_unanswered()
    return JSONResponse({"questions": questions})


@router.post("/answer-question")
@limiter.limit("10/minute")
async def answer_question(request: Request, req: AnswerRequest):
    from main import mind as global_mind
    mind = global_mind
    
    if not mind:
        return JSONResponse({"status": "error"})

    mind.question_manager.mark_answered(req.question_id, req.answer)

    if "نعم" in req.answer or "أريد" in req.answer or "تطور" in req.answer:
        mind._evolve_brain(f"المستخدم وافق على: {req.answer[:100]}")

    return JSONResponse({"status": "success"})
