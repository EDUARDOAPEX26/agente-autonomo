# core/truth_tiering.py
"""
Fase 22 — Herança Cognitiva Viva.
Aplica os níveis de verdade do integrity_guard em todas as fontes do sistema
e separa identidade real de romantização.

Função principal: auditar o conjunto de crenças e princípios e classificar
cada um com evidência ou sem evidência — impedindo que o legado vire ficção.

Níveis de verdade aplicados:
  observado  — evidência direta, aconteceu de fato
  recorrente — padrão confirmado múltiplas vezes
  inferido   — deduzido, preferência não confirmada
  narrativo  — relato autobiográfico, não verificável pelo sistema
"""

from core.logger import info, warn, debug


# ── AUDITORIA COMPLETA ────────────────────────────────────────────────────────

def auditar_crencas() -> dict:
    """
    Audita todas as crenças ativas e retorna distribuição por nível de verdade.
    Separa o que é verificável do que é narrativa.
    """
    from core.belief_tracker import listar_ativas
    from core.integrity_guard import classificar_lote, resumo_integridade

    crencas = listar_ativas(min_confianca=0.0)  # todas, sem filtro
    if not crencas:
        return {"total": 0, "auditadas": []}

    lote = classificar_lote([
        {"texto": c["texto"], "contagem": c.get("contagem", 1)}
        for c in crencas
    ])

    auditadas = []
    for i, c in enumerate(crencas):
        auditadas.append({
            "texto":         c["texto"][:200],
            "dominio":       c.get("dominio", "outro"),
            "confianca":     c.get("confianca", 0.5),
            "contagem":      c.get("contagem", 1),
            "nivel_verdade": lote[i]["nivel_verdade"],
        })

    resumo = resumo_integridade(lote)
    info("TRUTH", f"Crenças auditadas: {resumo}")

    return {"total": len(auditadas), "resumo": resumo, "auditadas": auditadas}


def auditar_principios() -> dict:
    """
    Audita todos os princípios ativos com níveis de verdade.
    """
    from core.principle_registry import listar_ativos
    from core.integrity_guard import classificar_lote, resumo_integridade

    principios = listar_ativos(min_confianca=0.0)
    if not principios:
        return {"total": 0, "auditados": []}

    lote = classificar_lote([
        {"texto": p["texto"], "contagem": p.get("contagem", 1)}
        for p in principios
    ])

    auditados = []
    for i, p in enumerate(principios):
        auditados.append({
            "texto":         p["texto"][:200],
            "dominio":       p.get("dominio", "outro"),
            "categoria":     p.get("categoria", "outro"),
            "confianca":     p.get("confianca", 0.8),
            "contagem":      p.get("contagem", 1),
            "nivel_verdade": lote[i]["nivel_verdade"],
        })

    resumo = resumo_integridade(lote)
    info("TRUTH", f"Princípios auditados: {resumo}")

    return {"total": len(auditados), "resumo": resumo, "auditados": auditados}


# ── SEPARAÇÃO IDENTIDADE REAL vs NARRATIVA ────────────────────────────────────

def separar_real_de_narrativa(entradas: list[dict]) -> dict:
    """
    Separa entradas em dois grupos:
      real      — observado + recorrente (verificável)
      narrativa — inferido + narrativo (não verificável)

    Entradas devem ter campo 'nivel_verdade'.
    Se não tiver, classifica na hora.
    """
    from core.integrity_guard import classificar

    real      = []
    narrativa = []

    for entrada in entradas:
        nivel = entrada.get("nivel_verdade")
        if not nivel:
            nivel = classificar(
                entrada.get("texto", ""),
                entrada.get("contagem", 1)
            )

        if nivel in ("observado", "recorrente"):
            real.append({**entrada, "nivel_verdade": nivel})
        else:
            narrativa.append({**entrada, "nivel_verdade": nivel})

    debug("TRUTH", f"Separação: {len(real)} real | {len(narrativa)} narrativa")

    return {"real": real, "narrativa": narrativa}


# ── RELATÓRIO COMPLETO ────────────────────────────────────────────────────────

def relatorio_completo() -> str:
    """
    Gera relatório textual completo de integridade do sistema cognitivo.
    Mostra o que é verificável e o que é narrativa — sem suprimir nenhum nível.
    """
    linhas = ["=== RELATÓRIO DE INTEGRIDADE COGNITIVA ===", ""]

    # Crenças
    auditoria_c = auditar_crencas()
    if auditoria_c["total"] > 0:
        resumo = auditoria_c["resumo"]
        linhas.append(f"CRENÇAS ({auditoria_c['total']} total | score={resumo.get('score',0):.0%})")
        for nivel in ("observado", "recorrente", "inferido", "narrativo"):
            n = resumo.get(nivel, 0)
            if n:
                linhas.append(f"  {nivel}: {n}")
        linhas.append("")

        sep = separar_real_de_narrativa(auditoria_c["auditadas"])
        if sep["real"]:
            linhas.append("  Verificáveis:")
            for e in sep["real"][:5]:
                linhas.append(f"    [{e['nivel_verdade']}] {e['texto'][:80]}")
        if sep["narrativa"]:
            linhas.append("  Não verificáveis (inferido/narrativo):")
            for e in sep["narrativa"][:5]:
                linhas.append(f"    [{e['nivel_verdade']}] {e['texto'][:80]}")
        linhas.append("")

    # Princípios
    auditoria_p = auditar_principios()
    if auditoria_p["total"] > 0:
        resumo = auditoria_p["resumo"]
        linhas.append(f"PRINCÍPIOS ({auditoria_p['total']} total | score={resumo.get('score',0):.0%})")
        for nivel in ("observado", "recorrente", "inferido", "narrativo"):
            n = resumo.get(nivel, 0)
            if n:
                linhas.append(f"  {nivel}: {n}")
        linhas.append("")

        sep = separar_real_de_narrativa(auditoria_p["auditados"])
        if sep["real"]:
            linhas.append("  Verificáveis:")
            for e in sep["real"][:5]:
                linhas.append(f"    [{e['nivel_verdade']}] {e['texto'][:80]}")
        if sep["narrativa"]:
            linhas.append("  Não verificáveis:")
            for e in sep["narrativa"][:5]:
                linhas.append(f"    [{e['nivel_verdade']}] {e['texto'][:80]}")
        linhas.append("")

    if auditoria_c["total"] == 0 and auditoria_p["total"] == 0:
        linhas.append("Nenhum dado cognitivo registrado ainda.")

    return "\n".join(linhas)