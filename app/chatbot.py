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
from app.prompt import PROMPT_VERSION, RECIPE_DRAFT_PROMPT, SYSTEM_PROMPT
from app.safety import SAFETY_REFUSAL, is_prompt_injection, redact_sensitive
from app.schemas import Message, RecipeDraft, RecipeDraftRequest

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
MAX_COMPLETION_TOKENS = int(os.getenv("MAX_COMPLETION_TOKENS", "800"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.25"))
RECIPE_DRAFT_MODEL = os.getenv("RECIPE_DRAFT_MODEL", "openai/gpt-oss-20b")

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


class InvalidModelResponseError(ChatUnavailableError):
    """O provedor respondeu, mas fora do contrato validado."""


class UnsafeInputError(ValueError):
    """A entrada tentou alterar regras internas ou carregar instruções hostis."""


def create_client() -> httpx.AsyncClient:
    """Cliente HTTP com pool de conexões, gerenciado pelo lifespan da aplicação."""
    return httpx.AsyncClient(timeout=TIMEOUT)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }


def _payload(model: str, user_input: str, history: Sequence[Message], stream: bool) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [
        {"role": msg.role, "content": redact_sensitive(msg.content)}
        for msg in history
        if not is_prompt_injection(msg.content)
    ]
    messages.append({"role": "user", "content": redact_sensitive(user_input)})

    payload = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "temperature": TEMPERATURE,
    }
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
    """Cacheia somente perguntas genéricas sem indícios de dados pessoais."""
    normalized = normalize(user_input)
    sensitive_markers = (
        "cpf",
        "telefone",
        "endereco",
        "pedido",
        "entrega",
        "alerg",
        "doenca",
        "gravida",
        "medic",
    )
    if history or len(normalized) > 240 or any(item in normalized for item in sensitive_markers):
        return None
    return f"{PROMPT_VERSION}:{normalized}"


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
    if is_prompt_injection(user_input):
        return SAFETY_REFUSAL
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

            content = redact_sensitive(content)
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


async def generate_recipe_draft(
    client: httpx.AsyncClient,
    request: RecipeDraftRequest,
) -> RecipeDraft:
    """Gera JSON estrito e rejeita qualquer produto fora do catálogo autorizado."""
    if is_prompt_injection(request.brief):
        raise UnsafeInputError
    _check_ready()
    catalog = [product.model_dump() for product in request.products]
    user_payload = {
        "brief": redact_sensitive(request.brief),
        "servings": request.servings,
        "tag": request.tag,
        "authorized_catalog": catalog,
    }
    payload = {
        "model": RECIPE_DRAFT_MODEL,
        "messages": [
            {"role": "system", "content": RECIPE_DRAFT_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": 0.2,
        "max_completion_tokens": max(MAX_COMPLETION_TOKENS, 1600),
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "meatshop_recipe_draft",
                "strict": True,
                "schema": RecipeDraft.model_json_schema(),
            },
        },
    }
    started = time.monotonic()
    try:
        response = await client.post(GROQ_URL, headers=_headers(), json=payload)
    except httpx.HTTPError as exc:
        logger.warning("Falha de rede ao gerar rascunho: %s", type(exc).__name__)
        raise ChatUnavailableError from exc

    if response.status_code != httpx.codes.OK:
        logger.warning("Falha ao gerar rascunho (HTTP %s)", response.status_code)
        raise ChatUnavailableError

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        draft = RecipeDraft.model_validate_json(content)
    except (ValueError, KeyError, IndexError) as exc:
        logger.error("Rascunho retornado fora do contrato")
        raise InvalidModelResponseError from exc

    allowed_ids = {product.id for product in request.products}
    if any(product.product_id not in allowed_ids for product in draft.products):
        logger.error("Rascunho tentou associar produto fora do catálogo autorizado")
        raise InvalidModelResponseError

    expected_steps = list(range(1, len(draft.steps) + 1))
    if [step.step_number for step in draft.steps] != expected_steps:
        logger.error("Rascunho retornou numeração de passos inválida")
        raise InvalidModelResponseError

    _log_usage(RECIPE_DRAFT_MODEL, started, body)
    return draft


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
    if is_prompt_injection(user_input):
        yield SAFETY_REFUSAL
        return
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
                raise ChatUnavailableError from exc
            continue

        # A Groq não devolve `usage` no modo stream sem `stream_options`, que não foi
        # validado contra a API — por ora registramos só latência e volume.
        if partes:
            logger.info(
                "groq stream ok model=%s latency_ms=%d chunks=%d chars=%d",
                model,
                (time.monotonic() - started) * 1000,
                len(partes),
                sum(len(parte) for parte in partes),
            )
            if key is not None:
                RESPONSE_CACHE.set(key, "".join(partes))
            return
        logger.warning("Modelo %s encerrou o stream sem conteúdo", model)

    raise ChatUnavailableError
