# 🥩 MeatShop Chatbot API

**Versão:** 3.1.0

**Data:** 26 de outubro de 2026

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


Mobile/Painel → Backend MeatShop autenticado → Chatbot privado → Groq API


Cada camada existe para evitar a chamada seguinte, que é a única que custa dinheiro:

| Camada | O que faz | Arquivo |
|---|---|---|
| Rate limit | Janela deslizante por usuário (header `X-MeatShop-User`, enviado pelo backend) com fallback para o IP; `429` acima do limite | `app/ratelimit.py` |
| Filtro de domínio | Casa palavras inteiras sobre texto normalizado (sem acentos nem pontuação). Sem correspondência, responde local | `app/filter.py` |
| Cache | Perguntas repetidas sem histórico são servidas da memória | `app/cache.py` |
| Groq | Cascata de três modelos com timeout | `app/chatbot.py` |

O fallback entre modelos só avança em falhas transitórias (rede, `429`, `5xx`, modelo
descontinuado); erros de credencial ou de payload interrompem na primeira tentativa.

O serviço aceita somente chamadas internas autenticadas em produção. JWT, permissões de
unidade, auditoria e limites por usuário pertencem ao backend principal. O chatbot não
recebe credenciais do cliente nem acesso direto ao banco MeatShop.
O histórico de conversa também pertence ao backend principal: fica no PostgreSQL por sete
dias e somente os últimos turnos necessários são enviados a este serviço, que segue sem estado.

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

### `GET /health/live` e `GET /health/ready`

Liveness do processo e prontidão de credenciais. Em produção, readiness exige
`GROQ_API_KEY` e `SERVICE_API_KEY`.

### `POST /chat`

**Request interno** — `history` é opcional e é preenchido exclusivamente pelo backend
principal com os turnos autorizados do usuário autenticado.
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
| `400` | `AI_UNSAFE_INPUT`: a entrada tenta alterar ou revelar regras internas (prompt injection) |
| `401` | `X-Service-Key`/`X-API-Key` ausente ou inválida (só quando `SERVICE_API_KEY` ou `API_KEY` está configurada) |
| `422` | Entrada fora dos limites de validação |
| `429` | Rate limit excedido (por `X-MeatShop-User` ou, sem ele, por IP) — respeite o header `Retry-After` |
| `503` | Nenhum modelo conseguiu responder — o cliente pode tentar novamente |

O corpo é sempre `{ "response": "..." }` em `200` e `503`. Em `/chat`, tentativas de prompt
injection recebem `200` com uma recusa local; o `400` é usado por `/recipe-drafts`:

```json
{ "code": "AI_UNSAFE_INPUT", "detail": "A solicitação contém instruções que não podem ser processadas.", "request_id": "..." }
```

Antes de qualquer chamada ao provedor, mensagem e histórico passam por redação local de
dados pessoais (e-mail, CPF, telefone, CEP, endereço e nome quando apresentado, como em
"meu nome é ..."). A mesma redação é aplicada à resposta do modelo.

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

### `POST /recipe-drafts`

Gera rascunho de receita com JSON Schema estrito. O catálogo autorizado é fornecido pelo
backend e a resposta é rejeitada se associar um `product_id` que não estava na solicitação.
O endpoint não salva nem publica receitas.

---

## 🔐 Variáveis de ambiente

Copie `.env.example` para `.env` e preencha:

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `GROQ_API_KEY` | Sim | — | Chave da API da Groq |
| `ALLOWED_ORIGINS` | Não | vazio (nenhuma origem) | Origens do CORS separadas por vírgula. Vazio bloqueia chamadas de navegador; o backend não depende de CORS |
| `API_KEY` | Não | vazio | Segredo exigido no header `X-API-Key`. Vazio desliga a checagem |
| `SERVICE_API_KEY` | Produção | vazio | Segredo interno exigido no header `X-Service-Key` |
| `ENVIRONMENT` | Não | `development` | Em `production`, impede chamadas sem credencial interna e desliga `/docs`, `/redoc` e `/openapi.json` |
| `RATE_LIMIT_REQUESTS` | Não | `20` | Requisições permitidas por janela |
| `RATE_LIMIT_WINDOW_SECONDS` | Não | `60` | Duração da janela |
| `CACHE_TTL_SECONDS` | Não | `3600` | Vida das respostas em cache. `0` desliga |
| `CACHE_MAX_ENTRIES` | Não | `500` | Máximo de respostas em cache |
| `LOG_LEVEL` | Não | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MAX_COMPLETION_TOKENS` | Não | `800` | Limite de saída do chat |
| `TEMPERATURE` | Não | `0.25` | Aleatoriedade das respostas |
| `RECIPE_DRAFT_MODEL` | Não | `openai/gpt-oss-20b` | Modelo de saída estruturada |

`SERVICE_API_KEY` pertence somente ao backend e ao chatbot. Nunca a inclua no mobile,
painel, repositório ou variável `NEXT_PUBLIC_*`.

---

## 💻 Execução local

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Documentação interativa em `http://127.0.0.1:8000/docs` (indisponível com `ENVIRONMENT=production`).

---

## ✅ Testes e qualidade

```bash
ruff check .    # lint
pytest          # testes funcionais sem chamadas reais à Groq
```

Cobertura da suíte:

| Arquivo | O que garante |
|---|---|
| `tests/test_filter.py` | Falsos positivos e negativos do filtro de domínio |
| `tests/test_chatbot.py` | Cascata de modelos, cache, histórico e streaming |
| `tests/test_api.py` | Contrato HTTP, rate limit, credencial, CORS e docs em produção |
| `tests/test_safety.py` | Prompt injection e redação de dados pessoais |
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

