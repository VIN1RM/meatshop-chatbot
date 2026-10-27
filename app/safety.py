"""Local privacy and prompt-injection guardrails applied before provider calls."""

import re
import unicodedata

from app.filter import is_meat_related

SAFETY_REFUSAL = (
    "Não posso seguir instruções para alterar ou revelar minhas regras. "
    "Posso ajudar com carnes, receitas, cortes e preparo."
)

NAME_PLACEHOLDER = "[nome removido]"
_INSTRUCTION_WORDS = {
    "ignore",
    "ignorar",
    "desconsidere",
    "esqueca",
    "revele",
    "mostre",
    "imprima",
    "bypass",
    "contorne",
}
_NAME_BOUNDARIES = {
    "e",
    "quero",
    "gostaria",
    "preciso",
    "moro",
    "resido",
    "tenho",
    "meu",
    "minha",
    "para",
    "com",
    "mas",
    "pois",
    "estou",
    "vou",
    "pode",
    "qual",
    "onde",
    "como",
    "hoje",
    "amanha",
    "telefone",
    "email",
    "endereco",
    "cpf",
    "cep",
    "faco",
    "trabalho",
    "gosto",
    "procuro",
    "prefiro",
    *_INSTRUCTION_WORDS,
}

_INJECTION = re.compile(
    r"\b(?:ignore|ignorar|desconsidere|esqueça|revele|mostre|imprima|bypass|contorne)\b"
    r".{0,80}\b(?:instruç(?:ão|ões)|regra|prompt|sistema|system|anterior|segredo)\b",
    re.IGNORECASE | re.DOTALL,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_CPF = re.compile(r"(?<!\d)\d{3}[.\s-]?\d{3}[.\s-]?\d{3}[-.\s]?\d{2}(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-\s]?\d{4}(?!\d)")
_CEP = re.compile(r"(?<!\d)\d{5}-\d{3}(?!\d)|\bCEP:?\s*\d{8}(?!\d)", re.IGNORECASE)
_ADDRESS = re.compile(
    r"\b(?:rua|avenida|av\.?|travessa|alameda|rodovia)\s+"
    r"[^\W\d_][\w.'\- ]{0,60}?,?\s*(?:n[º°o]?\.?\s*)?\d{1,6}\b",
    re.IGNORECASE,
)
_ANY_CASE_WORD = r"[^\W\d_]{2,}(?:['-][^\W\d_]+)?"
_CAPITALIZED_WORD = r"[A-ZÀ-Ý][a-zà-ÿ'-]+"
_SURNAMES = rf"(?:\s+(?:d[aeo]s?\s+)?{_ANY_CASE_WORD}){{0,3}}"
_NAME_INTRO = re.compile(rf"(\b(?i:meu nome (?:é|e)|me chamo)\s+)({_ANY_CASE_WORD}{_SURNAMES})")
_NAME_SOU = re.compile(rf"(\b(?i:sou (?:o|a))\s+)({_CAPITALIZED_WORD}{_SURNAMES})")


def is_prompt_injection(text: str) -> bool:
    return bool(_INJECTION.search(unicodedata.normalize("NFC", text)))


def _normalize_name_word(word: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", word.casefold())
        if not unicodedata.combining(char)
    )


def _replace_name(match: re.Match[str]) -> str:
    first_word = match.group(2).split()[0]
    if is_meat_related(first_word) or _normalize_name_word(first_word) in _INSTRUCTION_WORDS:
        return match.group(0)
    name = match.group(2)
    for index, word in enumerate(re.finditer(r"\S+", name)):
        normalized = _normalize_name_word(word.group())
        if index and normalized in _NAME_BOUNDARIES:
            spacing = re.search(r"\s+$", name[: word.start()])
            suffix = f"{spacing.group() if spacing else ' '}{name[word.start() :]}"
            return f"{match.group(1)}{NAME_PLACEHOLDER}{suffix}"
    return f"{match.group(1)}{NAME_PLACEHOLDER}"


def _redact_names(text: str) -> str:
    text = _NAME_INTRO.sub(_replace_name, text)
    return _NAME_SOU.sub(_replace_name, text)


def redact_sensitive(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = _EMAIL.sub("[e-mail removido]", text)
    text = _CPF.sub("[CPF removido]", text)
    text = _CEP.sub("[CEP removido]", text)
    text = _PHONE.sub("[telefone removido]", text)
    text = _ADDRESS.sub("[endereço removido]", text)
    return _redact_names(text)
