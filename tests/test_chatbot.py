"""Cascata de modelos, cache, domínio com histórico e streaming — com transporte simulado."""

import asyncio
import json

import httpx
import pytest

from app import chatbot
from app.schemas import Message

PERGUNTA = "qual a melhor picanha?"
OK_BODY = {
    "choices": [{"message": {"content": "resposta ok"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


@pytest.fixture(autouse=True)
def com_credencial(monkeypatch):
    monkeypatch.setattr(chatbot, "GROQ_API_KEY", "chave-de-teste")


def sse(*textos: str) -> bytes:
    linhas = [
        "data: " + json.dumps({"choices": [{"delta": {"content": texto}}]})
        for texto in textos
    ]
    linhas.append("data: [DONE]")
    return ("\n\n".join(linhas) + "\n\n").encode()


def executar(respostas, pergunta=PERGUNTA, history=(), stream=False):
    """Roda a chamada devolvendo `respostas` em ordem. Retorna (resultado, modelos_chamados)."""
    chamados: list[str] = []
    fila = list(respostas)

    def handler(request: httpx.Request) -> httpx.Response:
        chamados.append(json.loads(request.content)["model"])
        item = fila.pop(0)
        if isinstance(item, Exception):
            raise item
        status, body = item
        if isinstance(body, bytes):
            return httpx.Response(status, content=body)
        return httpx.Response(status, json=body)

    async def main():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            try:
                if stream:
                    partes = [
                        parte
                        async for parte in chatbot.stream_response(
                            client, pergunta, history
                        )
                    ]
                    return "".join(partes)
                return await chatbot.get_response(client, pergunta, history)
            except chatbot.ChatUnavailableError:
                return "INDISPONIVEL"

    return asyncio.run(main()), chamados


# ── Cascata de modelos ────────────────────────────────────────────────────────

def test_sucesso_no_primeiro_modelo_nao_tenta_os_outros():
    resultado, chamados = executar([(200, OK_BODY)])
    assert resultado == "resposta ok"
    assert len(chamados) == 1


@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504, 404])
def test_status_transitorio_cai_para_o_proximo_modelo(status):
    resultado, chamados = executar([(status, {}), (200, OK_BODY)])
    assert resultado == "resposta ok"
    assert len(chamados) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_erro_de_credencial_ou_payload_interrompe_na_primeira(status):
    resultado, chamados = executar([(status, {"error": "nao recuperavel"})])
    assert resultado == "INDISPONIVEL"
    assert len(chamados) == 1


def test_percorre_a_lista_inteira_antes_de_desistir():
    resultado, chamados = executar([(503, {}), (404, {}), (200, OK_BODY)])
    assert resultado == "resposta ok"
    assert len(chamados) == 3


def test_falha_de_rede_tenta_o_proximo_modelo():
    resultado, chamados = executar([httpx.ReadTimeout("timeout"), (200, OK_BODY)])
    assert resultado == "resposta ok"
    assert len(chamados) == 2


def test_sem_rede_em_todos_os_modelos():
    resultado, chamados = executar([httpx.ConnectError("sem rede")] * 3)
    assert resultado == "INDISPONIVEL"
    assert len(chamados) == 3


def test_corpo_fora_do_formato_esperado_tenta_o_proximo():
    resultado, chamados = executar([(200, {"inesperado": True}), (200, OK_BODY)])
    assert resultado == "resposta ok"
    assert len(chamados) == 2


def test_sem_credencial_nao_chama_a_api(monkeypatch):
    monkeypatch.setattr(chatbot, "GROQ_API_KEY", None)
    resultado, chamados = executar([])
    assert resultado == "INDISPONIVEL"
    assert chamados == []


# ── Filtro de domínio ────────────────────────────────────────────────────────

def test_fora_do_dominio_responde_local_sem_chamar_a_api():
    resultado, chamados = executar([], pergunta="quem ganhou a copa do mundo?")
    assert resultado == chatbot.OFF_TOPIC_MESSAGE
    assert chamados == []


def test_follow_up_sem_palavra_chave_e_aceito_pelo_historico():
    history = [
        Message(role="user", content="qual a melhor carne pra churrasco?"),
        Message(role="assistant", content="A picanha é a mais tradicional."),
    ]
    resultado, chamados = executar(
        [(200, OK_BODY)], pergunta="e para 10 pessoas?", history=history
    )
    assert resultado == "resposta ok"
    assert len(chamados) == 1


def test_follow_up_sem_historico_no_dominio_e_recusado():
    history = [Message(role="user", content="bom dia")]
    resultado, chamados = executar(
        [], pergunta="e para 10 pessoas?", history=history
    )
    assert resultado == chatbot.OFF_TOPIC_MESSAGE
    assert chamados == []


def test_historico_vai_no_payload_enviado_a_groq():
    enviados = []

    def handler(request: httpx.Request) -> httpx.Response:
        enviados.append(json.loads(request.content)["messages"])
        return httpx.Response(200, json=OK_BODY)

    history = [
        Message(role="user", content="qual a melhor carne pra churrasco?"),
        Message(role="assistant", content="A picanha é a mais tradicional."),
    ]

    async def main():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await chatbot.get_response(client, "e para 10 pessoas?", history)

    asyncio.run(main())

    papeis = [msg["role"] for msg in enviados[0]]
    assert papeis == ["system", "user", "assistant", "user"]
    assert enviados[0][-1]["content"] == "e para 10 pessoas?"


# ── Cache ────────────────────────────────────────────────────────────────────

def test_pergunta_repetida_nao_chama_a_api_de_novo():
    chatbot.RESPONSE_CACHE.clear()
    primeira, chamados = executar([(200, OK_BODY)])
    assert primeira == "resposta ok"

    # A segunda rodada não oferece nenhuma resposta: se sair do cache, nada é chamado.
    segunda, chamados = executar([])
    assert segunda == "resposta ok"
    assert chamados == []


def test_cache_ignora_variacao_de_caixa_e_pontuacao():
    chatbot.RESPONSE_CACHE.clear()
    executar([(200, OK_BODY)], pergunta="Qual a melhor picanha?")
    resultado, chamados = executar([], pergunta="qual a melhor PICANHA")
    assert resultado == "resposta ok"
    assert chamados == []


def test_pergunta_com_historico_nao_usa_cache():
    chatbot.RESPONSE_CACHE.clear()
    history = [Message(role="user", content="quero fazer churrasco")]
    executar([(200, OK_BODY)], history=history)

    resultado, chamados = executar([(200, OK_BODY)], history=history)
    assert resultado == "resposta ok"
    assert len(chamados) == 1


# ── Streaming ────────────────────────────────────────────────────────────────

def test_stream_monta_a_resposta_em_pedacos():
    chatbot.RESPONSE_CACHE.clear()
    resultado, chamados = executar(
        [(200, sse("A picanha ", "é o ", "corte mais tradicional."))], stream=True
    )
    assert resultado == "A picanha é o corte mais tradicional."
    assert len(chamados) == 1


def test_stream_cai_para_o_proximo_modelo_antes_do_primeiro_byte():
    chatbot.RESPONSE_CACHE.clear()
    resultado, chamados = executar(
        [(429, {}), (200, sse("resposta ok"))], stream=True
    )
    assert resultado == "resposta ok"
    assert len(chamados) == 2


def test_stream_nao_repete_modelo_em_erro_nao_recuperavel():
    chatbot.RESPONSE_CACHE.clear()
    resultado, chamados = executar([(401, {})], stream=True)
    assert resultado == "INDISPONIVEL"
    assert len(chamados) == 1


def test_stream_alimenta_o_cache_do_endpoint_normal():
    chatbot.RESPONSE_CACHE.clear()
    executar([(200, sse("resposta ", "ok"))], stream=True)

    resultado, chamados = executar([])
    assert resultado == "resposta ok"
    assert chamados == []


def test_stream_fora_do_dominio_responde_local():
    resultado, chamados = executar(
        [], pergunta="quem ganhou a copa do mundo?", stream=True
    )
    assert resultado == chatbot.OFF_TOPIC_MESSAGE
    assert chamados == []
