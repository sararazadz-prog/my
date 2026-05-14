import logging
import time
from fastapi import Request
from typing import Callable

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


async def log_requests_middleware(request: Request, call_next: Callable):
    start_time = time.time()
    logger.info(f"طلب: {request.method} {request.url.path}")
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"رد: {request.method} {request.url.path} -> {response.status_code} ({process_time:.3f}s)")
    response.headers["X-Process-Time"] = str(process_time)
    return response
