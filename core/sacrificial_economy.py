"""
core/sacrificial_economy.py
Fase 38 — Economia Sacrificial
Remove ou congela elementos que não agregam valor.
Usa dados reais de uso do livro_raciocinio para decidir o que podar.
"""
import json
import os
import threading
from datetime import datetime
from core.logger import info, warn, debug

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SACRIFICIOS_PATH = os.path.join(_RAIZ, "livro_sacrificios.json")
_RACIOCINIO_PATH = os.path.join(_RAIZ, "livro_raciocinio.json")
_lock = threading.Lock()

# Limiar de score baixo para considerar sacrifício
_SCORE_BAIXO = 0.5
# Mínimo de ocorrências para analisar um padrão
_MIN_OCORRENCIAS = 3

# Módulos internos que NUNCA são candidatos a sacrifício
# São nomes de módulos de controle, não estratégias de API
_PROTEGIDOS = {
    "valuator", "evaluator", "anti_loop", "consensus",
    "exa_early_exit", "exa_consensus", "classifier",
}


def _carregar_sacrificios() -> dict:
    try:
        with open(_SACRIFICIOS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"meta": {}, "sacrificios": []}


def _salvar_sacrificios(data: dict):
    try:
        with open(_SACRIFICIOS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("SACRIFICIAL", f"Erro ao salvar: {e}")


def _carregar_raciocinio() -> list:
    try:
        with open(_RACIOCINIO_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
            return dados if isinstance(dados, list) else []
    except Exception:
        return []


def analisar() -> list:
    """
    Analisa o livro_raciocinio buscando padrões de baixo desempenho.
    Retorna lista de candidatos a sacrifício.
    """
    entradas = _carregar_raciocinio()
    if not entradas:
        return []

    # Agrupa por estratégia
    por_estrategia = {}
    for e in entradas:
        estrategia = e.get("estrategia", "desconhecida")
        if estrategia not in por_estrategia:
            por_estrategia[estrategia] = []
        por_estrategia[estrategia].append(e)

    candidatos = []
    for estrategia, registros in por_estrategia.items():
        # Nunca analisa módulos internos de controle
        if estrategia in _PROTEGIDOS:
            debug("SACRIFICIAL", f"Protegido — ignorando: {estrategia}")
            continue

        if len(registros) < _MIN_OCORRENCIAS:
            continue

        scores = [r.get("score", 1.0) for r in registros]
        score_medio = sum(scores) / len(scores)
        latencias = [r.get("latencia_ms", 0) for r in registros]
        latencia_media = sum(latencias) / len(latencias)
        erros = sum(1 for r in registros if r.get("erro_tipo", "ok") != "ok")
        taxa_erro = erros / len(registros)

        # Candidato se score baixo OU alta latência com erros
        if score_medio < _SCORE_BAIXO or (latencia_media > 15000 and taxa_erro > 0.3):
            candidato = {
                "alvo": estrategia,
                "motivo": (
                    f"score_medio={score_medio:.2f} | "
                    f"latencia_media={int(latencia_media)}ms | "
                    f"taxa_erro={taxa_erro:.0%} | "
                    f"ocorrencias={len(registros)}"
                ),
                "custo_manter": min(10, int(taxa_erro * 10 + latencia_media / 3000)),
                "ganho_remover": min(10, int((1 - score_medio) * 10)),
                "risco": 3,
                "status": "candidato",
                "analisado_em": datetime.now().isoformat(),
            }
            candidatos.append(candidato)
            warn("SACRIFICIAL", (
                f"Candidato a sacrifício: {estrategia} | "
                f"score={score_medio:.2f} | erros={taxa_erro:.0%}"
            ))

    if candidatos:
        with _lock:
            data = _carregar_sacrificios()
            # Evita duplicatas pelo alvo
            alvos_existentes = {s["alvo"] for s in data["sacrificios"]}
            novos = [c for c in candidatos if c["alvo"] not in alvos_existentes]
            data["sacrificios"].extend(novos)
            _salvar_sacrificios(data)
            if novos:
                info("SACRIFICIAL", f"{len(novos)} novo(s) candidato(s) registrado(s)")

    return candidatos


def executar_sacrificio(alvo: str, justificativa: str) -> bool:
    """
    Marca um alvo como removido no livro de sacrifícios.
    Não remove código — apenas registra a decisão para revisão manual.
    """
    with _lock:
        data = _carregar_sacrificios()
        for s in data["sacrificios"]:
            if s["alvo"] == alvo:
                s["status"] = "removido"
                s["justificativa"] = justificativa
                s["removido_em"] = datetime.now().isoformat()
                _salvar_sacrificios(data)
                info("SACRIFICIAL", f"Sacrifício executado: {alvo} | {justificativa}")
                return True

        # Se não encontrou, cria novo registro
        data["sacrificios"].append({
            "alvo": alvo,
            "motivo": justificativa,
            "custo_manter": 5,
            "ganho_remover": 5,
            "risco": 5,
            "status": "removido",
            "justificativa": justificativa,
            "removido_em": datetime.now().isoformat(),
        })
        _salvar_sacrificios(data)
        return True


def relatorio() -> dict:
    """Retorna resumo do estado da economia sacrificial."""
    data = _carregar_sacrificios()
    sacrificios = data.get("sacrificios", [])

    por_status = {}
    for s in sacrificios:
        status = s.get("status", "desconhecido")
        por_status[status] = por_status.get(status, 0) + 1

    return {
        "total": len(sacrificios),
        "por_status": por_status,
        "candidatos": por_status.get("candidato", 0),
        "removidos": por_status.get("removido", 0),
    }


def inicializar():
    candidatos = analisar()
    rel = relatorio()
    info("SACRIFICIAL", (
        f"Fase 38 inicializada | total={rel['total']} | "
        f"candidatos={rel['candidatos']} | removidos={rel['removidos']}"
    ))
    return rel