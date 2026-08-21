import pytest

from app.ratelimit import SlidingWindowRateLimiter


@pytest.fixture
def criar_limiter(relogio):
    def _criar(max_requests=3, window=60.0):
        return SlidingWindowRateLimiter(max_requests, window, clock=relogio)

    return _criar


def test_permite_ate_o_limite(criar_limiter):
    rl = criar_limiter(max_requests=3)
    assert [rl.check("ip") for _ in range(3)] == [None, None, None]


def test_bloqueia_acima_do_limite_e_informa_espera(criar_limiter):
    rl = criar_limiter(max_requests=3, window=60.0)
    for _ in range(3):
        rl.check("ip")

    espera = rl.check("ip")
    assert espera is not None
    assert 0 < espera <= 60.0


def test_libera_quando_a_janela_desliza(criar_limiter, relogio):
    rl = criar_limiter(max_requests=2, window=60.0)
    rl.check("ip")
    rl.check("ip")
    assert rl.check("ip") is not None

    relogio.avancar(61)
    assert rl.check("ip") is None


def test_janela_e_deslizante_nao_fixa(criar_limiter, relogio):
    rl = criar_limiter(max_requests=2, window=60.0)
    rl.check("ip")
    relogio.avancar(40)
    rl.check("ip")
    assert rl.check("ip") is not None

    # Passam 21s: o primeiro acesso saiu da janela, o segundo (em +40s) ainda não.
    relogio.avancar(21)
    assert rl.check("ip") is None
    assert rl.check("ip") is not None


def test_chaves_sao_independentes(criar_limiter):
    rl = criar_limiter(max_requests=1)
    assert rl.check("ip-a") is None
    assert rl.check("ip-a") is not None
    assert rl.check("ip-b") is None


def test_purga_chaves_ociosas(criar_limiter, relogio):
    rl = criar_limiter(max_requests=1, window=10.0)
    rl.check("efemero")
    relogio.avancar(11)

    # A varredura roda por contagem de verificações; força o ciclo.
    for _ in range(1000):
        rl.check("estavel")

    assert "efemero" not in rl._hits
