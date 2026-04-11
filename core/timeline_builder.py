"""
core/timeline_builder.py
Fase 21 — Cartografia da Evolução Mental.

Constrói linha do tempo da evolução cognitiva do usuário combinando:
  - crenças (belief_tracker)
  - princípios (principle_registry)
  - revisões/metamorfoses (belief_revision_engine)
  - estabilidade (stability_index)

Retorna timeline consultável por domínio, período ou tipo de evento.
"""

import json
import os
from datetime import datetime
from core.logger import info, warn

TIMELINE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_precos.json"
)

# Tipos de evento na timeline
TIPO_CRENCA    = "crenca"
TIPO_PRINCIPIO = "principio"
TIPO_REVISAO   = "revisao"
TIPO_REFORCO   = "reforco"


def _ts(iso: str) -> datetime:
    try:
        return datetime.fromisoformat(iso)
    except Exception:
        return datetime.min


def construir_timeline(
    crencas:    dict,
    principios: dict,
    revisoes:   list,
) -> list[dict]:
    """
    Constrói timeline ordenada cronologicamente.
    Cada evento tem: tipo, timestamp, texto, dominio, custo, stability.
    """
    from core.stability_index import calcular_stability

    eventos = []

    # Crenças — cada reforço é um evento
    for c in crencas.values():
        ts = c.get("criado_em", c.get("ultima_vez", ""))
        if not ts:
            continue
        stability = calcular_stability(c)
        eventos.append({
            "tipo":      TIPO_CRENCA,
            "timestamp": ts,
            "texto":     c.get("texto", "")[:150],
            "dominio":   c.get("dominio", "outro"),
            "contagem":  c.get("contagem", 1),
            "confianca": c.get("confianca", 0.5),
            "stability": stability,
            "ativa":     c.get("ativa", True),
            "id":        c.get("id", ""),
        })

    # Princípios
    for p in principios.values():
        ts = p.get("criado_em", p.get("ultima_vez", ""))
        if not ts:
            continue
        stability = calcular_stability(p)
        eventos.append({
            "tipo":      TIPO_PRINCIPIO,
            "timestamp": ts,
            "texto":     p.get("texto", "")[:150],
            "dominio":   p.get("dominio", "outro"),
            "categoria": p.get("categoria", "outro"),
            "contagem":  p.get("contagem", 1),
            "confianca": p.get("confianca", 0.8),
            "stability": stability,
            "ativa":     p.get("ativo", True),
            "id":        p.get("id", ""),
        })

    # Revisões
    for r in revisoes:
        eventos.append({
            "tipo":      TIPO_REVISAO,
            "timestamp": r.get("timestamp", ""),
            "texto":     r.get("texto_novo", "")[:150],
            "anterior":  r.get("texto_anterior", "")[:100],
            "gatilho":   r.get("gatilho", ""),
            "custo":     r.get("custo", "baixo"),
            "confianca": r.get("confianca", 0.7),
            "stability": 0.0,  # revisão = instabilidade momentânea
            "dominio":   "outro",
            "id":        r.get("id", ""),
        })

    # Ordena cronologicamente
    eventos.sort(key=lambda e: _ts(e.get("timestamp", "")))
    return eventos


def filtrar_timeline(
    eventos:   list[dict],
    dominio:   str = "",
    tipo:      str = "",
    so_ativos: bool = False,
    custo_min: str = "",
) -> list[dict]:
    """Filtra a timeline por critérios."""
    _ORDEM_CUSTO = {"baixo": 0, "medio": 1, "alto": 2}
    custo_min_n  = _ORDEM_CUSTO.get(custo_min, 0)

    resultado = []
    for e in eventos:
        if dominio and e.get("dominio") != dominio:
            continue
        if tipo and e.get("tipo") != tipo:
            continue
        if so_ativos and not e.get("ativa", True):
            continue
        if custo_min and _ORDEM_CUSTO.get(e.get("custo", "baixo"), 0) < custo_min_n:
            continue
        resultado.append(e)

    return resultado


def resumir_evolucao(eventos: list[dict]) -> dict:
    """
    Gera resumo da evolução cognitiva.
    Responde: quantas crenças, princípios, revisões; domínios mais ativos.
    """
    n_crencas    = sum(1 for e in eventos if e["tipo"] == TIPO_CRENCA)
    n_principios = sum(1 for e in eventos if e["tipo"] == TIPO_PRINCIPIO)
    n_revisoes   = sum(1 for e in eventos if e["tipo"] == TIPO_REVISAO)

    # Domínios mais frequentes
    dominios: dict = {}
    for e in eventos:
        d = e.get("dominio", "outro")
        dominios[d] = dominios.get(d, 0) + 1
    dominio_principal = max(dominios, key=dominios.get) if dominios else "outro"

    # Estabilidade média
    stabs = [e.get("stability", 0.5) for e in eventos if e.get("stability") is not None]
    stability_media = round(sum(stabs) / len(stabs), 3) if stabs else 0.0

    # Revisões com custo alto
    revisoes_caras = sum(
        1 for e in eventos
        if e["tipo"] == TIPO_REVISAO and e.get("custo") == "alto"
    )

    return {
        "total_eventos":    len(eventos),
        "crenças":          n_crencas,
        "princípios":       n_principios,
        "revisões":         n_revisoes,
        "revisões_caras":   revisoes_caras,
        "dominio_principal": dominio_principal,
        "stability_media":  stability_media,
        "dominios":         dominios,
    }


def gerar_relatorio_evolucao(
    crencas:    dict,
    principios: dict,
    revisoes:   list,
) -> dict:
    """
    Ponto de entrada principal — gera relatório completo da evolução.
    """
    timeline = construir_timeline(crencas, principios, revisoes)
    resumo   = resumir_evolucao(timeline)

    info("TIMELINE", (
        f"Evolução: {resumo['crenças']} crenças | "
        f"{resumo['princípios']} princípios | "
        f"{resumo['revisões']} revisões | "
        f"stability={resumo['stability_media']}"
    ))

    return {
        "resumo":   resumo,
        "timeline": timeline,
    }