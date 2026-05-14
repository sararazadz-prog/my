import os
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from app.utils.security import limiter
from app.config import MAX_BOOK_SIZE

router = APIRouter(tags=["Books"])


@router.post("/upload-book")
@limiter.limit("5/minute")
async def upload_book(request: Request, file: UploadFile = File(...)):
    from app.main import get_book_reader_safe, backup_agent_state
    book_reader = await get_book_reader_safe()

    if not book_reader:
        raise HTTPException(status_code=503, detail="قارئ الكتب غير جاهز")

    content = await file.read()
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="الملف صغير جداً")
    if len(content) > MAX_BOOK_SIZE:
        raise HTTPException(status_code=400, detail=f"الكتاب كبير جداً (حد أقصى {MAX_BOOK_SIZE // (1024*1024)}MB)")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.txt', '.pdf']:
        raise HTTPException(status_code=400, detail="نوع ملف غير مدعوم. استخدم TXT أو PDF")

    try:
        if ext == '.pdf':
            success, message = book_reader.load_book_from_pdf(file.filename, content)
        else:
            success, message = book_reader.load_book_from_txt(file.filename, content)

        if success:
            backup_agent_state("new_book")
            return JSONResponse({"status": "success", "message": message})
        raise HTTPException(status_code=500, detail=message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
