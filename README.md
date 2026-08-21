# 🥩 MeatShop Chatbot API

**Versão:** 1.1.0  
**Data:** 21 de Agosto de 2026  
**Autor:** Vinícius Rodrigues  

API de chatbot inteligente especializada em carnes, integrada ao app MeatShop.

---

## 🚀 Sobre o Projeto

O MeatShop Chatbot é um serviço backend que utiliza Inteligência Artificial para responder perguntas sobre:

- Cortes de carne
- Receitas
- Técnicas de preparo
- Cultura brasileira

A API foi projetada para ser simples, rápida e focada no domínio do aplicativo.

---

## 🎯 Objetivo

Fornecer respostas inteligentes e contextualizadas para usuários do app MeatShop, garantindo:

- Respostas relevantes
- Controle de domínio
- Baixo custo de operação
- Integração simples com mobile

---

## 🏗️ Arquitetura


Flutter App → Rate limit → Filtro de domínio → Cache → Groq API → Resposta


Cada camada existe para evitar a chamada seguinte, que é a única que custa dinheiro:

| Camada | O que faz | Arquivo |
|---|---|---|
| Rate limit | Janela deslizante por IP; `429` acima do limite | `app/ratelimit.py` |
| Filtro de domínio | Casa palavras inteiras sobre texto normalizado (sem acentos nem pontuação). Sem correspondência, responde local | `app/filter.py` |
| Cache | Perguntas repetidas sem histórico são servidas da memória | `app/cache.py` |
| Groq | Cascata de três modelos com timeout | `app/chatbot.py` |

O fallback entre modelos só avança em falhas transitórias (rede, `429`, `5xx`, modelo
descontinuado); erros de credencial ou de payload interrompem na primeira tentativa.

**O servidor é sem estado.** O histórico da conversa vem do app em cada requisição —
não há sessão nem banco. Rate limit e cache vivem no processo: com mais de uma instância
no Render, cada uma mantém o seu (ver ressalvas nos módulos).

---

## ⚙️ Tecnologias

- Python 3.12
- FastAPI (SSE para streaming)
- HTTPX (cliente assíncrono com pool de conexões)
- Groq API
- Python-dotenv
- Pytest + Ruff
- GitHub Actions (CI)
- Render (deploy)

---

## 🌐 URL da API


https://meatshop-chatbot.onrender.com


---

## 🔌 Endpoints

### `GET /`
Healthcheck.

### `POST /chat`

**Request** — `history` é opcional; envie os turnos anteriores para manter contexto.
```json
{
  "message": "e para 10 pessoas?",
  "history": [
    { "role": "user", "content": "qual a melhor carne para churrasco?" },
    { "role": "assistant", "content": "A picanha é a mais tradicional..." }
  ]
}
```

**Response — 200**
```json
{ "response": "..." }
```

| Status | Quando |
|---|---|
| `200` | Resposta da IA ou recusa de domínio |
| `401` | `X-API-Key` ausente ou inválida (só quando `API_KEY` está configurada) |
| `422` | Entrada fora dos limites de validação |
| `429` | Rate limit por IP excedido — respeite o header `Retry-After` |
| `503` | Nenhum modelo conseguiu responder — o cliente pode tentar novamente |

O corpo é sempre `{ "response": "..." }` em `200` e `503`.

**Limites de entrada**

| Campo | Limite |
|---|---|
| `message` | 1 a 1000 caracteres |
| `history` | até 6 mensagens, 6000 caracteres somados |
| `history[].role` | `user` ou `assistant` |
| `history[].content` | 1 a 2000 caracteres |

### `POST /chat/stream`

Mesma entrada do `/chat`, resposta entregue em pedaços via **SSE** (`text/event-stream`).
Reduz a latência percebida — o texto aparece conforme é gerado.

```
data: {"delta": "A picanha "}
data: {"delta": "é o corte "}
data: [DONE]
```

Em falha, o evento é `{"error": "..."}` seguido de `[DONE]`. Como a resposta já começou,
o status HTTP permanece `200` — o cliente deve tratar o evento de erro.

---

## 🔐 Variáveis de ambiente

Copie `.env.example` para `.env` e preencha:

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `GROQ_API_KEY` | Sim | — | Chave da API da Groq |
| `ALLOWED_ORIGINS` | Não | `*` | Origens do CORS separadas por vírgula |
| `API_KEY` | Não | vazio | Segredo exigido no header `X-API-Key`. Vazio desliga a checagem |
| `RATE_LIMIT_REQUESTS` | Não | `20` | Requisições permitidas por janela |
| `RATE_LIMIT_WINDOW_SECONDS` | Não | `60` | Duração da janela |
| `CACHE_TTL_SECONDS` | Não | `3600` | Vida das respostas em cache. `0` desliga |
| `CACHE_MAX_ENTRIES` | Não | `500` | Máximo de respostas em cache |
| `LOG_LEVEL` | Não | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

> ⚠️ `API_KEY` é um segredo compartilhado com o app e **é extraível do pacote instalado**.
> Serve para barrar abuso casual, não um atacante dedicado. A proteção adequada é validar
> o token do usuário logado no MeatShop.

---

## 💻 Execução local

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Documentação interativa em `http://127.0.0.1:8000/docs`.

---

## ✅ Testes e qualidade

```bash
ruff check .    # lint
pytest          # 85 testes
```

Cobertura da suíte:

| Arquivo | O que garante |
|---|---|
| `tests/test_filter.py` | Falsos positivos e negativos do filtro de domínio |
| `tests/test_chatbot.py` | Cascata de modelos, cache, histórico e streaming |
| `tests/test_api.py` | Contrato HTTP, rate limit, credencial e CORS |
| `tests/test_ratelimit.py` | Janela deslizante, expiração e isolamento por chave |
| `tests/test_cache.py` | TTL, descarte do menos usado e desligamento |

Nenhuma chamada real à Groq: os testes usam `httpx.MockTransport`, e o tempo é controlado
por um relógio falso — a suíte roda em segundos.

O workflow (`.github/workflows/ci.yml`) roda lint e testes em todo push e PR para `main` e
`develop`. Usa apenas actions oficiais (`actions/*`) — actions de terceiros são vetor de
supply chain e ficam fora por política.

---

## 📊 Observabilidade

Cada resposta gera uma linha de log com modelo, latência e tokens consumidos:

```
INFO app.chatbot: groq ok model=llama-3.1-8b-instant latency_ms=412 prompt_tokens=2847 completion_tokens=193 total_tokens=3040
INFO app.chatbot: cache hit
```

Nenhum conteúdo de usuário é registrado. Use `total_tokens` para acompanhar o custo real
por conversa e `cache hit` para medir a taxa de acerto do cache.

---

