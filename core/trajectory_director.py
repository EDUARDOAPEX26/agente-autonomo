"""
core/trajectory_director.py
Fase 40 — Diretor de Trajetória.

Sintetiza os dados das Fases 37, 38 e 39 para definir a direção
de evolução do sistema. Não age isolado — lê o estado real de:
- counterfutures.py (contra-futuros detectados)
- sacrificial_economy.py (candidatos a sacrifício)
- constitutional_engine.py (cláusulas ativas)

Gera um vetor de trajetória: para onde o sistema deve ir,
o que deve abandonar, e qual é a próxima tensão produtiva.
"""

import json
import os
import threading
from datetime import datetime
from core.logger import info, warn

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TRAJETORIA_PATH = os.path.join(_ROOT, "livro_trajetoria.json")
_lock = threading.Lock()

# Direções possíveis
_DIRECOES = {
    "consolidar":  "Sistema estável — aprofundar o que funciona, não adicionar",
    "expandir":    "Momento de crescimento — novas capacidades são bem-vindas",
    "podar":       "Excesso cognitivo — remover antes de avançar",
    "reparar":     "Módulos críticos com falha — corrigir antes de qualquer nova fase",
    "aguardar":    "Dados insuficientes para decidir — continuar coletando",
}


def _carregar() -> list:
    if not os.path.exists(_TRAJETORIA_PATH):
        return []
    try:
        with open(_TRAJETORIA_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
            return dados if isinstance(dados, list) else []
    except Exception:
        return []


def _salvar(entradas: list):
    try:
        with open(_TRAJETORIA_PATH, "w", encoding="utf-8") as f:
            json.dump(entradas[-100:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("TRAJETORIA", f"Erro ao salvar: {e}")


def _ler_contrafuturos() -> dict:
    try:
        from core.counterfutures import inicializar
        return inicializar()
    except Exception:
        return {"criticos": 0, "total_registros": 0}


def _ler_sacrificios() -> dict:
    try:
        from core.sacrificial_economy import inicializar
        return inicializar()
    except Exception:
        return {"candidatos": 0, "removidos": 0}


def _ler_constituicao() -> dict:
    try:
        from core.constitutional_engine import inicializar
        return inicializar()
    except Exception:
        return {"clausulas_ativas": 0, "total_artigos": 0}


def calcular_vetor() -> dict:
    """
    Calcula o vetor de trajetória atual baseado nas Fases 37, 38 e 39.
    Retorna direção, justificativa e próxima tensão produtiva.
    """
    cf   = _ler_contrafuturos()
    sac  = _ler_sacrificios()
    const = _ler_constituicao()

    criticos      = cf.get("criticos", 0)
    candidatos    = sac.get("candidatos", 0)
    removidos     = sac.get("removidos", 0)
    clausulas     = const.get("clausulas_ativas", 0)
    total_artigos = const.get("total_artigos", 0)

    # Lógica de direção
    if criticos >= 3:
        direcao = "reparar"
        justificativa = f"{criticos} contra-futuros críticos detectados — sistema em risco"
        proxima_tensao = "Resolver módulos com falha antes de qualquer expansão"

    elif candidatos >= 3 and removidos == 0:
        direcao = "podar"
        justificativa = f"{candidatos} módulos candidatos a sacrifício sem remoção ainda"
        proxima_tensao = "Decidir o que sacrificar para liberar energia cognitiva"

    elif clausulas >= 3 and criticos == 0:
        direcao = "expandir"
        justificativa = f"{clausulas} cláusulas ativas — base constitucional sólida"
        proxima_tensao = "Novas capacidades podem ser adicionadas com segurança"

    elif total_artigos >= 10 and clausulas <= 1:
        direcao = "consolidar"
        justificativa = f"{total_artigos} artigos mas apenas {clausulas} cláusula(s) ativa(s)"
        proxima_tensao = "Fortalecer o que existe antes de crescer"

    else:
        direcao = "aguardar"
        justificativa = "Dados insuficientes para decisão segura"
        proxima_tensao = "Continuar coletando experiências reais"

    vetor = {
        "timestamp":      datetime.now().isoformat(),
        "direcao":        direcao,
        "descricao":      _DIRECOES.get(direcao, ""),
        "justificativa":  justificativa,
        "proxima_tensao": proxima_tensao,
        "inputs": {
            "contrafuturos_criticos": criticos,
            "sacrificios_candidatos": candidatos,
            "sacrificios_removidos":  removidos,
            "clausulas_ativas":       clausulas,
            "artigos_constituicao":   total_artigos,
        }
    }

    # Salva no histórico
    with _lock:
        entradas = _carregar()
        entradas.append(vetor)
        threading.Thread(target=_salvar, args=(entradas,), daemon=True).start()

    info("TRAJETORIA", f"Fase 40 | direcao={direcao} | {justificativa[:60]}")
    return vetor


def inicializar() -> dict:
    """Roda o cálculo inicial e retorna resumo."""
    vetor = calcular_vetor()
    return {
        "direcao":        vetor["direcao"],
        "justificativa":  vetor["justificativa"],
        "proxima_tensao": vetor["proxima_tensao"],
    }


def instrucao_trajetoria() -> str:
    """
    Retorna instrução curta para injetar no contexto do LLM.
    Só injeta quando direção for relevante para a resposta.
    """
    try:
        entradas = _carregar()
        if not entradas:
            return ""
        ultimo = entradas[-1]
        direcao = ultimo.get("direcao", "aguardar")
        if direcao == "aguardar":
            return ""
        desc = _DIRECOES.get(direcao, "")
        return f"\n[TRAJETÓRIA DO SISTEMA: {direcao.upper()} — {desc}]"
    except Exception:
        return ""