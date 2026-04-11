"""
Classificador unificado — 3 filtros + consciência de incerteza + Fase 11:

1. TOM        — como responder
2. RELEVÂNCIA — o que salvar
3. TIPO       — onde salvar (inclui LICAO — Fase 11)
4. INCERTEZA  — se o agente deve admitir limitação de dados
5. VOLATILIDADE + ESCOPO — política de busca (Fase 16)

Uma chamada ao GROQ, seis saídas.
"""

from core.logger import info, debug, erro

TONS = {
    "CASUAL":    "conversa leve, resposta curta e informal, sem bullet points",
    "HUMOR":     "usuário quer rir ou descontrair, pode ser criativo e leve",
    "TECNICO":   "quer solução precisa, direto ao ponto, use código se precisar",
    "URGENTE":   "problema acontecendo agora, solução já na primeira linha",
    "PROJETO":   "está planejando algo, pense junto, carregue livro_projetos",
    "REFLEXIVO": "quer explorar ideias, resposta mais aberta e aprofundada",
}

RELEVÂNCIAS = {
    "ALTA":  "salva automaticamente — bug, decisão, solução, configuração específica",
    "MEDIA": "pede confirmação — pode ser útil mas não é certeza",
    "BAIXA": "descarta — piada, conversa casual, pergunta genérica, small talk",
}

TIPOS = {
    "SEMANTICA":   "fato estável do projeto — arquitetura, configuração, decisão permanente",
    "EPISODICA":   "evento específico com data — bug resolvido, tarefa executada",
    "PROJETO":     "planejamento, requisito, ideia para projeto futuro",
    "DESCARTAVEL": "não merece ser salvo",
    "LICAO":       "correção do usuário, erro do agente confirmado, anti-padrão — Fase 11",
}

# ── Mentoria — acessa livro_mentores diretamente, zero busca externa ─────────
_PALAVRAS_MENTORES = [
    "livro_mentores", "livro de mentores", "meus mentores",
    "mentor", "mentores", "raciocínio de", "raciocinio de",
    "como pensaria", "como pensa", "estratégia de", "estrategia de",
    "conselho de", "o que diria", "visão de", "visao de",
    "einstein", "feynman", "tesla", "turing", "darwin",
    "da vinci", "drucker", "jung", "curie", "von neumann",
]

# ── FASE 16: ESCOPO + VOLATILIDADE ──────────────────────────────────────────
_PALAVRAS_IDENTIDADE = [
    "quem voce", "quem você", "quem és", "quem e voce", "quem é você",
    "o que voce e", "o que você é", "o que é voce",
    "qual seu nome", "como voce se chama", "como você se chama",
    "me fale de voce", "me fale de você", "fale sobre voce", "fale sobre você",
    "voce e um agente", "você é um agente",
    "quem te criou", "quem te fez", "quem te desenvolveu",
    "me apresente", "se apresente", "sua identidade",
    "como voce funciona", "como você funciona",
    "o que e voce", "o que é você",
    "sabe quem eu sou", "sabe quem sou", "quem sou eu",
    "voce me conhece", "você me conhece",
    "sabe quem e", "sabe quem é",
]

_PALAVRAS_DADO_REALTIME = [
    "preco", "preço", "cotacao", "cotação",
    "dolar", "dollar", "euro", "bitcoin", "btc", "eth", "ethereum",
    "selic", "ibovespa", "bolsa", "taxa", "juros",
    "temperatura", "clima",
    "resultado", "placar", "quem ganhou", "quem venceu",
    "eleicao", "eleição", "presidente", "governador",
    "oportunidades financeiras", "oportunidade financeira",
    "oportunidade de renda", "oportunidades de renda",
    "oportunidade de negocio", "oportunidades de negocio",
    "oportunidade de negócio", "oportunidades de negócio",
    "renda extra", "renda passiva", "ganhar dinheiro",
    "petroleo", "petróleo", "ouro", "prata", "cobre", "soja", "milho",
    "commodities", "commodity", "brent", "wti", "gas", "gás natural",
    "acoes", "ações", "fundos", "cripto", "nft",
    "dolar", "dollar", "euro", "libra", "iene", "yuan",
]

_MODIFICADORES_TEMPO = ["hoje", "agora", "neste momento", "no momento"]

_PALAVRAS_WORLD_STATE = _PALAVRAS_DADO_REALTIME + _MODIFICADORES_TEMPO

