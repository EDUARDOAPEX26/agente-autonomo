"""
core/stability_index.py
Fase 21 — Cartografia da Evolução Mental.

Calcula índice de estabilidade de uma crença ou princípio ao longo do tempo.
Zero API — cálculo local baseado em contagem, tempo e revisões.

stability_index: 0.0 (frágil/impulsivo) → 1.0 (estável/duradouro)
belief_half_life: tempo médio que a crença resiste antes de revisão
"""

import json
import os
from datetime import datetime, timedelta
from core.logger import info, debug


def calcular_stability(entrada: dict) -> float:
    """
    Calcula stability_index para uma crença ou princípio.

    Fatores:
      - contagem: mais repetições = mais estável
      - tempo desde criação: crença antiga sobrevivente = estável
      - ativa: crença revisada perde estabilidade
      - confianca: proxy de consistência
    """
    contagem   = entrada.get("contagem", 1)
    confianca  = entrada.get("confianca", 0.5)
    ativa      = entrada.get("ativa", entrada.get("ativo", True))
    criado_em  = entrada.get("criado_em", entrada.get("ultima_vez", ""))
    ultima_vez = entrada.get("ultima_vez", "")

    # Fator 1: contagem (logarítmica — diminishing returns)
    import math
    fator_contagem = min(1.0, math.log(contagem + 1) / math.log(10))

    # Fator 2: longevidade — crença que sobrevive mais tempo é mais estável
    fator_tempo = 0.5  # default
    if criado_em:
        try:
            criado = datetime.fromisoformat(criado_em)
            dias = (datetime.now() - criado).days
            fator_tempo = min(1.0, dias / 30)  # 30 dias = máximo
        except Exception:
            pass

    # Fator 3: penalidade por revisão
    penalidade_revisao = 0.0 if ativa else 0.4

    # Fator 4: confiança já calculada pelo tracker
    fator_confianca = confianca

    stability = (
        fator_contagem   * 0.30 +
        fator_tempo      * 0.25 +
        fator_confianca  * 0.45
    ) - penalidade_revisao

    return round(max(0.0, min(1.0, stability)), 3)


def calcular_half_life(entradas: list[dict]) -> float:
    """
    Calcula belief_half_life: tempo médio em dias que uma crença dura.
    Considera apenas crenças revisadas (ativa=False) que têm criado_em.
    Retorna -1 se não há dados suficientes.
    """
    duracoes = []
    for e in entradas:
        ativa = e.get("ativa", e.get("ativo", True))
        if ativa:
            continue  # só revisadas
        criado_em  = e.get("criado_em", "")
        ultima_vez = e.get("ultima_vez", "")
        if not criado_em or not ultima_vez:
            continue
        try:
            criado  = datetime.fromisoformat(criado_em)
            revisao = datetime.fromisoformat(ultima_vez)
            dias    = (revisao - criado).days
            if dias >= 0:
                duracoes.append(dias)
        except Exception:
            pass

    if len(duracoes) < 2:
        return -1.0

    return round(sum(duracoes) / len(duracoes), 1)


def analisar_portfolio(crencas: dict, principios: dict) -> dict:
    """
    Analisa o portfolio completo de crenças e princípios.
    Retorna resumo com distribuição de estabilidade.
    """
    todas = list(crencas.values()) + list(principios.values())

    if not todas:
        return {"total": 0, "estaveis": 0, "frageis": 0, "half_life_dias": -1}

    estaveis = 0
    frageis  = 0
    scores   = []

    for e in todas:
        s = calcular_stability(e)
        scores.append(s)
        if s >= 0.7:
            estaveis += 1
        elif s < 0.4:
            frageis += 1

    half_life = calcular_half_life(todas)
    score_medio = round(sum(scores) / len(scores), 3) if scores else 0.0

    return {
        "total":          len(todas),
        "estaveis":       estaveis,
        "frageis":        frageis,
        "score_medio":    score_medio,
        "half_life_dias": half_life,
    }