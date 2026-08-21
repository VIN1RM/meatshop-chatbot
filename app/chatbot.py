"""Integração com a API da Groq."""

import logging
import os

import httpx
from dotenv import load_dotenv

from app.filter import is_meat_related
from app.prompt import SYSTEM_PROMPT

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Ordem de preferência: começa pelo modelo mais rápido e barato.
MODELS = (
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
)

OFF_TOPIC_MESSAGE = (
    "Sou especialista em carnes e posso ajudar com receitas, cortes e preparo. "
    "Para dúvidas sobre o app, entre em contato com o suporte."
)

TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)

# Falhas do modelo/infra: vale tentar o próximo modelo da lista.
# O que ficou de fora (401, 403, 400, 422) é erro nosso — repetir só desperdiça chamada.
RETRYABLE_STATUS = frozenset({404, 408, 409, 429, 500, 502, 503, 504})


class ChatUnavailableError(RuntimeError):
    """Nenhum modelo conseguiu responder."""


def create_client() -> httpx.AsyncClient:
    """Cliente HTTP com pool de conexões, gerenciado pelo lifespan da aplicação."""
    return httpx.AsyncClient(timeout=TIMEOUT)


def _payload(model: str, user_input: str) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ],
    }


async def get_response(client: httpx.AsyncClient, user_input: str) -> str:
    if not is_meat_related(user_input):
        return OFF_TOPIC_MESSAGE

    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY não configurada — impossível chamar a Groq")
        raise ChatUnavailableError

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    for model in MODELS:
        try:
            response = await client.post(
                GROQ_URL, headers=headers, json=_payload(model, user_input)
            )
        except httpx.HTTPError as exc:
            logger.warning("Falha de rede em %s: %s", model, type(exc).__name__)
            continue

        if response.status_code == httpx.codes.OK:
            try:
                return response.json()["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError):
                logger.error("Resposta em formato inesperado de %s", model)
                continue

        if response.status_code in RETRYABLE_STATUS:
            logger.warning("Modelo %s indisponível (HTTP %s)", model, response.status_code)
            continue

        logger.error(
            "Erro não recuperável na Groq (HTTP %s) — interrompendo fallback",
            response.status_code,
        )
        break

    raise ChatUnavailableError