_PALAVRAS_MERCHANT = [
    "loja", "produto", "preco em", "preço em", "comprar", "frete",
    "disponivel", "disponível", "estoque", "entrega", "site de",
    "mercado livre", "amazon", "shopee", "americanas", "magazine",
]

_PALAVRAS_ENCYCLOPEDIC = [
    "quem foi", "o que e", "o que é", "quando foi fundad",
    "definicao", "definição", "historia de", "história de",
    "origem do", "origem da", "criado em", "inventado por",
]

_PALAVRAS_CONVERSACIONAL = [
    "oi", "olá", "ola", "hey", "eai", "e aí", "tudo bem", "tudo bom",
    "boa noite", "bom dia", "boa tarde", "até logo", "ate logo", "tchau",
    "obrigado", "obrigada", "valeu", "tmj",
    "como vai", "como você está", "como voce esta", "como foi seu dia",
    "foi um dia", "meu dia", "seu dia",
    "como esta seu humor", "como está seu humor", "seu humor", "como esta", "como está",
    "podemos ter", "posso te", "bater papo", "conversa casual",
    "era so", "era só", "sim ou não", "sim ou nao",
    "treinamento llama", "treinamento seu", "treinamento meu",
    "dia todo", "o dia todo", "hoje foi", "foi um dia cheio", "foi um dia",
    "certo", "entendido", "ok", "combinado", "perfeito", "bacana", "certo!",
    "legal", "massa", "show", "boa",
    "pode me xingar", "me xinga", "xinga", "pode xingar",
]

_PALAVRAS_SUBJETIVAS = [
    "devo", "deveria", "vale a pena", "compensa", "faz sentido",
    "é certo", "é errado", "devo mudar", "devo continuar", "devo parar",
    "o que fazer", "me ajude a decidir", "como decidir",
    "estou em dúvida", "estou em duvida", "não sei se", "nao sei se",
    "tenho medo de", "será que", "sera que",
    "me arrependo", "foi certo", "foi errado", "poderia ter",
    "minha vida", "meu futuro", "minha carreira", "meu relacionamento",
    "sentido da vida", "sentido de vida", "proposito da vida", "propósito da vida",
    "significado da vida", "para que vivemos", "por que existimos",
    "o que e felicidade", "o que é felicidade", "o que e sucesso",
    "o que é sucesso", "o que e amor", "o que é amor",
    "por que estamos aqui", "qual o proposito", "qual o propósito",
    "vale a pena viver", "o que importa", "o que realmente importa",
]

_PALAVRAS_VOLATEIS = _PALAVRAS_WORLD_STATE

# ── Queries dirigidas ao agente — conversacional, zero busca externa ─────────
# Detecta: "voce/você" + verbo de ação/pergunta SEM dado real externo
_VERBOS_SOBRE_AGENTE = [
    "voce sugere", "você sugere", "voce acha", "você acha",
    "voce vê", "voce ve", "você vê", "você ve",
    "voce percebe", "você percebe", "voce nota", "você nota",
    "voce quer", "você quer", "voce gostaria", "você gostaria",
    "voce tem alguma", "você tem alguma", "voce tem algum", "você tem algum",
    "voce tem algo", "você tem algo",
    "voce diria", "você diria", "voce mudaria", "você mudaria",
    "voce recomenda", "você recomenda", "voce indica", "você indica",
    "voce prefere", "você prefere", "voce escolheria", "você escolheria",
    "voce consegue", "você consegue", "voce pode", "você pode",
    "testes em voce", "testes em você", "testando voce", "testando você",
    "estou testando", "fazendo testes",
    "pergunta para voce", "pergunta para você", "pergunta a voce", "pergunta a você",
    "pergunta que gostaria", "alguma pergunta",
    "sobre voce", "sobre você",
]

_PRONOMES_CONTEXTO = {
    "esse", "essa", "isso", "este", "esta", "isto",
    "aquele", "aquela", "aquilo",
}

_VERBOS_AGENTE = {
    "analisou", "entendeu", "viu", "leu", "rodou", "testou",
    "funcionou", "quebrou", "conseguiu", "fez", "achou",
    "teve", "foi", "criou", "gerou", "executou",
}

_CONFIRMACOES = {
    "sim", "não", "nao", "ok", "certo", "correto", "exato",
    "claro", "entendi", "ótimo", "otimo", "beleza", "pode",
}

