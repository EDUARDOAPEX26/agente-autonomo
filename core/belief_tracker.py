# core/belief_tracker.py
"""
Fase 20 — Motor de Coerência Cognitiva.
Camada 1: extração candidata de crenças/preferências (heurística local, zero API).
Camada 2: consolidação — só vira crença operacional com recorrência >= 2.
Camada 3: ativação — consultada pelo dissonance_trigger quando relevante.

v5 — fix principal: invalidadores verificados como expressões isoladas
     (f" {inv} " in t) em vez de substring simples (inv in t).
     Corrige falso positivo: "e se" bloqueava "importante sempre".
"""

import json
import os
import hashlib
import threading
from datetime import datetime
from core.logger import info, debug, warn

CRENCAS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_crencas.json"
)

_cache = {"dados": None}
_lock  = threading.Lock()

# ── DOMÍNIOS SEMÂNTICOS ───────────────────────────────────────────────────────
_DOMINIOS = {
    "risco": [
        "risco", "seguro", "segurança", "conservador", "cuidado", "cautela",
        "perda", "prejuízo", "devagar", "calma", "estável", "estabilidade",
    ],
    "crescimento": [
        "crescimento", "crescer", "expandir", "expansão", "oportunidade",
        "lucro", "ganho", "retorno", "investir", "escalar", "resultado",
    ],
    "velocidade": [
        "rápido", "rapidez", "velocidade", "urgente", "logo", "agora",
        "imediato", "ágil", "agilidade", "prazo", "deadline",
    ],
    "qualidade": [
        "qualidade", "cuidado", "detalhe", "perfeito", "excelência",
        "robusto", "confiável", "testado", "validado", "correto",
    ],
    "autonomia": [
        "autonomia", "autônomo", "independente", "livre", "sozinho",
        "controle", "decisão própria", "sem supervisão",
    ],
    "custo": [
        "custo", "barato", "caro", "economia", "economizar", "gratuito",
        "grátis", "pagar", "dinheiro", "orçamento", "budget",
    ],
}

# ── PADRÕES DE PREFERÊNCIA ────────────────────────────────────────────────────
_PADROES_PREFERENCIA = [
    # Preferências explícitas
    "prefiro", "prefere", "gosto de", "não gosto de", "odeio", "adoro",
    "sempre faço", "nunca faço", "costumo", "meu estilo",
    # Valores declarados — versões específicas de "para mim" (com e sem acento)
    "para mim é importante", "para mim e importante",
    "para mim o que vale", "para mim sempre",
    "para mim nunca", "para mim o certo", "para mim faz sentido",
    "acredito que", "acho que", "na minha visão",
    "o que importa", "o que mais importa", "o que é importante",
    # Princípios de trabalho
    "regra minha", "princípio", "filosofia",
    "minha abordagem", "meu jeito", "trabalho assim",
    # Aprendizados explícitos
    "aprendi que", "descobri que", "percebi que", "entendi que",
    "me arrependi", "foi um erro", "valeu a pena",
]

# Palavras que invalidam uma crença candidata
# IMPORTANTE: verificados como expressões isoladas — não como substrings
_INVALIDADORES = [
    # Dúvida e hipótese
    "talvez", "não sei", "sei lá", "depende", "por acaso",
    "imagina", "e se", "hipótese", "exemplo", "suponha",
    "ficção", "inventei", "brincando", "piada",
    "estou testando", "só testando", "era para testar",
    "na verdade voce", "voce disse", "voce pediu",
    "você disse", "você pediu", "você me pediu",
    # Comandos e injeções de prompt
    "comando de prioridade", "comando prioridade",
    "altere o escopo", "altere escopo",
    "utilize o tavily", "utilize o exa", "utilize tavily", "utilize exa",
    "fase 40", "fase 39", "fase 38", "fase 37",
    "deep dive", "escopo para external", "escopo para",
    "quero que tragas", "quero que você traga", "quero que voce traga",
    "instrução obrigatória", "instrucao obrigatoria",
    "prioridade fase", "comando fase",
    "altere", "force escopo", "mude escopo",
    # Referências a APIs internas
    "tavily", "exa_client", "groq", "sambanova",
    "pipeline", "classifier", "valuator",
]

# Indicadores de instrução técnica
_INDICADORES_TECNICO = [
    "altere", "utilize", "execute", "rode", "faça uma busca",
    "busque no", "traga um resumo", "resumo técnico",
    "não quero uma conversa", "quero apenas", "quero que você",
]


def _normalizar(texto: str) -> str:
    return " ".join(texto.lower().strip().split())


def _gerar_id(texto: str) -> str:
    return hashlib.md5(_normalizar(texto).encode()).hexdigest()[:8]


def _detectar_dominio(texto: str) -> str:
    t = texto.lower()
    for dominio, palavras in _DOMINIOS.items():
        if any(p in t for p in palavras):
            return dominio
    return "outro"


