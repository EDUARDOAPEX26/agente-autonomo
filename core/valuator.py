"""
core/valuator.py
Fase 16-C — Valuator age de verdade. Tem a ultima palavra.
Atualizado Fase 32: redução de falsos positivos em vazamento + reincidência mais tolerante
Atualizado Fase 41-A: information_validator integrado
"""

import re
from core.logger import warn, info

NOMES_INTERNOS = [
    "tavily", "exa", "router", "groq", "sambanova", "huggingface",
    "livro_raciocinio", "livro_resumo", "livro_mentores",
    "book_raciocinio", "tool_decider", "system_state",
    "valuator", "evaluator", "classifier", "railway_client",
    "prompt_base", "identidade_agente",
]

_ESCOPOS_TECNICOS = {"internal", "identidade_interna"}

_PALAVRAS_CONSULTA_INTERNA = [
    "sua memória", "suas memórias", "memorias passadas", "memórias passadas",
    "memorias anteriores", "memórias anteriores",
    "suas apis", "suas api", "quais apis", "que apis", "quais sua",
    "suas ferramentas", "como você funciona", "como voce funciona",
    "seus livros", "livros temáticos", "livros tematicos",
    "suas capacidades", "o que você usa", "o que voce usa",
    "seu sistema", "sua arquitetura", "como é feito", "como e feito",
    "quais suas", "me fala das", "me conte sobre",
]

PADROES_CONTRADICAO = [
    (r"\bsim\b", r"\bnao\b"),
    (r"\bpossivel\b", r"\bimpossivel\b"),
    (r"\bsempre\b", r"\bnunca\b"),
    (r"\bcorreto\b", r"\berrado\b"),
]

PESOS_DOMINIO = {
    "reuters.com": 1.0,
    "bbc.com": 1.0,
    "gov.br": 1.0,
    "wikipedia.org": 0.8,
    "g1.globo.com": 0.8,
    "coinmarketcap.com": 0.9,
    "investing.com": 0.9,
}
PESO_DOMINIO_PADRAO = 0.6

FRASES_INCERTEZA = [
    "Nao ha confirmacao consistente entre as fontes consultadas.",
    "Ha divergencia entre as fontes — nao e possivel confirmar esse dado agora.",
    "Dados insuficientes no momento para confirmar esse valor com seguranca.",
]

_ESCOPOS_SEM_REINCIDENCIA = {
    "subjective_decision", "conversacional", "identidade_interna", "internal"
}

_PERGUNTAS_PROFUNDA = {
    "sentido da vida", "propósito da vida", "por que existimos", "qual o sentido",
    "felicidade", "o que é ser humano", "existência"
}


def _score_dominio(fontes: list) -> float:
    if not fontes:
        return 0.0
    total = 0.0
    for url in fontes:
        peso = PESO_DOMINIO_PADRAO
        for dominio, p in PESOS_DOMINIO.items():
            if dominio in url:
                peso = p
                break
        total += peso
    return round((total / len(fontes)) * 0.1, 3)


def _e_consulta_interna(pergunta: str, escopo: str) -> bool:
    if escopo in _ESCOPOS_TECNICOS:
        return True
    p = pergunta.lower()
    return any(k in p for k in _PALAVRAS_CONSULTA_INTERNA)


def _detectar_vazamento(resposta: str, pergunta: str = "", escopo: str = "") -> bool:
    if _e_consulta_interna(pergunta, escopo):
        return False
    r = resposta.lower()
    nomes_criticos = ["exa_client", "tavily_client", "tool_decider", "railway_client"]
    for nome in nomes_criticos:
        if nome in r:
            warn("VALUATOR", f"Vazamento crítico detectado: '{nome}'")
            return True
    for nome in NOMES_INTERNOS:
        if nome in r and len(resposta.strip()) < 120:
            warn("VALUATOR", f"Vazamento leve detectado: '{nome}'")
            return True
    return False