_PADROES_INTERNOS = [
    r"fase \d+",
    r"erro \d+",
    r"versao \d+",
    r"versão \d+",
    r"v\d+\.\d+",
    r"quantas? (api|chave|model|livro|fase)",
    r"qual (model|api|chave|fase|livro)",
    r"como funciona (sua|o|a)",
    r"o que (e|é) a fase",
    r"quais livros",
    r"seu status",
    r"status atual",
    r"como (você|voce) (está|esta|tá|ta)",
    r"(você|voce) (está|esta|tá|ta) (bem|ok|funcionando|rodando|online|ativo)",
    r"lembra (que|do|da|de|quando)",
    r"voce (disse|falou|pediu|sugeriu)",
    r"quando (falamos|conversamos|fizemos)",
    r"a gente (decidiu|combinou|fez)",
    r"nos (decidimos|falamos|colocamos)",
    r"suas? memorias",
    r"conversa anterior",
    r"qual seu status",
    r"como o agente (está|esta|ta)",
    r"blocos do livro",
    r"livro de resumo",
    r"livro_resumo",
    r"livros tematicos",
    r"livros temáticos",
    r"livros que voce",
    r"livros que você",
    r"pipeline (atual|do agente|completo)",
    r"fases (ativas|do sistema|completas)",
]

_PADROES_CORRECAO = [
    "não é assim",    "isso está errado",   "você errou",
    "errou de novo",  "já falei isso",       "já disse isso",
    "não faça isso",  "não faça mais isso",  "para de fazer",
    "isso é um erro", "esse é o problema",   "não funciona assim",
    "correção:",      "corrigindo:",         "na verdade",
    "você entendeu errado", "entendeu errado", "interpretou errado",
    "isso não é correto",   "isso está incorreto",
    "lembre-se que",  "preciso que você lembre", "sempre que",
    "nunca faça",     "nunca mais faça",     "não repita",
    "anti-padrão",    "antipadrão",          "evite isso",
    "você inventou",  "está confundindo",    "não foi isso",
]

_PADROES_ENSINO = [
    "lembre que",     "guarde isso",     "regra:",
    "importante:",    "salva isso",      "anota:",
    "para o futuro:", "daqui pra frente", "a partir de agora",
    "sempre faça",    "toda vez que",    "quando eu pedir",
]

_PADROES_INCERTEZA = [
    "quando foi", "qual foi", "quem foi", "quem criou", "quem inventou",
    "em que ano", "qual o ano", "qual data", "quando aconteceu",
    "quantos", "qual o valor", "qual o preco", "qual o preço",
    "primeiro hackathon", "primeiro a", "história de", "historia de",
    "origem do", "origem da", "fundado em", "criado em",
]

_PADROES_RESPOSTA_INCERTA = [
    "ocorreu em 19", "ocorreu em 20", "foi em 19", "foi em 20",
    "no ano de 19", "no ano de 20",
    "aproximadamente", "estima-se", "acredita-se",
    "não tenho certeza", "não tenho informações precisas",
    "pode variar", "segundo algumas fontes",
]

_cache = {}
MAX_CACHE = 200

def _limpar_cache():
    while len(_cache) > MAX_CACHE:
        _cache.pop(next(iter(_cache)))


def _e_saudacao_curta(p: str) -> bool:
    palavras = p.strip().split()
    if len(palavras) <= 6:
        for palavra in palavras:
            if palavra in {"oi", "olá", "ola", "hey", "certo", "ok", "combinado",
                           "perfeito", "bacana", "legal", "massa", "show", "boa",
                           "valeu", "obrigado", "obrigada", "tmj", "entendido"}:
                return True
    return False


def _e_contextual(p: str) -> bool:
    import re
    palavras = p.strip().split()
    n = len(palavras)

    if any(w in p for w in _PALAVRAS_DADO_REALTIME):
        return False

    if palavras and palavras[0] in _CONFIRMACOES:
        return True

    if n <= 6 and any(w in _PRONOMES_CONTEXTO for w in palavras):
        return True

    if n <= 7 and any(w in _VERBOS_AGENTE for w in palavras):
        return True

    if re.search(r"\bvoc[eê]\s+(est[aá]|tem|teve)\b", p):
        return True

    if n <= 1:
        return True

    return False


