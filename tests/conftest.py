import pytest

from app.chatbot import RESPONSE_CACHE
from app.main import rate_limiter


class RelogioFalso:
    """Evita sleep nos testes: o tempo anda quando o teste manda."""

    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora

    def avancar(self, segundos: float) -> None:
        self.agora += segundos


@pytest.fixture
def relogio():
    return RelogioFalso()


@pytest.fixture(autouse=True)
def estado_limpo():
    """Cache e rate limit vivem no processo: sem reset, um teste contamina o próximo."""
    RESPONSE_CACHE.clear()
    rate_limiter.reset()
    yield
    RESPONSE_CACHE.clear()
    rate_limiter.reset()
