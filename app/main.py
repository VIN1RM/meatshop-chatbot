import json
import logging
import math
import os
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.chatbot import (
    ChatUnavailableError,
    create_client,
    get_response,
    stream_response,
)
from app.ratelimit import SlidingWindowRateLimiter
from app.schemas import ChatRequest, ChatResponse

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Em produção, restrinja a origem (ex: ALLOWED_ORIGINS=https://app.meatshop.com.br).
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

# Segredo compartilhado com o app. Vazio desliga a checagem.
# Um segredo embutido no app é extraível do pacote: barra abuso casual, não atacante
# dedicado. A proteção de verdade é validar o token do usuário logado no MeatShop.
API_KEY = os.getenv("API_KEY", "")

UNAVAILABLE_MESSAGE = (
    "Não consegui responder agora. Tente novamente em alguns instantes."
)

rate_limiter = SlidingWindowRateLimiter(
    max_requests=int(os.getenv("RATE_LIMIT_REQUESTS", "20")),
    window_seconds=float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with create_client() as client:
        app.state.http_client = client
        yield


app = FastAPI(title="MeatShop Chatbot API", version="1.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # A API não usa cookies nem sessão; com credentials=True o wildcard seria inválido.
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


def _client_key(request: Request) -> str:
    """IP do cliente conforme o proxy do Render. Ver ressalvas em app/ratelimit.py."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    if not API_KEY:
        return
    if x_api_key is None or not secrets.compare_digest(x_api_key, API_KEY):
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
        content=ChatResponse(response=UNAVAILABLE_MESSAGE).model_dump(),
    )


@app.get("/")
def root():
    return {"status": "MeatShop Chatbot rodando 🚀"}


@app.post("/chat", response_model=ChatResponse, dependencies=PROTECTED)
async def chat(req: ChatRequest, request: Request):
    resposta = await get_response(
        request.app.state.http_client, req.message, req.history
    )
    return ChatResponse(response=resposta)


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
                yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
        except ChatUnavailableError:
            # A resposta já começou, então o erro vai como evento — não como status HTTP.
            yield f"data: {json.dumps({'error': UNAVAILABLE_MESSAGE}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        eventos(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
