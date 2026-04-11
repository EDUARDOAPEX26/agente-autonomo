"""
core/self_optimizer.py
Fase 19 — Arquiteto de Auto-Otimização

Lê livro_raciocinio.json, detecta gargalos por escopo e gera sugestões
seguras e reversíveis. Não altera código — só propõe configs aplicáveis
pelo safe_config_apply.py.

Execução:
  python -c "from core.self_optimizer import gerar_relatorio; gerar_relatorio()"
  ou chamado automaticamente pelo pipeline a cada N execuções.
"""

import json
import os
from collections import defaultdict
from datetime import datetime
from core.logger import info, warn

RACIOCINIO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_raciocinio.json"
)
RELATORIO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "optimizer_report.json"
)
SUGESTOES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "optimizer_suggestions.json"
)

# ── LIMIARES DE DIAGNÓSTICO ───────────────────────────────────────────────────
_LIMIAR_ERRO_CRITICO  = 0.60   # >= 60% erros → crítico
_LIMIAR_ERRO_ALTO     = 0.35   # >= 35% erros → alto
_LIMIAR_LATENCIA_ALTA = 8000   # >= 8s → latência alta
_JANELA              = 20      # últimas N entradas por escopo

# ── ANÁLISE POR ESCOPO ────────────────────────────────────────────────────────

def _analisar_escopo(entradas: list) -> dict:
    """Analisa métricas de um conjunto de entradas do mesmo escopo."""
    n = len(entradas)
    if n == 0:
        return {}

    erros = sum(
        1 for e in entradas
        if e.get("score", 1.0) < 0.6
        or e.get("erro_tipo", "ok") not in ("ok", "aceitar", "aceitar_com_cautela")
    )

    lats = [e.get("latencia_ms", 0) for e in entradas if e.get("latencia_ms", 0) > 0]
    lat_media = int(sum(lats) / len(lats)) if lats else 0

    apis = defaultdict(int)
    for e in entradas:
        apis[e.get("api_usada", "?")] += 1

    scores = [e.get("score", 1.0) for e in entradas]
    score_medio = round(sum(scores) / len(scores), 2)

    taxa_erro = round(erros / n, 2)

    nivel = "ok"
    if taxa_erro >= _LIMIAR_ERRO_CRITICO:
        nivel = "critico"
    elif taxa_erro >= _LIMIAR_ERRO_ALTO:
        nivel = "alto"
    elif lat_media >= _LIMIAR_LATENCIA_ALTA:
        nivel = "lento"

    return {
        "n":           n,
        "erros":       erros,
        "taxa_erro":   taxa_erro,
        "score_medio": score_medio,
        "lat_media_ms": lat_media,
        "apis":        dict(apis),
        "nivel":       nivel,
    }


# ── GERAÇÃO DE SUGESTÕES ──────────────────────────────────────────────────────

def _gerar_sugestoes(analise_por_escopo: dict) -> list:
    """
    Gera sugestões seguras baseadas na análise.
    Cada sugestão tem: escopo, problema, acao, parametro, valor, impacto, reversivel.
    """
    sugestoes = []

    for escopo, m in analise_por_escopo.items():
        if not m:
            continue

        nivel = m.get("nivel", "ok")

        # ── world_state com muitos erros ──────────────────────────────────────
        if escopo == "world_state" and nivel in ("critico", "alto"):
            sugestoes.append({
                "escopo":     escopo,
                "problema":   f"{m['taxa_erro']:.0%} de erros nas últimas {m['n']} execuções",
                "acao":       "aumentar_limiar_consenso",
                "parametro":  "LIMIAR_CONSENSO_WORLD_STATE",
                "valor":      2,
                "descricao":  "Exigir consenso mínimo de 2 fontes antes de aceitar dado",
                "impacto":    "reduz respostas erradas mas pode aumentar latência",
                "reversivel": True,
                "prioridade": "alta",
            })

        # ── world_state com latência alta ─────────────────────────────────────
        if escopo == "world_state" and m.get("lat_media_ms", 0) >= _LIMIAR_LATENCIA_ALTA:
            sugestoes.append({
                "escopo":     escopo,
                "problema":   f"Latência média {m['lat_media_ms']}ms (acima de {_LIMIAR_LATENCIA_ALTA}ms)",
                "acao":       "ativar_busca_paralela",
                "parametro":  "TRI_SOURCE_PARALELO",
                "valor":      True,
                "descricao":  "3 buscas simultâneas em vez de sequenciais (~7s vs ~20s)",
                "impacto":    "reduz latência em ~65%",
                "reversivel": True,
                "prioridade": "alta",
            })

        # ── merchant com erros acima do limiar ────────────────────────────────
        if escopo == "merchant_specific" and nivel in ("critico", "alto"):
            sugestoes.append({
                "escopo":     escopo,
                "problema":   f"{m['taxa_erro']:.0%} de erros em merchant_specific",
                "acao":       "desativar_early_exit",
                "parametro":  "EARLY_EXIT_MERCHANT",
                "valor":      False,
                "descricao":  "Sempre passar pelo LLM para validar preços de lojas",
                "impacto":    "mais custo de API mas menos preços errados",
                "reversivel": True,
                "prioridade": "media",
            })

        # ── encyclopedic com latência alta ────────────────────────────────────
        if escopo == "encyclopedic" and m.get("lat_media_ms", 0) >= _LIMIAR_LATENCIA_ALTA:
            sugestoes.append({
                "escopo":     escopo,
                "problema":   f"Latência média {m['lat_media_ms']}ms em encyclopedic",
                "acao":       "reduzir_max_tokens",
                "parametro":  "MAX_TOKENS_ENCYCLOPEDIC",
                "valor":      200,
                "descricao":  "Reduzir max_tokens de 400 para 200 em perguntas enciclopédicas",
                "impacto":    "reduz latência e custo, resposta mais direta",
                "reversivel": True,
                "prioridade": "baixa",
            })

    return sorted(sugestoes, key=lambda s: {"alta": 0, "media": 1, "baixa": 2}[s["prioridade"]])


