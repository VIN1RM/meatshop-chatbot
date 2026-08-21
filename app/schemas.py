from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    # O limite protege o custo por chamada: prompt gigante = token gasto sem retorno.
    message: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    response: str
