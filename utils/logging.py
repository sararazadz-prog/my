# ============================================================
# إعدادات التسجيل المتقدمة
# ============================================================

import logging
import time
from fastapi import Request
from typing import Callable
import json

# إعداد التسجيل الأساسي
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

# Middleware لتسجيل كل طلب
async def log_requests_middleware(request: Request, call_next: Callable):
    """تسجيل جميع طلبات API مع وقت الاستجابة"""
    start_time = time.time()
    
    # تسجيل الطلب
    logger.info(f"📨 {request.method} {request.url.path} from {request.client.host}")
    
    response = await call_next(request)
    
    # تسجيل وقت الاستجابة
    process_time = time.time() - start_time
    logger.info(f"✅ {request.method} {request.url.path} -> {response.status_code} ({process_time:.3f}s)")
    
    response.headers["X-Process-Time"] = str(process_time)
    return response
