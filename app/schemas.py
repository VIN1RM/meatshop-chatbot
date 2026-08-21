from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# O servidor continua sem estado: o histórico vem do app a cada requisição.
# Os limites existem para conter o custo por chamada — histórico longo é token pago.
MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_CHARS = 6000


class Message(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=1000)
    history: list[Message] = Field(
        default_factory=list, max_length=MAX_HISTORY_MESSAGES
    )

    @model_validator(mode="after")
    def validar_tamanho_do_historico(self) -> "ChatRequest":
        total = sum(len(msg.content) for msg in self.history)
        if total > MAX_HISTORY_CHARS:
            raise ValueError(
                f"histórico excede {MAX_HISTORY_CHARS} caracteres somados"
            )
        return self


class ChatResponse(BaseModel):
    response: str
