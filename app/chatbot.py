import os
import requests
from dotenv import load_dotenv
from app.prompt import SYSTEM_PROMPT
from app.filter import is_meat_related

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b"
]

def get_response(user_input: str) -> str:
    if not is_meat_related(user_input):
        return "Não posso ajudar com esse assunto."

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    for model in MODELS:
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ]
        }

        response = requests.post(url, headers=headers, json=data)
        result = response.json()

        print("MODEL:", model)
        print("STATUS:", response.status_code)
        print("RESPOSTA:", result)

        if "choices" in result:
            return result["choices"][0]["message"]["content"]

    return "Erro ao gerar resposta com IA."