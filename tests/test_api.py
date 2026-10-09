"""Contrato HTTP: status, corpo, rate limit, credencial e CORS."""

import json
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from app import chatbot, main
from app.main import app

OK_BODY = {"choices": [{"message": {"content": "resposta ok"}}]}


@contextmanager
def api(handler=None):
    """TestClient com o lifespan ativo e, opcionalmente, a Groq simulada."""
    with TestClient(app) as client:
        if handler is not None:
            app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        yield client


def groq_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=OK_BODY)


def groq_sse(request: httpx.Request) -> httpx.Response:
    corpo = (
        'data: {"choices":[{"delta":{"content":"resposta "}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    return httpx.Response(200, content=corpo.encode())


@pytest.fixture(autouse=True)
def com_credencial(monkeypatch):
    monkeypatch.setattr(chatbot, "GROQ_API_KEY", "chave-de-teste")


def test_healthcheck():
    with api() as client:
        resposta = client.get("/")
    assert resposta.status_code == 200
    assert "status" in resposta.json()


def test_chat_responde_no_contrato():
    with api(groq_ok) as client:
        resposta = client.post("/chat", json={"message": "qual a melhor picanha?"})
    assert resposta.status_code == 200
    body = resposta.json()
    assert body["response"] == "resposta ok"
    assert body["request_id"]
    assert resposta.headers["X-Request-ID"] == body["request_id"]


def test_fora_do_dominio_responde_200_com_recusa():
    with api() as client:
        resposta = client.post("/chat", json={"message": "quem ganhou a copa?"})
    assert resposta.status_code == 200
    assert "especialista em carnes" in resposta.json()["response"]


def test_indisponivel_responde_503_mantendo_o_contrato(monkeypatch):
    monkeypatch.setattr(chatbot, "GROQ_API_KEY", None)
    with api() as client:
        resposta = client.post("/chat", json={"message": "qual a melhor picanha?"})
    assert resposta.status_code == 503
    assert "response" in resposta.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "   "},
        {"message": "picanha " * 500},
        {},
        {"message": "picanha", "history": [{"role": "sistema", "content": "x"}]},
        {"message": "picanha", "history": [{"role": "user", "content": ""}]},
        {
            "message": "picanha",
            "history": [{"role": "user", "content": "x"}] * 7,
        },
    ],
)
def test_entrada_invalida_responde_422(payload):
    with api() as client:
        resposta = client.post("/chat", json=payload)
    assert resposta.status_code == 422


def test_historico_valido_e_aceito():
    with api(groq_ok) as client:
        resposta = client.post(
            "/chat",
            json={
                "message": "e para 10 pessoas?",
                "history": [
                    {"role": "user", "content": "quero fazer churrasco"},
                    {"role": "assistant", "content": "Ótimo! Quantas pessoas?"},
                ],
            },
        )
    assert resposta.status_code == 200


def test_rate_limit_bloqueia_com_429_e_retry_after(monkeypatch):
    monkeypatch.setattr(main.rate_limiter, "max_requests", 3)
    with api(groq_ok) as client:
        for _ in range(3):
            assert client.post("/chat", json={"message": "picanha"}).status_code == 200

        # Pergunta diferente para não ser servida pelo cache.
        resposta = client.post("/chat", json={"message": "costela"})

    assert resposta.status_code == 429
    assert int(resposta.headers["Retry-After"]) >= 1


def test_rate_limit_separa_por_ip(monkeypatch):
    monkeypatch.setattr(main.rate_limiter, "max_requests", 1)
    with api(groq_ok) as client:
        primeira = client.post(
            "/chat",
            json={"message": "picanha"},
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        mesma_origem = client.post(
            "/chat",
            json={"message": "costela"},
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        outra_origem = client.post(
            "/chat",
            json={"message": "cupim"},
            headers={"X-Forwarded-For": "10.0.0.2"},
        )

    assert primeira.status_code == 200
    assert mesma_origem.status_code == 429
    assert outra_origem.status_code == 200


def test_api_key_desligada_por_padrao():
    with api(groq_ok) as client:
        assert client.post("/chat", json={"message": "picanha"}).status_code == 200


def test_api_key_exigida_quando_configurada(monkeypatch):
    monkeypatch.setattr(main, "API_KEY", "segredo")
    with api(groq_ok) as client:
        sem_header = client.post("/chat", json={"message": "picanha"})
        errada = client.post("/chat", json={"message": "picanha"}, headers={"X-API-Key": "outra"})
        correta = client.post(
            "/chat", json={"message": "picanha"}, headers={"X-API-Key": "segredo"}
        )

    assert sem_header.status_code == 401
    assert errada.status_code == 401
    assert correta.status_code == 200


def test_service_key_e_aceita_para_comunicacao_interna(monkeypatch):
    monkeypatch.setattr(main, "SERVICE_API_KEY", "segredo-interno")
    with api(groq_ok) as client:
        resposta = client.post(
            "/chat",
            json={"message": "picanha"},
            headers={"X-Service-Key": "segredo-interno"},
        )
    assert resposta.status_code == 200


def test_readiness_detecta_configuracao_ausente(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(main, "ENVIRONMENT", "production")
    monkeypatch.setattr(main, "SERVICE_API_KEY", "")
    monkeypatch.setattr(main, "API_KEY", "")
    with api() as client:
        resposta = client.get("/health/ready")
    assert resposta.status_code == 503
    assert set(resposta.json()["missing"]) == {"GROQ_API_KEY", "SERVICE_API_KEY"}


def test_recipe_draft_retorna_json_validado():
    draft = {
        "title": "Picanha com ervas",
        "description": "Rascunho para revisão.",
        "tag": "Bovina",
        "ingredients": [{"name": "Picanha", "quantity": "1 kg", "tip": None}],
        "steps": [{"step_number": 1, "description": "Asse com segurança.", "tip": None}],
        "products": [{"product_id": 7, "call_to_action": "Confira a picanha."}],
        "safety_notice": "Use termômetro culinário.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(draft)}}]},
        )

    with api(handler) as client:
        resposta = client.post(
            "/recipe-drafts",
            json={
                "brief": "picanha com ervas",
                "servings": 4,
                "products": [
                    {"id": 7, "name": "Picanha", "unit_of_measure": "kg"},
                ],
            },
        )
    assert resposta.status_code == 200
    assert resposta.json()["draft"] == draft


def test_cors_nao_envia_allow_credentials():
    with api() as client:
        resposta = client.options(
            "/chat",
            headers={
                "Origin": "https://app.meatshop.com.br",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert resposta.headers.get("access-control-allow-credentials") is None


def test_stream_entrega_eventos_sse():
    with api(groq_sse) as client:
        resposta = client.post("/chat/stream", json={"message": "qual a melhor picanha?"})

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/event-stream")

    eventos = [
        linha[len("data: ") :] for linha in resposta.text.splitlines() if linha.startswith("data: ")
    ]
    assert eventos[-1] == "[DONE]"

    texto = "".join(json.loads(evento)["delta"] for evento in eventos[:-1])
    assert texto == "resposta ok"


def test_stream_reporta_falha_como_evento(monkeypatch):
    monkeypatch.setattr(chatbot, "GROQ_API_KEY", None)
    with api() as client:
        resposta = client.post("/chat/stream", json={"message": "qual a melhor picanha?"})

    assert resposta.status_code == 200
    assert '"error"' in resposta.text
    assert resposta.text.rstrip().endswith("[DONE]")
