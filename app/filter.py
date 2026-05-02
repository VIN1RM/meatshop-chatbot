def is_meat_related(text: str) -> bool:
    keywords = [
        # ── Bovino – cortes de primeira ──
        "carne", "bife", "picanha", "alcatra", "contrafilé", "filé",
        "filé-mignon", "file mignon", "fraldinha", "maminha", "patinho",
        "coxão", "coxao", "lagarto", "vazio",

        # ── Bovino – cortes de segunda ──
        "acém", "acem", "paleta", "músculo", "musculo", "cupim",
        "costela", "ponta de agulha", "ripa",

        # ── Bovino – cortes de terceira / especiais ──
        "rabo", "pescoço", "pescoco", "mocotó", "mocoto",
        "tutano", "ossobuco", "miúdo", "miudo", "fígado", "figado",
        "coração bovino", "bucho", "dobradinha",

        # ── Bovino – premium / internacional ──
        "ribeye", "new york strip", "t-bone", "prime rib", "tomahawk",
        "flat iron", "chuck", "steak", "wagyu", "angus",
        "dry-aged", "dry aged", "wet-aged", "wet aged", "maturad",

        # ── Regional brasileiro ──
        "chã", "cha de dentro", "cha de fora", "entrecôte", "entrecote",
        "bife do lombo", "janela", "agulha",

        # ── Suíno ──
        "porco", "suíno", "suino", "lombo", "pernil", "bacon",
        "linguiça", "linguica", "costelinha", "panceta", "pancetta",
        "bisteca", "copa lombo", "copa", "toucinho", "leitão", "leitao",
        "barriga de porco", "paleta suína", "pulled pork", "carré",

        # ── Frango e aves ──
        "frango", "sobrecoxa", "coxa", "peito de frango", "asa",
        "chester", "peru", "pato", "codorna", "coração de frango",
        "coxinha da asa", "frango inteiro", "frango caipira",
        "galinha", "galeto",

        # ── Peixe e frutos do mar ──
        "peixe", "salmão", "salmao", "atum", "tilápia", "tilapia",
        "bacalhau", "sardinha", "camarão", "camarao", "polvo",
        "lula", "mariscos", "ostra", "robalo", "tainha", "pintado",
        "corvina", "merluza", "cação",

        # ── Preparo e técnicas ──
        "churrasco", "grelhar", "grelha", "assar", "assado",
        "cozinhar", "marinar", "marinada", "temperar", "tempero",
        "defumar", "defumado", "selar", "dourar",
        "brasa", "carvão", "carvao", "lenha", "forno", "frigideira",
        "panela de pressão", "slow cooker", "churrasqueira",
        "bafo", "no bafo", "lento", "baixa temperatura",

        # ── Pontos da carne ──
        "mal passado", "ao ponto", "bem passado", "medium", "rare",
        "ponto da carne", "suculento", "suculenta",

        # ── Receitas e contexto culinário ──
        "receita", "molho", "acompanhamento", "farofa", "vinagrete",
        "chimichurri", "sal grosso", "sal fino", "tempero",
        "hamburguer", "hambúrguer", "burger", "smash",
        "estrogonofe", "picadinho", "ensopado", "cozido", "rabada",
        "feijoada", "mocotó", "dobradinha", "caldinho",
        "medalhão", "escalope", "milanesa", "parmegiana",
        "boeuf", "rosbife", "carne louca", "carne desfiada",
        "carreteiro", "costelão",

        # ── Armazenamento e segurança alimentar ──
        "descongelar", "congelar", "geladeira", "freezer",
        "validade", "armazenar", "armazenamento", "conservar",
        "carne fresca", "carne vencida", "cheiro de carne",
        "cor da carne",

        # ── Datas e ocasiões ──
        "churrasco de natal", "ceia", "páscoa", "pascoa",
        "festa junina", "dia dos pais", "dia das mães",
        "confraternização", "confraternizacao", "churrascão",
        "churrascao", "réveillon", "reveillon",

        # ── Contexto do app ──
        "açougue", "acougue", "pedido", "entrega", "delivery",
        "promoção", "promocao", "meatshop", "meat shop",

        # ── Quantidade e planejamento ──
        "quanto comprar", "quanto de carne", "quantas pessoas",
        "porção", "porcao", "gramas por pessoa",
    ]
    text = text.lower()
    return any(word in text for word in keywords)