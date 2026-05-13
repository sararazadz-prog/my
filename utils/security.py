# ============================================================
# نظام الأمان والحماية
# ============================================================

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request, HTTPException
from config import MAX_REQUESTS_PER_MINUTE

# تهيئة Rate Limiter
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{MAX_REQUESTS_PER_MINUTE}/minute"])

def setup_rate_limiting(app: FastAPI):
    """تفعيل نظام حماية الطلبات"""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

def get_client_ip(request: Request) -> str:
    """الحصول على IP العميل بشكل آمن"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0]
    return request.client.host
