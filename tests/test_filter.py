import pytest

from app.filter import is_meat_related, normalize

NO_DOMINIO = [
    "qual a melhor picanha pra churrasco?",
    "como faço um churras pra 10 pessoas?",
    "o que e maturacao a seco?",
    "quanto tempo dura frango na geladeira",
    "quero uma receita de costela no bafo",
    "o que significa dry-aged?",
    "acem ou musculo pra ensopado?",
    "COMO TEMPERAR CONTRAFILE",
    "carne moida ta com cheiro ruim",
    "qual a temperatura interna segura do porco",
    "quantos quilos por pessoa?",
    "tem promoção de linguiça?",
    "salmão na frigideira",
    "meu pedido no açougue atrasou",
]

FORA_DO_DOMINIO = [
    "quem ganhou a copa do mundo?",
    "minha casa esta suja",
    "fiz uma chamada e caiu",
    "o app esta travando",
    "qual a capital da Franca?",
    "me fala sobre patologia clinica",
    "preciso de um advogado",
    "bom dia",
]


@pytest.mark.parametrize("texto", NO_DOMINIO)
def test_aceita_perguntas_do_dominio(texto):
    assert is_meat_related(texto)


@pytest.mark.parametrize("texto", FORA_DO_DOMINIO)
def test_rejeita_perguntas_fora_do_dominio(texto):
    assert not is_meat_related(texto)


def test_acentos_e_pontuacao_nao_alteram_o_resultado():
    assert is_meat_related("Açém!") == is_meat_related("acem")
    assert is_meat_related("dry-aged") == is_meat_related("dry aged")


def test_normalize_gera_chave_estavel():
    assert normalize("  Picanha, no ponto?  ") == "picanha no ponto"
    assert normalize("PICANHA no ponto") == normalize("picanha   no  ponto")


def test_texto_vazio_nao_e_do_dominio():
    assert not is_meat_related("")
    assert not is_meat_related("   ")