def _e_dirigida_ao_agente(p: str) -> bool:
    """Detecta queries dirigidas ao agente que não precisam de busca externa.
    Regra: contém 'voce'/'você' sem dado real externo e sem trigger encyclopedic.
    Também cobre verbos explícitos sobre o agente.
    """
    import re as _re
    # Já tratado como identidade — não reclassificar
    if any(k in p for k in _PALAVRAS_IDENTIDADE):
        return False
    # Não pode ter dado real externo
    if any(w in p for w in _PALAVRAS_DADO_REALTIME):
        return False
    # Verbo explícito de ação/pergunta dirigido ao agente
    if any(k in p for k in _VERBOS_SOBRE_AGENTE):
        return True
    # Regex genérico: qualquer frase com voce/você sem trigger encyclopedic
    if _re.search(r'\bvoc[eê]\b', p) and not any(w in p for w in _PALAVRAS_ENCYCLOPEDIC):
        return True
    # "metas e objetivos" sem contexto externo — é conversa interna
    if "metas" in p and "objetivos" in p and not any(w in p for w in _PALAVRAS_ENCYCLOPEDIC):
        return True
    return False


def _detectar_escopo(pergunta: str) -> tuple:
    import re
    p = pergunta.lower()

    # 0. Mentoria
    if any(k in p for k in _PALAVRAS_MENTORES):
        return "mentoria_raciocinio", "baixa", 0

    # 1. Interno — padrões do sistema
    for padrao in _PADROES_INTERNOS:
        if re.search(padrao, p):
            return "internal", "baixa", 0

    # 2. Identidade do agente
    if any(k in p for k in _PALAVRAS_IDENTIDADE):
        return "identidade_interna", "baixa", 0

    # 3. World state — só com dado real externo
    tem_dado_real = any(w in p for w in _PALAVRAS_DADO_REALTIME)
    # Verbos de busca + "agora/hoje" → world_state mesmo sem palavra de dado explícita
    _VERBOS_BUSCA = {"procure", "busque", "pesquise", "encontre", "ache", "procura", "busca"}
    _TEM_VERBO_BUSCA = any(w in p.split() for w in _VERBOS_BUSCA)
    _TEM_URGENCIA = any(w in p for w in ["agora", "hoje", "neste momento", "urgente"])
    if not tem_dado_real and _TEM_VERBO_BUSCA and _TEM_URGENCIA:
        tem_dado_real = True
    if tem_dado_real:
        return "world_state", "alta", 2

    # 4. Conversacional
    if _e_saudacao_curta(p) or any(w in p for w in _PALAVRAS_CONVERSACIONAL):
        return "conversacional", "baixa", 0

    # 5. Query dirigida ao agente — ANTES do encyclopedic
    if _e_dirigida_ao_agente(p):
        return "conversacional", "baixa", 0

    # 5b. Filtro de Ego — "agente" como auto-referência sem verbo encyclopedic
    # "o agente tem metas?", "o agente aprendeu?", "qual o objetivo do agente?"
    import re as _re2
    _VERBOS_ESTADO_AGENTE = [
        "agente aprendeu", "agente evoluiu", "agente tem", "agente esta",
        "agente está", "agente fez", "agente conseguiu", "agente mudou",
        "agente melhorou", "agente piorou", "agente sabe", "agente pode",
        "do agente", "o agente", "agente esta", "agente está", "agente autonomo esta", "agente autonomo está",
    ]
    _tem_ref_agente = any(k in p for k in _VERBOS_ESTADO_AGENTE)
    _tem_verbo_encycl = any(w in p for w in _PALAVRAS_ENCYCLOPEDIC)
    if _tem_ref_agente and not _tem_verbo_encycl and not tem_dado_real:
        return "internal", "baixa", 0

    # 5c. Contextual curto (pronomes, verbos do agente) — depois do ego filter
    if _e_contextual(p):
        return "conversacional", "baixa", 0

    # 6. Subjetivo
    if any(w in p for w in _PALAVRAS_SUBJETIVAS):
        return "subjective_decision", "baixa", 0

    # 7. Merchant
    if any(w in p for w in _PALAVRAS_MERCHANT):
        tem_preco = any(w in p for w in [
            "preco", "preço", "valor", "quanto", "custa", "custo",
            "frete", "desconto", "oferta", "promocao", "promoção"
        ])
        volatilidade = "alta" if tem_preco else "baixa"
        return "merchant_specific", volatilidade, 1

    _tem_preco_gen = any(w in p for w in [
        "preco", "preço", "custa", "custo", "vale", "valor", "frete", "desconto"
    ])
    _tem_loja_gen = bool(re.search(r"\b(na|no|em)\s+[a-zA-Z]\w{2,}", p))
    if _tem_preco_gen and _tem_loja_gen:
        return "merchant_specific", "alta", 1

    # 8. Encyclopedic — só com trigger explícito
    if any(w in p for w in _PALAVRAS_ENCYCLOPEDIC):
        return "encyclopedic", "baixa", 1

    # 9. Fallback inteligente:
    palavras = p.strip().split()
    _SUBSTANTIVOS_TECNICOS = {
        "sistema", "codigo", "arquivo", "função", "api", "servidor",
        "banco", "dados", "erro", "bug", "deploy", "config", "modelo",
        "agente", "pipeline", "fase", "livro", "memoria", "token",
        "chave", "classe", "metodo", "variavel", "loop", "script",
    }
    _PRONOMES_PESSOAIS = {"eu", "me", "meu", "minha", "seu", "sua", "nos", "nosso", "voce", "você"}
    _VERBOS_CONVERSA = {
        "acertei", "errei", "ganha", "ganhou", "perdi", "perdeu", "diz", "diga",
        "fala", "fale", "brincadeira", "graca", "graça", "numero", "número",
        "tentei", "tentou", "saio", "saindo", "voltar", "volto", "lembrar",
        "lembro", "teste", "testando", "jogo", "jogando", "adivinha",
    }
    pergunta_explicita = pergunta.strip().endswith("?")
    tem_substantivo_tecnico = any(w in _SUBSTANTIVOS_TECNICOS for w in palavras)
    tem_pronome_pessoal = any(w in _PRONOMES_PESSOAIS for w in palavras)
    tem_verbo_conversa = any(w in _VERBOS_CONVERSA for w in palavras)

    # Frase curta sem substantivo técnico → conversacional
    if not pergunta_explicita and len(palavras) <= 5 and not tem_substantivo_tecnico:
        return "conversacional", "baixa", 0

    # Frase longa mas claramente conversacional → conversacional
    if not pergunta_explicita and not tem_substantivo_tecnico and (tem_pronome_pessoal or tem_verbo_conversa):
        return "conversacional", "baixa", 0

    return "encyclopedic", "baixa", 1


