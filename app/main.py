from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import ChatRequest, ChatResponse
from app.chatbot import get_response

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "MeatShop Chatbot rodando 🚀"}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    resposta = get_response(req.message)
    return ChatResponse(response=resposta)