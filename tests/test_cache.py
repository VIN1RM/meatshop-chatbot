import pytest

from app.cache import TTLCache


@pytest.fixture
def criar_cache(relogio):
    def _criar(ttl=60.0, max_entries=3):
        return TTLCache(ttl, max_entries, clock=relogio)

    return _criar


def test_guarda_e_devolve(criar_cache):
    c = criar_cache()
    c.set("picanha", "resposta")
    assert c.get("picanha") == "resposta"


def test_chave_ausente_devolve_none(criar_cache):
    assert criar_cache().get("inexistente") is None


def test_expira_apos_o_ttl(criar_cache, relogio):
    c = criar_cache(ttl=60.0)
    c.set("picanha", "resposta")

    relogio.avancar(59)
    assert c.get("picanha") == "resposta"

    relogio.avancar(2)
    assert c.get("picanha") is None


def test_descarta_o_menos_usado_ao_encher(criar_cache):
    c = criar_cache(max_entries=2)
    c.set("a", "1")
    c.set("b", "2")
    c.get("a")  # "a" passa a ser o mais recente
    c.set("c", "3")

    assert c.get("b") is None
    assert c.get("a") == "1"
    assert c.get("c") == "3"


def test_ttl_zero_desliga_o_cache(criar_cache):
    c = criar_cache(ttl=0)
    assert not c.enabled
    c.set("picanha", "resposta")
    assert c.get("picanha") is None


def test_clear_esvazia(criar_cache):
    c = criar_cache()
    c.set("picanha", "resposta")
    c.clear()
    assert c.get("picanha") is None