def _detectar_contradicao(resposta: str) -> bool:
    r = resposta.lower()
    for p1, p2 in PADROES_CONTRADICAO:
        if re.search(p1, r) and re.search(p2, r):
            warn("VALUATOR", f"Contradicao detectada: '{p1}' + '{p2}'")
            return True
    return False


def _penalidade_reincidencia(pergunta: str, escopo: str = "") -> float:
    if escopo in _ESCOPOS_SEM_REINCIDENCIA:
        return 0.0
    p_lower = pergunta.lower()
    if any(term in p_lower for term in _PERGUNTAS_PROFUNDA):
        return 0.0
    try:
        from core.book_raciocinio import buscar
        entrada = buscar(pergunta)
        if entrada and entrada.get("erro_tipo") not in ("ok", "", None) and entrada.get("score", 1.0) < 0.6:
            warn("VALUATOR", f"Reincidencia detectada: erro_tipo={entrada['erro_tipo']}")
            return -0.15
    except Exception:
        pass
    return 0.0


def _decidir_acao(score: float, erro_tipo: str) -> str:
    if erro_tipo in ("vazamento", "vazio"):
        return "descartar"
    if erro_tipo in ("consenso_fraco", "reincidencia"):
        return "responder_com_incerteza"
    if erro_tipo.startswith("sem_fonte_"):
        return "responder_com_incerteza"
    if score < 0.7:
        return "aceitar_com_cautela"
    return "aceitar"


def avaliar(pergunta: str, resposta: str, contexto: dict = None) -> dict:
    contexto = contexto or {}
    erro_tipo = "ok"
    escopo = contexto.get("escopo", "")

    if not resposta or not resposta.strip():
        return {"score": 0.0, "erro_tipo": "vazio", "acao": "descartar", "detalhe": "Resposta vazia"}

    if _detectar_vazamento(resposta, pergunta, escopo):
        return {"score": 0.0, "erro_tipo": "vazamento", "acao": "descartar", "detalhe": "Nome interno na resposta"}

    score = 1.0
    if len(resposta.strip()) < 10:
        score -= 0.3

    if _detectar_contradicao(resposta):
        score -= 0.2
        erro_tipo = "contradicao"

    consenso = contexto.get("consenso")
    if consenso is not None and consenso < 2:
        score -= 0.2
        erro_tipo = "consenso_fraco"
        warn("VALUATOR", f"Consenso fraco: {consenso} fonte(s)")

    fontes = contexto.get("fontes", [])
    score += _score_dominio(fontes)

    penalidade_r = _penalidade_reincidencia(pergunta, escopo)
    if penalidade_r < 0:
        score += penalidade_r
        erro_tipo = "reincidencia"

    score = round(max(0.0, min(1.0, score)), 3)

    if consenso == 1:
        score = round(max(0.0, score - 0.3), 3)
        erro_tipo = "consenso_fraco"
    elif consenso == 0:
        score = round(max(0.0, score - 0.4), 3)
        erro_tipo = "consenso_fraco"

    # Fase 41-A — Validador Universal de Informação
    try:
        from core.information_validator import validar as validar_info
        dados_online = contexto.get("dados_online", "")
        resultado_info = validar_info(pergunta, resposta, dados_online, escopo, score)
        score = resultado_info["score_final"]
        if resultado_info["flag"] and erro_tipo == "ok":
            erro_tipo = resultado_info["flag"]
    except Exception:
        pass
    # fim Fase 41-A

    acao = _decidir_acao(score, erro_tipo)

    detalhe = (
        f"score={score} | erro_tipo={erro_tipo} | "
        f"acao={acao} | consenso={consenso} | fontes={len(fontes)}"
    )
    info("VALUATOR", detalhe)

    return {
        "score": score,
        "erro_tipo": erro_tipo,
        "acao": acao,
        "detalhe": detalhe,
    }


def frase_incerteza(indice: int = 0) -> str:
    return FRASES_INCERTEZA[indice % len(FRASES_INCERTEZA)]