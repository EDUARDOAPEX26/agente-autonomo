"""
core/belief_revision_engine.py
Fase 21 — Cartografia da Evolução Mental.

Detecta eventos de revisão: momentos em que o usuário muda de posição
em relação a uma crença ou princípio anterior.

Um revision_event contém:
{
    "id":            str,
    "crenca_id":     str,          # id da crença revisada
    "texto_anterior": str,         # o que o usuário acreditava
    "texto_novo":    str,          # nova posição
    "gatilho":       str,          # o que causou a mudança
    "custo":         str,          # "baixo" | "medio" | "alto" — impacto percebido
    "confianca":     float,        # 0.0-1.0 quão certo é que foi uma revisão
    "timestamp":     str,
}
"""

import json
import os
import hashlib
import threading
from datetime import datetime
from core.logger import info, debug, warn

METAMORFOSES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_metamorfoses.json"
)

_cache = {"dados": None}
_lock  = threading.Lock()

# Padrões que indicam mudança de posição
_PADROES_REVISAO = [
    "mudei de ideia", "mudei de opinião", "pensei melhor",
    "antes achava", "antes pensava", "antes acreditava",
    "agora acho", "agora penso", "agora acredito",
    "errei quando", "foi um erro acreditar",
    "aprendi que estava errado", "percebi que estava errado",
    "não acredito mais", "deixei de acreditar",
    "revi minha posição", "reconsiderei",
    "hoje penso diferente", "mudou minha visão",
]

# Indicadores de custo da revisão
_CUSTO_ALTO = [
    "perdi", "custou caro", "caro demais", "muito difícil",
    "foi doloroso", "prejudicou", "fracassei", "falhou",
    "arrependo", "me arrependo",
]
_CUSTO_MEDIO = [
    "demorei", "levei tempo", "não foi fácil", "custou",
    "precisei de ajuda", "foi trabalhoso",
]


def _normalizar(texto: str) -> str:
    return " ".join(texto.lower().strip().split())


def _gerar_id(texto: str, ts: str) -> str:
    return hashlib.md5(f"{texto}{ts}".encode()).hexdigest()[:8]


def _detectar_custo(texto: str) -> str:
    t = texto.lower()
    if any(p in t for p in _CUSTO_ALTO):
        return "alto"
    if any(p in t for p in _CUSTO_MEDIO):
        return "medio"
    return "baixo"


def _carregar() -> list:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(METAMORFOSES_PATH):
        _cache["dados"] = []
        return []
    try:
        with open(METAMORFOSES_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
            _cache["dados"] = dados if isinstance(dados, list) else []
            return _cache["dados"]
    except Exception as e:
        warn("METAMORFOSE", f"Erro ao carregar: {e}")
        _cache["dados"] = []
        return []


def _salvar(dados: list):
    try:
        with open(METAMORFOSES_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("METAMORFOSE", f"Erro ao salvar: {e}")


def detectar_revisao(texto: str) -> bool:
    """Retorna True se o texto indica mudança de posição."""
    if len(texto) < 15:
        return False
    t = texto.lower()
    return any(p in t for p in _PADROES_REVISAO)


def registrar_revisao(
    texto_novo:    str,
    texto_anterior: str = "",
    crenca_id:     str = "",
    gatilho:       str = "",
):
    """
    Registra um evento de revisão no livro_metamorfoses.json.
    Chamado pelo pipeline quando detectar_revisao() retornar True.
    """
    ts    = datetime.now().isoformat()
    rid   = _gerar_id(texto_novo, ts)
    custo = _detectar_custo(texto_novo)

    evento = {
        "id":             rid,
        "crenca_id":      crenca_id,
        "texto_anterior": texto_anterior[:300],
        "texto_novo":     texto_novo[:300],
        "gatilho":        gatilho[:200] if gatilho else "",
        "custo":          custo,
        "confianca":      0.7,
        "timestamp":      ts,
    }

    with _lock:
        dados = _carregar()
        dados.append(evento)
        if len(dados) > 200:
            dados = dados[-200:]
        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()

    info("METAMORFOSE", f"Revisão registrada: custo={custo} | '{texto_novo[:50]}'")
    return evento


def listar_revisoes(dominio: str = "", custo_min: str = "") -> list:
    """Retorna revisões filtradas por domínio ou custo mínimo."""
    dados = _carregar()
    _ORDEM_CUSTO = {"baixo": 0, "medio": 1, "alto": 2}
    custo_min_n  = _ORDEM_CUSTO.get(custo_min, 0)

    resultado = []
    for e in dados:
        if custo_min and _ORDEM_CUSTO.get(e.get("custo", "baixo"), 0) < custo_min_n:
            continue
        resultado.append(e)

    return resultado


def processar(pergunta: str, resposta: str = ""):
    """
    Chamado pelo pipeline. Detecta e registra revisões automaticamente.
    Zero API.
    """
    if detectar_revisao(pergunta):
        registrar_revisao(
            texto_novo     = pergunta,
            texto_anterior = "",
            gatilho        = resposta[:100] if resposta else "",
        )