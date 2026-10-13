from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# O chatbot continua sem estado: o backend principal envia o histórico confiável a cada chamada.
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
    history: list[Message] = Field(default_factory=list, max_length=MAX_HISTORY_MESSAGES)
    locale: Literal["pt-BR"] = "pt-BR"

    @model_validator(mode="after")
    def validar_tamanho_do_historico(self) -> "ChatRequest":
        total = sum(len(msg.content) for msg in self.history)
        if total > MAX_HISTORY_CHARS:
            raise ValueError(f"histórico excede {MAX_HISTORY_CHARS} caracteres somados")
        return self


class ChatResponse(BaseModel):
    response: str
    request_id: str | None = None


class CatalogProduct(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=150)
    unit_of_measure: str = Field(min_length=1, max_length=50)


class RecipeDraftRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    brief: str = Field(min_length=3, max_length=1000)
    servings: int = Field(default=4, ge=1, le=100)
    tag: str | None = Field(default=None, max_length=50)
    products: list[CatalogProduct] = Field(default_factory=list, max_length=20)


class RecipeDraftIngredient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=150)
    quantity: str = Field(min_length=1, max_length=50)
    tip: str | None = Field(max_length=500)


class RecipeDraftStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_number: int = Field(ge=1, le=30)
    description: str = Field(min_length=1, max_length=1500)
    tip: str | None = Field(max_length=500)


class RecipeDraftProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(gt=0)
    call_to_action: str = Field(min_length=1, max_length=255)


class RecipeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=1000)
    tag: str = Field(min_length=1, max_length=50)
    ingredients: list[RecipeDraftIngredient] = Field(min_length=1, max_length=40)
    steps: list[RecipeDraftStep] = Field(min_length=1, max_length=30)
    products: list[RecipeDraftProduct] = Field(max_length=20)
    safety_notice: str = Field(min_length=1, max_length=500)


class RecipeDraftResponse(BaseModel):
    draft: RecipeDraft
    request_id: str | None = None
