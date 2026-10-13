# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

---

## [Projeto ainda não publicado]

## [3.0.0] - 2026-10-09
### Integração segura com backend e copiloto de receitas

### Added
- Autenticação interna por `X-Service-Key` e identidade técnica por usuário.
- Request ID em headers e respostas.
- Healthchecks separados de liveness e readiness.
- Geração de rascunhos com JSON Schema, catálogo autorizado e validação de produtos.
- Limites explícitos de tokens e temperatura.
- Proteção local contra prompt injection e remoção de CPF, telefone e e-mail.
- Dockerfile, `.dockerignore` e manifesto Render.

### Changed
- Prompt compacto, versionado e com orientações alimentares corrigidas.
- Cache restrito a perguntas genéricas, sem histórico ou marcadores sensíveis.
- CORS fechado por padrão e credencial obrigatória em produção.
- Streams vazios ou interrompidos deixam de ser tratados como sucesso.
- O histórico multi-turno passa a ser recebido exclusivamente do backend principal, que o mantém no PostgreSQL por sete dias; o chatbot permanece sem estado.

### Security
- Mobile e painel não devem chamar este serviço diretamente.
- Entradas e saídas estruturadas são validadas antes de retornar ao backend.
- Nenhum conteúdo de usuário é incluído nos logs da aplicação.

---

## [1.1.0] - 2026-08-21
### Endurecimento para produção, proteção contra abuso, conversa multi-turno e base de testes

### Added
- `.env.example` com as variáveis suportadas e comentário descritivo em cada uma
- `ALLOWED_ORIGINS` para restringir as origens do CORS por ambiente
- `LOG_LEVEL` para controlar a verbosidade dos logs
- Validação de entrada em `POST /chat`: `message` entre 1 e 1000 caracteres (`422` fora da faixa)
- Timeout explícito nas chamadas à Groq (5s de conexão, 30s de leitura)
- Documentação de endpoints, variáveis de ambiente e execução local no README
- **Suíte de testes** com 85 casos (`tests/`) cobrindo filtro, cascata de modelos, cache,
  rate limit, contrato HTTP e streaming. Sem chamada real à Groq (`httpx.MockTransport`) e
  sem `sleep` (relógio injetado), roda em segundos
- **Pipeline de CI** (`.github/workflows/ci.yml`) com `ruff check` e `pytest` em todo push e PR
  para `main` e `develop`, usando apenas actions oficiais
- **Rate limit por IP** com janela deslizante em memória (`app/ratelimit.py`), respondendo
  `429` com header `Retry-After`. Configurável por `RATE_LIMIT_REQUESTS` e
  `RATE_LIMIT_WINDOW_SECONDS`
- **Credencial opcional** no header `X-API-Key`, ativada por `API_KEY`, com comparação em
  tempo constante. Desligada por padrão
- **Conversa multi-turno**: campo `history` opcional em `POST /chat`. O servidor segue sem
  estado — o histórico vem do app e é validado (6 mensagens, 6000 caracteres somados)
- **Endpoint `POST /chat/stream`** com resposta em SSE, reduzindo a latência percebida.
  Fallback entre modelos só antes do primeiro texto emitido, para não duplicar conteúdo
- **Cache de respostas** com TTL e descarte do menos usado (`app/cache.py`), aplicado a
  perguntas sem histórico. Configurável por `CACHE_TTL_SECONDS` e `CACHE_MAX_ENTRIES`
- **Log de custo por chamada**: modelo, latência e tokens (prompt, completion, total),
  além de `cache hit` para medir a taxa de acerto
- `requirements-dev.txt` e `pyproject.toml` com configuração de ruff e pytest

### Changed
- `requests` substituído por `httpx` com cliente assíncrono e pool de conexões reaproveitado
  entre requisições, removendo o limite de concorrência do threadpool do FastAPI
- Fallback entre modelos agora avança apenas em falhas transitórias (rede, `408`, `409`, `429`,
  `404`, `5xx`); erros de credencial ou payload (`400`, `401`, `403`, `422`) interrompem na
  primeira tentativa em vez de consumir as três
- Filtro de domínio passou a casar palavras inteiras sobre texto normalizado (sem acentos e sem
  pontuação), eliminando falsos positivos como "copa do mundo", "casa" e "chamada", e cobrindo
  variações como "churras", "maturação" e "dry-aged" sem entradas duplicadas
- Falha ao gerar resposta agora retorna `503` mantendo o contrato `{"response": "..."}`,
  permitindo retry do cliente em vez de `200` com mensagem de erro ou `500` sem tratamento
- Dependências fixadas por versão compatível (`~=`) em `requirements.txt`
- O filtro de domínio passou a considerar os 2 turnos anteriores: follow-ups sem palavra-chave
  própria ("e para 10 pessoas?") eram recusados antes de chegar à IA
- `normalize()` promovido a função pública em `app/filter.py`, reaproveitado como chave de
  cache — "Picanha?" e "picanha" passam a compartilhar a mesma entrada

### Fixed
- Exceção de rede na chamada à Groq resultava em `500` sem tratamento
- Ausência de timeout podia manter um worker do uvicorn preso até o limite da plataforma
- `CORSMiddleware` combinava `allow_origins=["*"]` com `allow_credentials=True`, combinação
  inválida pela especificação e ignorada pelos navegadores

### Security
- `print` da resposta completa da IA substituído por `logging` estruturado que não registra
  conteúdo do usuário nem corpo da resposta
- Métodos e headers do CORS restringidos ao que a API realmente usa
- Endpoint público sem qualquer limite era um proxy de LLM gratuito para quem descobrisse a URL,
  com o custo debitado do projeto
- Headers do CORS ampliados para incluir `X-API-Key`, mantendo a lista restritiva

---

## [1.0.0] - 2026-05-02
### Versão inicial

### Added
- API FastAPI com `GET /` (healthcheck) e `POST /chat`
- Integração com a Groq API e cascata de três modelos
- Filtro de domínio por palavras-chave de carnes, cortes e preparo
- System prompt com base de conhecimento sobre cortes, técnicas, armazenamento e
  sazonalidade do mercado brasileiro
- Deploy no Render (`start.sh`, `runtime.txt`)
