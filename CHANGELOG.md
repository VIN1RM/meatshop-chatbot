# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

---

## [Projeto ainda não publicado]

---

## [1.1.0] - 2026-08-21
### Endurecimento da API para produção

### Added
- `.env.example` com as variáveis suportadas e comentário descritivo em cada uma
- `ALLOWED_ORIGINS` para restringir as origens do CORS por ambiente
- `LOG_LEVEL` para controlar a verbosidade dos logs
- Validação de entrada em `POST /chat`: `message` entre 1 e 1000 caracteres (`422` fora da faixa)
- Timeout explícito nas chamadas à Groq (5s de conexão, 30s de leitura)
- Documentação de endpoints, variáveis de ambiente e execução local no README

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

### Fixed
- Exceção de rede na chamada à Groq resultava em `500` sem tratamento
- Ausência de timeout podia manter um worker do uvicorn preso até o limite da plataforma
- `CORSMiddleware` combinava `allow_origins=["*"]` com `allow_credentials=True`, combinação
  inválida pela especificação e ignorada pelos navegadores

### Security
- `print` da resposta completa da IA substituído por `logging` estruturado que não registra
  conteúdo do usuário nem corpo da resposta
- Métodos e headers do CORS restringidos ao que a API realmente usa

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
