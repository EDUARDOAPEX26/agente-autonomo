"""
core/metamorphosis_tracker.py
Fase 21 — Cartografia da Evolução Mental.

Orquestrador da Fase 21: coordena belief_revision_engine, stability_index
e timeline_builder para responder perguntas sobre a evolução cognitiva.

Ponto de entrada único para o pipeline e para consultas diretas.
"""

import json
import os
from datetime import datetime
from core.logger import info, warn, debug

CRENCAS_PATH    = os.path.join(os.path.dirname(os.path.dirname(__file__)), "livro_crencas.json")
PRINCIPIOS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "livro_principios.json")
METAMORFOSES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "livro_metamorfoses.json")


def _carregar_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        warn("METAMORFOSE", f"Erro ao carregar {path}: {e}")
        return default


def processar(pergunta: str, resposta: str = ""):
    """
    Chamado pelo pipeline após cada interação.
    Coordena detecção de revisões e extração de crenças/princípios.
    Zero API.
    """
    try:
        from core.belief_revision_engine import processar as rev_processar
        rev_processar(pergunta, resposta)
    except Exception as e:
        debug("METAMORFOSE", f"Revisão falhou: {e}")

    try:
        from core.belief_tracker import processar as bt_processar
        bt_processar(pergunta, resposta)
    except Exception as e:
        debug("METAMORFOSE", f"Belief tracker falhou: {e}")

    try:
        from core.principle_registry import processar as pr_processar
        pr_processar(pergunta)
    except Exception as e:
        debug("METAMORFOSE", f"Principle registry falhou: {e}")


def consultar_evolucao(dominio: str = "", so_ativos: bool = False) -> dict:
    """
    Retorna relatório da evolução cognitiva do usuário.
    Pode ser filtrado por domínio.
    """
    crencas    = _carregar_json(CRENCAS_PATH, {})
    principios = _carregar_json(PRINCIPIOS_PATH, {})
    revisoes   = _carregar_json(METAMORFOSES_PATH, [])

    try:
        from core.timeline_builder import gerar_relatorio_evolucao, filtrar_timeline
        relatorio = gerar_relatorio_evolucao(crencas, principios, revisoes)

        if dominio:
            relatorio["timeline"] = filtrar_timeline(
                relatorio["timeline"], dominio=dominio, so_ativos=so_ativos
            )

        return relatorio
    except Exception as e:
        warn("METAMORFOSE", f"Erro ao gerar evolução: {e}")
        return {}


def consultar_portfolio() -> dict:
    """
    Retorna análise do portfolio completo de crenças e princípios.
    Inclui índices de estabilidade e half_life.
    """
    crencas    = _carregar_json(CRENCAS_PATH, {})
    principios = _carregar_json(PRINCIPIOS_PATH, {})

    try:
        from core.stability_index import analisar_portfolio
        return analisar_portfolio(crencas, principios)
    except Exception as e:
        warn("METAMORFOSE", f"Erro no portfolio: {e}")
        return {}


def grandes_revisoes(custo_min: str = "medio") -> list:
    """
    Retorna as revisões de maior custo — as viradas significativas.
    custo_min: "baixo" | "medio" | "alto"
    """
    try:
        from core.belief_revision_engine import listar_revisoes
        return listar_revisoes(custo_min=custo_min)
    except Exception as e:
        warn("METAMORFOSE", f"Erro ao listar revisões: {e}")
        return []


def crenças_frageis(threshold: float = 0.4) -> list:
    """
    Retorna crenças com stability_index abaixo do threshold.
    Útil para identificar padrões instáveis.
    """
    crencas = _carregar_json(CRENCAS_PATH, {})
    try:
        from core.stability_index import calcular_stability
        return [
            {**c, "stability": calcular_stability(c)}
            for c in crencas.values()
            if calcular_stability(c) < threshold and c.get("ativa", True)
        ]
    except Exception as e:
        warn("METAMORFOSE", f"Erro em crenças frágeis: {e}")
        return []


def crenças_estaveis(threshold: float = 0.7) -> list:
    """
    Retorna crenças com stability_index acima do threshold.
    Indica identidade consolidada do usuário.
    """
    crencas    = _carregar_json(CRENCAS_PATH, {})
    principios = _carregar_json(PRINCIPIOS_PATH, {})
    todas      = list(crencas.values()) + list(principios.values())

    try:
        from core.stability_index import calcular_stability
        return [
            {**e, "stability": calcular_stability(e)}
            for e in todas
            if calcular_stability(e) >= threshold
        ]
    except Exception as e:
        warn("METAMORFOSE", f"Erro em crenças estáveis: {e}")
        return []