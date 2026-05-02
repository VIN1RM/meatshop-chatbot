def is_meat_related(text: str) -> bool:
    keywords = [
        "carne", "bife", "picanha", "frango", "porco",
        "churrasco", "grelhar", "assado", "receita",
        "corte", "costela", "steak", "hamburguer"
    ]

    text = text.lower()

    return any(word in text for word in keywords)