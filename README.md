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


Flutter App → FastAPI → Filtro de domínio → Groq API → Resposta


O filtro de domínio (`app/filter.py`) casa palavras inteiras sobre o texto normalizado
(sem acentos e sem pontuação). Se nada casar, a resposta é local — sem gastar chamada de IA.

A chamada à Groq tem timeout e faz fallback em cascata entre três modelos. O fallback só
avança em falhas transitórias (rede, 429, 5xx, modelo descontinuado); erros de credencial
ou de payload interrompem na primeira tentativa.

---

## ⚙️ Tecnologias

- Python 3.12
- FastAPI
- HTTPX (cliente assíncrono com pool de conexões)
- Groq API
- Python-dotenv
- Render (deploy)

---

## 🌐 URL da API


https://meatshop-chatbot.onrender.com


---

## 🔌 Endpoints

### `GET /`
Healthcheck.

### `POST /chat`

**Request**
```json
{ "message": "qual a melhor carne para churrasco?" }
```

**Response — 200**
```json
{ "response": "..." }
```

| Status | Quando |
|---|---|
| `200` | Resposta da IA ou recusa de domínio |
| `422` | `message` vazia ou acima de 1000 caracteres |
| `503` | Nenhum modelo conseguiu responder — o cliente pode tentar novamente |

O corpo é sempre `{ "response": "..." }`, inclusive no `503`.

---

## 🔐 Variáveis de ambiente

Copie `.env.example` para `.env` e preencha:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `GROQ_API_KEY` | Sim | Chave da API da Groq |
| `ALLOWED_ORIGINS` | Não | Origens do CORS separadas por vírgula (padrão `*`) |
| `LOG_LEVEL` | Não | `DEBUG`, `INFO`, `WARNING`, `ERROR` (padrão `INFO`) |

---

## 💻 Execução local

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Documentação interativa em `http://127.0.0.1:8000/docs`.

---

