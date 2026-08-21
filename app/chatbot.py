"""Integração com a API da Groq."""

import json
import logging
import os
import time
from collections.abc import AsyncIterator, Sequence

import httpx
from dotenv import load_dotenv

from app.cache import TTLCache
from app.filter import is_meat_related, normalize
from app.prompt import SYSTEM_PROMPT
from app.schemas import Message

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

# Quantas mensagens anteriores contam para decidir se um follow-up está no domínio.
CONTEXT_MESSAGES = 2

RESPONSE_CACHE = TTLCache(
    ttl_seconds=float(os.getenv("CACHE_TTL_SECONDS", "3600")),
    max_entries=int(os.getenv("CACHE_MAX_ENTRIES", "500")),
)


class ChatUnavailableError(RuntimeError):
    """Nenhum modelo conseguiu responder."""


def create_client() -> httpx.AsyncClient:
    """Cliente HTTP com pool de conexões, gerenciado pelo lifespan da aplicação."""
    return httpx.AsyncClient(timeout=TIMEOUT)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }


def _payload(
    model: str, user_input: str, history: Sequence[Message], stream: bool
) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": msg.role, "content": msg.content} for msg in history]
    messages.append({"role": "user", "content": user_input})

    payload = {"model": model, "messages": messages}
    if stream:
        payload["stream"] = True
    return payload


def _in_domain(user_input: str, history: Sequence[Message]) -> bool:
    if is_meat_related(user_input):
        return True

    # Follow-ups como "e para 10 pessoas?" não têm palavra-chave própria. Aceita se os
    # últimos turnos estavam no domínio — sem isso, o multi-turno quebra na segunda pergunta.
    recente = " ".join(msg.content for msg in history[-CONTEXT_MESSAGES:])
    return bool(recente) and is_meat_related(recente)


def _cache_key(user_input: str, history: Sequence[Message]) -> str | None:
    """Só faz cache de pergunta isolada: com histórico a repetição exata é improvável."""
    return None if history else normalize(user_input)


def _log_usage(model: str, started: float, payload: dict) -> None:
    usage = payload.get("usage") or {}
    logger.info(
        "groq ok model=%s latency_ms=%d prompt_tokens=%s completion_tokens=%s total_tokens=%s",
        model,
        (time.monotonic() - started) * 1000,
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        usage.get("total_tokens"),
    )


def _check_ready() -> None:
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY não configurada — impossível chamar a Groq")
        raise ChatUnavailableError


async def get_response(
    client: httpx.AsyncClient,
    user_input: str,
    history: Sequence[Message] = (),
) -> str:
    if not _in_domain(user_input, history):
        return OFF_TOPIC_MESSAGE

    key = _cache_key(user_input, history)
    if key is not None:
        cached = RESPONSE_CACHE.get(key)
        if cached is not None:
            logger.info("cache hit")
            return cached

    _check_ready()

    for model in MODELS:
        started = time.monotonic()
        try:
            response = await client.post(
                GROQ_URL,
                headers=_headers(),
                json=_payload(model, user_input, history, stream=False),
            )
        except httpx.HTTPError as exc:
            logger.warning("Falha de rede em %s: %s", model, type(exc).__name__)
            continue

        if response.status_code == httpx.codes.OK:
            try:
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError):
                logger.error("Resposta em formato inesperado de %s", model)
                continue

            _log_usage(model, started, payload)
            if key is not None:
                RESPONSE_CACHE.set(key, content)
            return content

        if response.status_code in RETRYABLE_STATUS:
            logger.warning("Modelo %s indisponível (HTTP %s)", model, response.status_code)
            continue

        logger.error(
            "Erro não recuperável na Groq (HTTP %s) — interrompendo fallback",
            response.status_code,
        )
        break

    raise ChatUnavailableError


def _parse_sse_delta(line: str) -> str | None:
    """Extrai o texto de uma linha SSE da Groq. `None` quando a linha não traz conteúdo."""
    if not line.startswith("data:"):
        return None

    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return None

    try:
        chunk = json.loads(data)
    except ValueError:
        return None

    choices = chunk.get("choices") or []
    if not choices:
        return None
    return (choices[0].get("delta") or {}).get("content") or None


async def stream_response(
    client: httpx.AsyncClient,
    user_input: str,
    history: Sequence[Message] = (),
) -> AsyncIterator[str]:
    """Gera a resposta em pedaços. O fallback só vale antes do primeiro texto emitido."""
    if not _in_domain(user_input, history):
        yield OFF_TOPIC_MESSAGE
        return

    key = _cache_key(user_input, history)
    if key is not None:
        cached = RESPONSE_CACHE.get(key)
        if cached is not None:
            logger.info("cache hit (stream)")
            yield cached
            return

    _check_ready()

    for model in MODELS:
        started = time.monotonic()
        partes: list[str] = []
        try:
            async with client.stream(
                "POST",
                GROQ_URL,
                headers=_headers(),
                json=_payload(model, user_input, history, stream=True),
            ) as response:
                if response.status_code != httpx.codes.OK:
                    await response.aread()
                    if response.status_code in RETRYABLE_STATUS:
                        logger.warning(
                            "Modelo %s indisponível (HTTP %s)", model, response.status_code
                        )
                        continue
                    logger.error(
                        "Erro não recuperável na Groq (HTTP %s) — interrompendo fallback",
                        response.status_code,
                    )
                    break

                async for line in response.aiter_lines():
                    delta = _parse_sse_delta(line)
                    if delta:
                        partes.append(delta)
                        yield delta
        except httpx.HTTPError as exc:
            logger.warning("Falha de rede em %s: %s", model, type(exc).__name__)
            if partes:
                # Reiniciar com outro modelo duplicaria o texto já enviado ao cliente.
                logger.error("Stream interrompido após envio parcial em %s", model)
                return
            continue

        # A Groq não devolve `usage` no modo stream sem `stream_options`, que não foi
        # validado contra a API — por ora registramos só latência e volume.
        logger.info(
            "groq stream ok model=%s latency_ms=%d chunks=%d chars=%d",
            model,
            (time.monotonic() - started) * 1000,
            len(partes),
            sum(len(parte) for parte in partes),
        )
        if partes and key is not None:
            RESPONSE_CACHE.set(key, "".join(partes))
        return

    raise ChatUnavailableError