def _detectar_volatilidade(pergunta: str) -> str:
    _, volatilidade, _ = _detectar_escopo(pergunta)
    return volatilidade


def _detectar_incerteza(pergunta: str, resposta: str, usou_tavily: bool = False) -> bool:
    if usou_tavily:
        return False
    p = pergunta.lower()
    r = resposta.lower()
    pergunta_factual = any(padrao in p for padrao in _PADROES_INCERTEZA)
    resposta_incerta = any(padrao in r for padrao in _PADROES_RESPOSTA_INCERTA)
    return pergunta_factual or resposta_incerta


def detectar_correcao(pergunta: str) -> bool:
    p = pergunta.lower()
    return any(padrao in p for padrao in _PADROES_CORRECAO)


def detectar_ensino(pergunta: str) -> bool:
    p = pergunta.lower()
    return any(padrao in p for padrao in _PADROES_ENSINO)


def classificar(pergunta: str, resposta: str = "", get_groq_fn=None, usou_tavily: bool = False) -> dict:
    chave = f"{pergunta[:100]}|{resposta[:50]}"
    _limpar_cache()

    if chave in _cache:
        debug("CLASSIFIER", f"Cache hit: {_cache[chave]}")
        return _cache[chave]

    escopo, volatilidade, n_fontes = _detectar_escopo(pergunta)

    resultado_padrao = {
        "tom": "TECNICO", "relevancia": "BAIXA", "tipo": "DESCARTAVEL",
        "incerteza": False, "volatilidade": volatilidade,
        "escopo": escopo, "n_fontes": n_fontes,
    }

    if not get_groq_fn:
        return resultado_padrao

    p = pergunta.lower()

    palavras_futeis = ["kkk", "haha", "rs", "tudo bem", "obrigado", "tchau", "piada"]
    if any(w in p for w in palavras_futeis):
        resultado = {
            "tom": "CASUAL", "relevancia": "BAIXA", "tipo": "DESCARTAVEL",
            "incerteza": False, "volatilidade": "baixa",
            "escopo": escopo, "n_fontes": n_fontes,
        }
        _cache[chave] = resultado
        return resultado

    if escopo == "mentoria_raciocinio":
        resultado = {
            "tom": "REFLEXIVO", "relevancia": "MEDIA", "tipo": "SEMANTICA",
            "incerteza": False, "volatilidade": "baixa",
            "escopo": "mentoria_raciocinio", "n_fontes": 0,
        }
        info("CLASSIFIER", "ESCOPO:mentoria_raciocinio | livro_mentores | TOM:REFLEXIVO")
        _cache[chave] = resultado
        return resultado

    if escopo == "conversacional":
        resultado = {
            "tom": "CASUAL", "relevancia": "BAIXA", "tipo": "DESCARTAVEL",
            "incerteza": False, "volatilidade": "baixa",
            "escopo": "conversacional", "n_fontes": 0,
        }
        info("CLASSIFIER", "ESCOPO:conversacional | 0 busca externa | TOM:CASUAL")
        _cache[chave] = resultado
        return resultado

    if escopo == "identidade_interna":
        resultado = {
            "tom": "CASUAL", "relevancia": "BAIXA", "tipo": "DESCARTAVEL",
            "incerteza": False, "volatilidade": "baixa",
            "escopo": "identidade_interna", "n_fontes": 0,
        }
        info("CLASSIFIER", "ESCOPO:identidade_interna | 0 busca externa | TOM:CASUAL")
        _cache[chave] = resultado
        return resultado

    if escopo == "internal":
        resultado = {
            "tom": "TECNICO", "relevancia": "BAIXA", "tipo": "DESCARTAVEL",
            "incerteza": False, "volatilidade": "baixa",
            "escopo": "internal", "n_fontes": 0,
        }
        info("CLASSIFIER", "ESCOPO:internal | 0 busca externa | TOM:TECNICO")
        _cache[chave] = resultado
        return resultado

    if escopo == "subjective_decision":
        resultado = {
            "tom": "REFLEXIVO", "relevancia": "BAIXA", "tipo": "DESCARTAVEL",
            "incerteza": False, "volatilidade": "baixa",
            "escopo": "subjective_decision", "n_fontes": 0,
        }
        info("CLASSIFIER", "ESCOPO:subjective_decision | 0 busca externa | TOM:REFLEXIVO")
        _cache[chave] = resultado
        return resultado

    if detectar_correcao(pergunta):
        resultado = {
            "tom": "TECNICO", "relevancia": "ALTA", "tipo": "LICAO",
            "incerteza": False, "volatilidade": "baixa",
            "escopo": escopo, "n_fontes": n_fontes,
            "confianca_override": 0.95, "origem_override": "correcao_usuario",
        }
        info("CLASSIFIER", "TOM:TECNICO | RELEVÂNCIA:ALTA | TIPO:LICAO | ORIGEM:correcao_usuario")
        return resultado

    if detectar_ensino(pergunta):
        resultado = {
            "tom": "TECNICO", "relevancia": "ALTA", "tipo": "LICAO",
            "incerteza": False, "volatilidade": "baixa",
            "escopo": escopo, "n_fontes": n_fontes,
            "confianca_override": 0.92, "origem_override": "ensino_usuario",
        }
        info("CLASSIFIER", "TOM:TECNICO | RELEVÂNCIA:ALTA | TIPO:LICAO | ORIGEM:ensino_usuario")
        return resultado

    palavras_urgentes = ["caiu", "parou", "erro crítico", "não funciona", "quebrou", "urgente"]
    if any(w in p for w in palavras_urgentes):
        resultado = {
            "tom": "URGENTE", "relevancia": "ALTA", "tipo": "EPISODICA",
            "incerteza": _detectar_incerteza(pergunta, resposta, usou_tavily),
            "volatilidade": volatilidade, "escopo": escopo, "n_fontes": n_fontes,
        }
        _cache[chave] = resultado
        return resultado

    palavras_projeto = ["salvar projeto", "quero projetar", "vou criar", "ideia para", "planejar"]
    if any(w in p for w in palavras_projeto):
        resultado = {
            "tom": "PROJETO", "relevancia": "ALTA", "tipo": "PROJETO",
            "incerteza": False, "volatilidade": "baixa",
            "escopo": escopo, "n_fontes": n_fontes,
        }
        _cache[chave] = resultado
        return resultado

    palavras_alta = ["hackathon", "pitch", "mvp", "solução", "arquitetura", "deploy", "bug", "configuração"]
    if any(w in p for w in palavras_alta):
        resultado = {
            "tom": "TECNICO", "relevancia": "ALTA", "tipo": "SEMANTICA",
            "incerteza": _detectar_incerteza(pergunta, resposta, usou_tavily),
            "volatilidade": volatilidade, "escopo": escopo, "n_fontes": n_fontes,
        }
        _cache[chave] = resultado
        return resultado

    contexto_resposta = f"\nResposta: {resposta[:400]}" if resposta.strip() else ""
    prompt = f"""Analise esta conversa e responda EXATAMENTE neste formato JSON, sem explicações:

Pergunta: {pergunta[:400]}{contexto_resposta}

Responda APENAS com JSON assim:
{{"tom": "X", "relevancia": "Y", "tipo": "Z"}}

Valores possíveis:
- tom: CASUAL | HUMOR | TECNICO | URGENTE | PROJETO | REFLEXIVO
- relevancia: ALTA | MEDIA | BAIXA
- tipo: SEMANTICA | EPISODICA | PROJETO | DESCARTAVEL

Regras:
- ALTA somente se for bug resolvido, decisão de arquitetura, configuração específica, hackathon, solução técnica
- BAIXA para tudo genérico, casual, piada
- DESCARTAVEL quando relevancia for BAIXA"""

    try:
        import json, re
        cliente = get_groq_fn()
        r = cliente.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50, temperature=0
        )
        texto = r.choices[0].message.content.strip()
        match = re.search(r'\{[^}]+\}', texto)
        if match:
            dados = json.loads(match.group())
            tom        = dados.get("tom", "TECNICO").upper()
            relevancia = dados.get("relevancia", "BAIXA").upper()
            tipo       = dados.get("tipo", "DESCARTAVEL").upper()
            if tom not in TONS:               tom = "TECNICO"
            if relevancia not in RELEVÂNCIAS: relevancia = "BAIXA"
            if tipo not in TIPOS:             tipo = "DESCARTAVEL"
            incerteza = _detectar_incerteza(pergunta, resposta, usou_tavily)
            resultado = {
                "tom": tom, "relevancia": relevancia, "tipo": tipo,
                "incerteza": incerteza, "volatilidade": volatilidade,
                "escopo": escopo, "n_fontes": n_fontes,
            }
            nivel_log = f"TOM:{tom} | RELEVÂNCIA:{relevancia} | TIPO:{tipo} | VOLATILIDADE:{volatilidade} | ESCOPO:{escopo} | FONTES:{n_fontes}"
            if incerteza:
                nivel_log += " | INCERTEZA:SIM"
            info("CLASSIFIER", nivel_log)
            _cache[chave] = resultado
            return resultado
    except Exception as e:
        debug("CLASSIFIER", f"GROQ falhou: {e}")

    _cache[chave] = resultado_padrao
    return resultado_padrao


