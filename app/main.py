import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.chatbot import ChatUnavailableError, create_client, get_response
from app.schemas import ChatRequest, ChatResponse

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# Em produção, restrinja a origem (ex: ALLOWED_ORIGINS=https://app.meatshop.com.br).
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

UNAVAILABLE_MESSAGE = (
    "Não consegui responder agora. Tente novamente em alguns instantes."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with create_client() as client:
        app.state.http_client = client
        yield


app = FastAPI(title="MeatShop Chatbot API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # A API não usa cookies nem sessão; com credentials=True o wildcard seria inválido.
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


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


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    resposta = await get_response(request.app.state.http_client, req.message)
    return ChatResponse(response=resposta)