def _e_crenca_valida(texto: str) -> bool:
    """Retorna False se o texto parece hipótese, ficção, dúvida ou injeção técnica."""
    # v5: normaliza e adiciona espaços para verificar expressões isoladas
    t = " " + _normalizar(texto) + " "

    # Verifica invalidadores como expressões isoladas (não substrings)
    if any(f" {inv.strip()} " in t for inv in _INVALIDADORES):
        return False

    indicadores_presentes = sum(1 for ind in _INDICADORES_TECNICO if ind in t)
    if indicadores_presentes >= 2:
        debug("CRENCAS", f"Texto rejeitado — parece instrução técnica ({indicadores_presentes} indicadores)")
        return False

    if len(texto) > 200 and not any(p in t for p in ["prefiro", "gosto", "acredito", "aprendi", "meu jeito"]):
        debug("CRENCAS", f"Texto rejeitado — longo sem padrão claro de preferência")
        return False

    return True


# ── PERSISTÊNCIA ─────────────────────────────────────────────────────────────

def _carregar() -> dict:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(CRENCAS_PATH):
        _cache["dados"] = {}
        return {}
    try:
        with open(CRENCAS_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if isinstance(dados, dict):
            _cache["dados"] = dados
            return dados
        warn("CRENCAS", f"livro_crencas.json inválido (tipo={type(dados).__name__}) — resetando para {{}}")
        _cache["dados"] = {}
        threading.Thread(target=_salvar, args=({},), daemon=True).start()
        return {}
    except Exception as e:
        warn("CRENCAS", f"Erro ao carregar: {e}")
        _cache["dados"] = {}
        return {}


def _salvar(dados: dict):
    try:
        with open(CRENCAS_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("CRENCAS", f"Erro ao salvar: {e}")


# ── CAMADA 1 — EXTRAÇÃO CANDIDATA ────────────────────────────────────────────

def extrair_candidatos(pergunta: str, resposta: str = "") -> list:
    texto = pergunta.strip()
    if len(texto) < 10:
        return []
    t = texto.lower()
    tem_padrao = any(p in t for p in _PADROES_PREFERENCIA)
    if not tem_padrao:
        return []
    if not _e_crenca_valida(texto):
        return []
    dominio = _detectar_dominio(texto)
    debug("CRENCAS", f"Candidato detectado: '{texto[:60]}' | domínio={dominio}")
    return [{"texto": texto[:300], "dominio": dominio}]


# ── CAMADA 2 — CONSOLIDAÇÃO ───────────────────────────────────────────────────

def registrar_candidato(texto: str, dominio: str):
    with _lock:
        dados = _carregar()
        cid = _gerar_id(texto)
        if cid in dados:
            entrada = dados[cid]
            entrada["contagem"] += 1
            if texto not in entrada["evidencias"] and len(entrada["evidencias"]) < 5:
                entrada["evidencias"].append(texto[:200])
            entrada["confianca"] = min(0.95, entrada["confianca"] + 0.15)
            entrada["stability"] = min(1.0, entrada["stability"] + 0.05)
            entrada["ultima_vez"] = datetime.now().isoformat()
            info("CRENCAS", f"Crença reforçada: '{texto[:50]}' | confiança={entrada['confianca']:.2f} | contagem={entrada['contagem']}")
        else:
            dados[cid] = {
                "id":         cid,
                "texto":      texto[:300],
                "dominio":    dominio,
                "evidencias": [texto[:200]],
                "contagem":   1,
                "confianca":  0.5,
                "stability":  0.5,
                "ultima_vez": datetime.now().isoformat(),
                "ativa":      True,
            }
            debug("CRENCAS", f"Novo candidato: '{texto[:50]}' | domínio={dominio}")
        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()


# ── CAMADA 3 — ATIVAÇÃO ───────────────────────────────────────────────────────

def listar_ativas(min_confianca: float = 0.65) -> list:
    dados = _carregar()
    return [
        c for c in dados.values()
        if c.get("ativa", True) and c.get("confianca", 0) >= min_confianca
    ]


def buscar_por_dominio(dominio: str, min_confianca: float = 0.65) -> list:
    return [c for c in listar_ativas(min_confianca) if c.get("dominio") == dominio]


def revisar_crenca(cid: str, motivo: str = ""):
    with _lock:
        dados = _carregar()
        if cid in dados:
            dados[cid]["ativa"] = False
            dados[cid]["stability"] = max(0.0, dados[cid]["stability"] - 0.3)
            dados[cid]["ultima_vez"] = datetime.now().isoformat()
            if motivo:
                dados[cid]["evidencias"].append(f"[REVISÃO] {motivo[:100]}")
            info("CRENCAS", f"Crença revisada: {cid} | motivo={motivo[:50]}")
            _cache["dados"] = dados
            threading.Thread(target=_salvar, args=(dados,), daemon=True).start()


# ── PONTO DE ENTRADA PRINCIPAL ────────────────────────────────────────────────

def processar(pergunta: str, resposta: str = ""):
    candidatos = extrair_candidatos(pergunta, resposta)
    for c in candidatos:
        registrar_candidato(c["texto"], c["dominio"])