# ── RELATÓRIO PRINCIPAL ───────────────────────────────────────────────────────

def gerar_relatorio(janela: int = _JANELA) -> dict:
    """
    Gera relatório de auto-otimização e salva em optimizer_report.json
    e optimizer_suggestions.json.
    """
    if not os.path.exists(RACIOCINIO_PATH):
        warn("OPTIMIZER", "livro_raciocinio.json não encontrado")
        return {}

    try:
        with open(RACIOCINIO_PATH, "r", encoding="utf-8") as f:
            todas = json.load(f)
    except Exception as e:
        warn("OPTIMIZER", f"Erro ao carregar raciocinio: {e}")
        return {}

    # Agrupa por escopo — só entradas com escopo definido
    por_escopo = defaultdict(list)
    for e in todas:
        esc = e.get("escopo", "")
        if esc and esc != "sem_escopo":
            por_escopo[esc].append(e)

    # Analisa só as últimas N por escopo
    analise = {}
    for esc, entradas in por_escopo.items():
        recentes = list(reversed(entradas))[:janela]
        analise[esc] = _analisar_escopo(recentes)

    sugestoes = _gerar_sugestoes(analise)

    # Conta problemas
    criticos = sum(1 for m in analise.values() if m.get("nivel") == "critico")
    altos    = sum(1 for m in analise.values() if m.get("nivel") == "alto")
    lentos   = sum(1 for m in analise.values() if m.get("nivel") == "lento")

    relatorio = {
        "gerado_em":    datetime.now().isoformat(),
        "janela":       janela,
        "total_dados":  len(todas),
        "escopos":      analise,
        "resumo": {
            "criticos": criticos,
            "altos":    altos,
            "lentos":   lentos,
            "total_sugestoes": len(sugestoes),
        },
        "sugestoes":    sugestoes,
    }

    # Salva relatório completo
    try:
        with open(RELATORIO_PATH, "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)
        info("OPTIMIZER", f"Relatório salvo: {len(sugestoes)} sugestões | criticos={criticos} altos={altos}")
    except Exception as e:
        warn("OPTIMIZER", f"Erro ao salvar relatório: {e}")

    # Salva só as sugestões (para safe_config_apply)
    try:
        with open(SUGESTOES_PATH, "w", encoding="utf-8") as f:
            json.dump(sugestoes, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("OPTIMIZER", f"Erro ao salvar sugestões: {e}")

    # Log resumido no terminal
    _logar_resumo(relatorio)

    return relatorio


def _logar_resumo(relatorio: dict):
    """Imprime resumo legível do relatório."""
    print("\n" + "="*60)
    print("  RELATÓRIO DE AUTO-OTIMIZAÇÃO — Fase 19")
    print("="*60)
    r = relatorio.get("resumo", {})
    print(f"  Dados analisados: {relatorio.get('total_dados', 0)} entradas")
    print(f"  Problemas críticos: {r.get('criticos', 0)}")
    print(f"  Problemas altos:    {r.get('altos', 0)}")
    print(f"  Lentos:             {r.get('lentos', 0)}")
    print(f"  Sugestões geradas:  {r.get('total_sugestoes', 0)}")
    print()

    for esc, m in relatorio.get("escopos", {}).items():
        nivel = m.get("nivel", "ok")
        emoji = {"ok": "✅", "lento": "⚠️", "alto": "🔴", "critico": "🚨"}.get(nivel, "❓")
        print(f"  {emoji} [{esc}] n={m['n']} | erro={m['taxa_erro']:.0%} | lat={m['lat_media_ms']}ms | score={m['score_medio']}")

    print()
    sugestoes = relatorio.get("sugestoes", [])
    if sugestoes:
        print("  SUGESTÕES:")
        for i, s in enumerate(sugestoes, 1):
            print(f"  {i}. [{s['prioridade'].upper()}] {s['escopo']} — {s['acao']}")
            print(f"     {s['descricao']}")
    else:
        print("  Nenhuma sugestão — sistema operando dentro dos limiares.")
    print("="*60 + "\n")


# ── EXECUÇÃO AUTOMÁTICA (chamada pelo pipeline a cada N execuções) ────────────

_EXECUTAR_A_CADA = 25   # gera relatório a cada 25 execuções do pipeline
_contador_execucoes = {"n": 0}

def verificar_e_otimizar():
    """
    Chamada pelo pipeline após cada execução.
    Gera relatório automaticamente a cada N execuções.
    """
    _contador_execucoes["n"] += 1
    if _contador_execucoes["n"] >= _EXECUTAR_A_CADA:
        _contador_execucoes["n"] = 0
        info("OPTIMIZER", f"Gerando relatório automático (a cada {_EXECUTAR_A_CADA} execuções)")
        try:
            gerar_relatorio()
        except Exception as e:
            warn("OPTIMIZER", f"Erro no relatório automático: {e}")


if __name__ == "__main__":
    gerar_relatorio()