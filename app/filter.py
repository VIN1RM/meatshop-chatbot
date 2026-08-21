"""Filtro de domínio: decide se vale a pena gastar uma chamada de IA.

Casa palavras inteiras (não substrings) sobre um texto normalizado — minúsculas,
sem acentos e sem pontuação. Isso resolve dois problemas de uma vez:

- falsos positivos: "asa" não casa mais dentro de "casa", nem "cha" dentro de "chamada";
- duplicidade: "acém"/"acem" e "dry-aged"/"dry aged" viram uma única entrada.

TERMS casa a palavra exata (com plural opcional). STEMS casa o radical seguido de
qualquer sufixo — use apenas quando o radical não é prefixo de palavras comuns
fora do domínio.
"""

import re
import unicodedata

# Palavras e expressões exatas (plural tolerado automaticamente).
TERMS = (
    # ── Bovino – cortes de primeira ──
    "carne", "bife", "picanha", "alcatra", "contrafile", "file",
    "file mignon", "filet", "fraldinha", "maminha", "patinho",
    "coxao", "coxao mole", "coxao duro", "lagarto", "vazio",
    "cha de dentro", "cha de fora",

    # ── Bovino – cortes de segunda ──
    "acem", "paleta", "musculo", "cupim", "costela", "costelinha",
    "costelao", "ponta de agulha", "ripa", "agulha",

    # ── Bovino – cortes de terceira / miúdos ──
    "rabo", "rabada", "pescoco", "mocoto", "tutano", "ossobuco",
    "miudo", "figado", "bucho", "dobradinha",
    "coracao bovino", "coracao de frango",

    # ── Bovino – premium / internacional ──
    "ribeye", "new york strip", "t bone", "prime rib", "tomahawk",
    "flat iron", "chuck", "steak", "wagyu", "angus",
    "dry aged", "wet aged", "marmoreio", "marmorizada",

    # ── Regionalismos ──
    "entrecote", "bife do lombo", "janela", "boi de chao",

    # ── Suíno ──
    "porco", "lombo", "pernil", "bacon", "linguica", "panceta",
    "pancetta", "bisteca", "copa lombo", "toucinho", "leitao",
    "barriga de porco", "pulled pork", "carre", "calabresa", "toscana",

    # ── Frango e aves ──
    "frango", "galinha", "galeto", "sobrecoxa", "coxa", "asa", "asinha",
    "peito de frango", "coxinha da asa", "chester", "peru", "pato",
    "codorna", "ave",

    # ── Peixe e frutos do mar ──
    "peixe", "salmao", "atum", "tilapia", "bacalhau", "sardinha",
    "camarao", "polvo", "lula", "marisco", "ostra", "robalo", "tainha",
    "pintado", "corvina", "merluza", "cacao", "frutos do mar",

    # ── Preparo e técnicas ──
    "brasa", "carvao", "lenha", "forno", "frigideira", "panela",
    "panela de pressao", "slow cooker", "air fryer", "sous vide",
    "espeto", "espetinho", "bafo", "no bafo", "baixa temperatura",
    "fogo baixo", "fogo alto", "vacuo", "a vacuo", "salmoura",
    "defumador", "assar", "assado", "assada", "selar", "selado", "dourar",

    # ── Pontos da carne ──
    "mal passado", "ao ponto", "bem passado", "medium rare", "medium",
    "rare", "well done", "ponto da carne", "passadao", "termometro",

    # ── Receitas e contexto culinário ──
    "receita", "molho", "acompanhamento", "farofa", "vinagrete",
    "chimichurri", "sal grosso", "sal fino", "pao de alho",
    "hamburguer", "burger", "smash", "estrogonofe", "picadinho",
    "ensopado", "feijoada", "caldo", "caldinho", "medalhao",
    "escalope", "milanesa", "parmegiana", "boeuf", "rosbife",
    "carne louca", "carne seca", "charque", "carne de sol",
    "carreteiro", "matambre", "chorizo", "tataki",

    # ── Armazenamento e segurança alimentar ──
    "geladeira", "freezer", "validade", "carne fresca", "carne vencida",
    "cheiro da carne", "cor da carne",

    # ── Datas e ocasiões ──
    "ceia", "pascoa", "natal", "carnaval", "festa junina",
    "dia dos pais", "dia das maes", "confraternizacao", "reveillon",

    # ── Contexto do app ──
    "acougue", "pedido", "entrega", "delivery", "retirada",
    "meatshop", "meat shop",

    # ── Quantidade e planejamento ──
    "quanto comprar", "quanto de carne", "quantas pessoas",
    "porcao", "gramas por pessoa", "grama", "quilo", "kg",

    # ── Genéricos do domínio ──
    "corte", "proteina", "gordura", "osso",
)

# Radicais: casam qualquer sufixo (churras → churrasco, churrasqueira, churrascão).
STEMS = (
    "churras", "grelha", "cozi", "temper", "matura", "defuma", "marina",
    "congela", "descongela", "armazena", "conserva", "suculent", "fatia",
    "desfia", "promo", "suin", "bovin", "moid",
)


def normalize(text: str) -> str:
    """Minúsculas, sem acentos, pontuação virando espaço.

    Também serve de chave de cache: "Picanha?" e "picanha" viram a mesma string.
    """
    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def _phrase(term: str) -> str:
    """Expressão de várias palavras tolerante a espaçamento e hífen."""
    return r"\s+".join(re.escape(word) for word in normalize(term).split())


_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(
        [rf"{_phrase(term)}(?:es|s)?" for term in TERMS]
        + [rf"{_phrase(stem)}\w*" for stem in STEMS]
    )
    + r")\b"
)


def is_meat_related(text: str) -> bool:
    return bool(_PATTERN.search(normalize(text)))
