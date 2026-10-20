"""Local privacy and prompt-injection guardrails applied before provider calls."""

import re

SAFETY_REFUSAL = (
    "Não posso seguir instruções para alterar ou revelar minhas regras. "
    "Posso ajudar com carnes, receitas, cortes e preparo."
)

_INJECTION = re.compile(
    r"\b(?:ignore|ignorar|desconsidere|esqueça|revele|mostre|imprima|bypass|contorne)\b"
    r".{0,80}\b(?:instruç(?:ão|ões)|regra|prompt|sistema|system|anterior|segredo)\b",
    re.IGNORECASE | re.DOTALL,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_CPF = re.compile(r"(?<!\d)\d{3}[.\s-]?\d{3}[.\s-]?\d{3}[-.\s]?\d{2}(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-\s]?\d{4}(?!\d)")


def is_prompt_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


def redact_sensitive(text: str) -> str:
    text = _EMAIL.sub("[e-mail removido]", text)
    text = _CPF.sub("[CPF removido]", text)
    return _PHONE.sub("[telefone removido]", text)
