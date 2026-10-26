import json
import logging
import math
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.chatbot import (
    ChatUnavailableError,
    UnsafeInputError,
    create_client,
    generate_recipe_draft,
    get_response,
    stream_response,
)
from app.ratelimit import SlidingWindowRateLimiter
from app.safety import redact_sensitive
from app.schemas import ChatRequest, ChatResponse, RecipeDraftRequest, RecipeDraftResponse

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Em produção, restrinja a origem (ex: ALLOWED_ORIGINS=https://app.meatshop.com.br).
ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "").split(",") if origin.strip()
]

# API_KEY permanece apenas por compatibilidade. SERVICE_API_KEY é o contrato recomendado
# entre o backend MeatShop e este serviço; nenhuma das duas deve ir para o app ou painel.
API_KEY = os.getenv("API_KEY", "")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

UNAVAILABLE_MESSAGE = "Não consegui responder agora. Tente novamente em alguns instantes."

rate_limiter = SlidingWindowRateLimiter(
    max_requests=int(os.getenv("RATE_LIMIT_REQUESTS", "20")),
    window_seconds=float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with create_client() as client:
        app.state.http_client = client
        yield


def docs_urls(environment: str) -> dict[str, str | None]:
    if environment.strip().lower() == "production":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


app = FastAPI(
    title="MeatShop Chatbot API",
    version="3.0.0",
    lifespan=lifespan,
    **docs_urls(ENVIRONMENT),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # A API não usa cookies nem sessão; com credentials=True o wildcard seria inválido.
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "X-Service-Key", "X-Request-ID", "X-MeatShop-User"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied = request.headers.get("x-request-id", "").strip()
    request_id = supplied[:64] if supplied else str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _client_key(request: Request) -> str:
    """IP do cliente conforme o proxy do Render. Ver ressalvas em app/ratelimit.py."""
    user_id = request.headers.get("x-meatshop-user", "").strip()
    if user_id:
        return f"user:{user_id[:64]}"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    x_service_key: Annotated[str | None, Header(alias="X-Service-Key")] = None,
) -> None:
    expected = SERVICE_API_KEY or API_KEY
    if not expected:
        if ENVIRONMENT == "production":
            raise HTTPException(status_code=503, detail="Credencial interna não configurada.")
        return
    supplied = x_service_key or x_api_key
    if supplied is None or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Credencial inválida.")


def enforce_rate_limit(request: Request) -> None:
    retry_after = rate_limiter.check(_client_key(request))
    if retry_after is None:
        return

    logger.warning("rate limit atingido")
    raise HTTPException(
        status_code=429,
        detail="Muitas perguntas em sequência. Aguarde alguns segundos.",
        headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
    )


PROTECTED = [Depends(require_api_key), Depends(enforce_rate_limit)]


@app.exception_handler(ChatUnavailableError)
async def chat_unavailable_handler(request: Request, exc: ChatUnavailableError):
    """Mantém o contrato {"response": ...} para o app, mas sinaliza 503 para retry."""
    return JSONResponse(
        status_code=503,
        content=ChatResponse(
            response=UNAVAILABLE_MESSAGE,
            request_id=request.state.request_id,
        ).model_dump(),
    )


@app.exception_handler(UnsafeInputError)
async def unsafe_input_handler(request: Request, exc: UnsafeInputError):
    return JSONResponse(
        status_code=400,
        content={
            "code": "AI_UNSAFE_INPUT",
            "detail": "A solicitação contém instruções que não podem ser processadas.",
            "request_id": request.state.request_id,
        },
    )


@app.get("/")
def root():
    return {"status": "MeatShop Chatbot rodando 🚀", "version": app.version}


@app.get("/health/live")
def health_live():
    return {"status": "ok", "version": app.version}


@app.get("/health/ready")
def health_ready():
    missing = []
    if not os.getenv("GROQ_API_KEY"):
        missing.append("GROQ_API_KEY")
    if ENVIRONMENT == "production" and not (SERVICE_API_KEY or API_KEY):
        missing.append("SERVICE_API_KEY")
    if missing:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "missing": missing},
        )
    return {"status": "ready", "version": app.version}


@app.post("/chat", response_model=ChatResponse, dependencies=PROTECTED)
async def chat(req: ChatRequest, request: Request):
    resposta = await get_response(request.app.state.http_client, req.message, req.history)
    return ChatResponse(response=resposta, request_id=request.state.request_id)


@app.post(
    "/recipe-drafts",
    response_model=RecipeDraftResponse,
    dependencies=PROTECTED,
)
async def recipe_draft(req: RecipeDraftRequest, request: Request):
    draft = await generate_recipe_draft(request.app.state.http_client, req)
    return RecipeDraftResponse(draft=draft, request_id=request.state.request_id)


@app.post("/chat/stream", dependencies=PROTECTED)
async def chat_stream(req: ChatRequest, request: Request):
    """Mesma resposta do /chat, entregue em pedaços via SSE.

    Eventos: {"delta": "..."} para texto, {"error": "..."} em falha, e [DONE] no fim.
    """

    async def eventos():
        try:
            async for delta in stream_response(
                request.app.state.http_client, req.message, req.history
            ):
                safe_delta = redact_sensitive(delta)
                yield f"data: {json.dumps({'delta': safe_delta}, ensure_ascii=False)}\n\n"
        except ChatUnavailableError:
            # A resposta já começou, então o erro vai como evento — não como status HTTP.
            yield f"data: {json.dumps({'error': UNAVAILABLE_MESSAGE}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        eventos(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
