from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import CueError
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("cue.main")


class SecurityAndErrorShieldMiddleware:
    """
    Pure ASGI middleware that adds security headers and converts unexpected errors into JSON 500
    INSIDE CORSMiddleware so browsers never lose Access-Control-Allow-Origin headers on errors.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = list(message.get("headers") or [])
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                        (b"cache-control", b"no-store"),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception as exc:
            logger.exception("Unhandled error in ASGI request: %s", exc)
            if not response_started:
                resp = JSONResponse(
                    status_code=500,
                    content={"error_code": "INTERNAL_ERROR", "detail": str(exc)},
                )
                await resp(scope, receive, send_with_headers)


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url=None,
)

# Register inner shield first, then CORSMiddleware LAST so CORSMiddleware is outermost.
app.add_middleware(SecurityAndErrorShieldMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Business-Id"],
)


@app.exception_handler(CueError)
async def cue_error_handler(request: Request, exc: CueError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.code, "detail": exc.message},
    )


app.include_router(api_router, prefix=settings.API_PREFIX)