def instrucao_tom(tom: str, incerteza: bool = False) -> str:
    instrucoes = {
        "CASUAL":    "\nINSTRUÇÃO DE TOM: Responda de forma leve e informal. Sem bullet points. Resposta curta.",
        "HUMOR":     "\nINSTRUÇÃO DE TOM: O usuário quer descontrair. Pode ser criativo, leve, até fazer uma piada se fizer sentido.",
        "TECNICO":   "\nINSTRUÇÃO DE TOM: Resposta técnica e precisa. Direto ao ponto. Use código se necessário.",
        "URGENTE":   "\nINSTRUÇÃO DE TOM: URGENTE. Coloque a solução JÁ NA PRIMEIRA LINHA. Zero introdução.",
        "PROJETO":   "\nINSTRUÇÃO DE TOM: Eduardo está planejando. Pense junto, explore possibilidades, seja colaborativo.",
        "REFLEXIVO": "\nINSTRUÇÃO DE TOM: Explore a ideia em profundidade. Resposta mais longa, sem pressa de concluir.",
    }
    base = instrucoes.get(tom, "")
    if incerteza:
        base += (
            "\nAVISO DE INCERTEZA: Esta resposta pode conter dados factuais sem verificação em tempo real. "
            "Se houver datas, valores ou fatos históricos específicos, indique claramente que são baseados "
            "no seu conhecimento de treinamento e podem não ser precisos. Sugira verificar em fonte confiável."
        )
    return base