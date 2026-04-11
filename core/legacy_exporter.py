# core/legacy_exporter.py
"""
Fase 22 — Herança Cognitiva Viva.
Exporta o retrato cognitivo completo do usuário com níveis de verdade,
evidências e timeline em formato consultável.

Gera cápsulas cognitivas no livro_legado.json.
Cada cápsula é um snapshot datado da identidade verificável do usuário.
"""

import json
import os
import threading
from datetime import datetime
from core.logger import info, warn, debug

LEGADO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_legado.json"
)

_cache = {"dados": None}
_lock  = threading.Lock()


def _carregar() -> dict:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(LEGADO_PATH):
        _cache["dados"] = {"descricao": "Herança cognitiva viva", "versao": 1,
                           "criado_em": "", "atualizado_em": "", "capsulas": []}
        return _cache["dados"]
    try:
        with open(LEGADO_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
            _cache["dados"] = dados
            return dados
    except Exception as e:
        warn("LEGADO", f"Erro ao carregar: {e}")
        _cache["dados"] = {"capsulas": []}
        return _cache["dados"]


def _salvar(dados: dict):
    try:
        with open(LEGADO_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("LEGADO", f"Erro ao salvar: {e}")


# ── GERAÇÃO DE CÁPSULA ────────────────────────────────────────────────────────

def gerar_capsula(titulo: str = "") -> dict:
    """
    Gera uma cápsula cognitiva com o estado atual do usuário.
    Consolida crenças, princípios e constituição com níveis de verdade.
    Salva no livro_legado.json.
    """
    from core.integrity_guard import classificar_lote, resumo_integridade
    from core.constitution_builder import consultar as consultar_constituicao

    agora = datetime.now().isoformat()
    capsula = {
        "titulo":       titulo or f"Cápsula {agora[:10]}",
        "gerado_em":    agora,
        "principios":   [],
        "crencas":      [],
        "metamorfoses": [],
        "integridade":  {},
    }

    # Princípios
    try:
        from core.principle_registry import listar_ativos
        principios = listar_ativos(min_confianca=0.7)
        lote = classificar_lote([
            {"texto": p["texto"], "contagem": p.get("contagem", 1)}
            for p in principios
        ])
        for i, p in enumerate(principios):
            capsula["principios"].append({
                "texto":         p["texto"][:300],
                "dominio":       p.get("dominio", "outro"),
                "confianca":     p.get("confianca", 0.8),
                "nivel_verdade": lote[i]["nivel_verdade"],
            })
    except Exception as e:
        warn("LEGADO", f"Erro ao carregar princípios: {e}")

    # Crenças
    try:
        from core.belief_tracker import listar_ativas
        crencas = listar_ativas(min_confianca=0.65)
        lote = classificar_lote([
            {"texto": c["texto"], "contagem": c.get("contagem", 1)}
            for c in crencas
        ])
        for i, c in enumerate(crencas):
            capsula["crencas"].append({
                "texto":         c["texto"][:300],
                "dominio":       c.get("dominio", "outro"),
                "confianca":     c.get("confianca", 0.65),
                "contagem":      c.get("contagem", 1),
                "nivel_verdade": lote[i]["nivel_verdade"],
            })
    except Exception as e:
        warn("LEGADO", f"Erro ao carregar crenças: {e}")

    # Metamorfoses
    try:
        from core.metamorphosis_tracker import listar_metamorfoses
        metamorfoses = listar_metamorfoses()
        for m in metamorfoses[:10]:  # máx 10 por cápsula
            capsula["metamorfoses"].append({
                "de":           m.get("crenca_anterior", "")[:150],
                "para":         m.get("crenca_nova", "")[:150],
                "dominio":      m.get("dominio", "outro"),
                "gatilho":      m.get("gatilho", "")[:100],
                "nivel_verdade": "inferido",
            })
    except Exception as e:
        debug("LEGADO", f"Sem metamorfoses: {e}")

    # Score de integridade
    todas = (
        [{"texto": p["texto"], "nivel_verdade": p["nivel_verdade"]} for p in capsula["principios"]] +
        [{"texto": c["texto"], "nivel_verdade": c["nivel_verdade"]} for c in capsula["crencas"]]
    )
    capsula["integridade"] = resumo_integridade(todas)

    # Salva no livro
    with _lock:
        dados = _carregar()
        dados["capsulas"].append(capsula)
        # Mantém máximo de 50 cápsulas
        if len(dados["capsulas"]) > 50:
            dados["capsulas"] = dados["capsulas"][-50:]
        dados["atualizado_em"] = agora
        if not dados.get("criado_em"):
            dados["criado_em"] = agora
        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()

    info("LEGADO", (
        f"Cápsula gerada: '{capsula['titulo']}' | "
        f"{len(capsula['principios'])} princípios | "
        f"{len(capsula['crencas'])} crenças | "
        f"integridade={capsula['integridade'].get('score', 0):.2f}"
    ))

    return capsula


# ── CONSULTA ─────────────────────────────────────────────────────────────────

def listar_capsulas() -> list[dict]:
    """Retorna todas as cápsulas salvas."""
    dados = _carregar()
    return dados.get("capsulas", [])


def ultima_capsula() -> dict | None:
    """Retorna a cápsula mais recente."""
    capsulas = listar_capsulas()
    return capsulas[-1] if capsulas else None


def exportar_texto() -> str:
    """
    Exporta o retrato cognitivo em formato textual legível.
    Usado pelo temporal_council e para consulta direta.
    """
    capsula = ultima_capsula()
    if not capsula:
        return "Nenhuma cápsula cognitiva gerada ainda. Use gerar_capsula() primeiro."

    linhas = [
        f"=== RETRATO COGNITIVO — {capsula['gerado_em'][:10]} ===",
        f"Integridade: {capsula['integridade'].get('score', 0):.0%}",
        "",
    ]

    if capsula["principios"]:
        linhas.append("PRINCÍPIOS DECLARADOS:")
        for p in capsula["principios"]:
            linhas.append(
                f"  [{p['nivel_verdade']}] ({p['confianca']:.2f}) {p['texto'][:100]}"
            )
        linhas.append("")

    if capsula["crencas"]:
        linhas.append("CRENÇAS OPERACIONAIS:")
        for c in capsula["crencas"]:
            linhas.append(
                f"  [{c['nivel_verdade']}] ({c['confianca']:.2f}) {c['texto'][:100]}"
            )
        linhas.append("")

    if capsula["metamorfoses"]:
        linhas.append("REVISÕES DETECTADAS:")
        for m in capsula["metamorfoses"]:
            linhas.append(f"  DE: {m['de'][:60]}")
            linhas.append(f"  PARA: {m['para'][:60]}")
            linhas.append("")

    return "\n".join(linhas)