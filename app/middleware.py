"""Middleware для rate limiting у POST /bookings.

Использует простой sliding window counter в Redis.
"""

import time

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint
)

from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Ограничивает число POST-запросов к /bookings.

    Разрешено не более `rate_limit_per_minute` запросов в минуту
    с одного IP-адреса.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if (
            request.method == "POST"
            and request.url.path.rstrip("/") == "/bookings"
        ):
            client_ip = request.client.host if request.client else "unknown"

            try:
                # Пробуем Redis; в тестах он может быть недоступен.
                import redis as redis_lib

                r = redis_lib.from_url(
                    settings.redis_url,
                    decode_responses=True,
                )
                key = f"rate_limit:{client_ip}:{int(time.time() // 60)}"
                count = r.incr(key)

                if count == 1:
                    r.expire(key, 60)

                if count > settings.rate_limit_per_minute:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": (
                                "Rate limit exceeded: max "
                                f"{settings.rate_limit_per_minute} requests "
                                "per minute"
                            ),
                        },
                    )
            except Exception:
                # Если Redis недоступен, пропускаем rate limiting.
                pass

        return await call_next(request)
