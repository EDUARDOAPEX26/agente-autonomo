"""
core/nucleo_vivo/metamorphosis_log_v3.py
Fase 36 — Metamorfose Autogênica + Consolidação Final

Integra:
- cognitive_genealogy.py  (Fase 34)
- self_amendment.py       (Fase 35)
- metamorphosis_tracker   (Fase 21)
- parliament_memory.py    (Fase 33)

Gera relatório unificado de evolução do sistema.
Verifica conectividade de todos os módulos das Fases 31-36.

Correção: usa funções reais de cada módulo (resumo, listar_pendentes, etc.)
"""

import os
import json
from datetime import datetime
from core.logger import info, warn

# ── Caminhos ──────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_LOG_PATH = os.path.join(_ROOT, "livro_metamorfose_v3.json")

# ── Módulos das Fases 31-36 para verificação ─────────────────────────────────
_MODULOS_ESPERADOS = {
    "cognitive_genealogy":   "core/nucleo_vivo/cognitive_genealogy.py",
    "self_amendment":        "core/nucleo_vivo/self_amendment.py",
    "parliament_memory":     "core/nucleo_vivo/parliament_memory.py",
    "metamorphosis_tracker": "core/metamorphosis_tracker.py",
    "belief_tracker":        "core/belief_tracker.py",
    "principle_registry":    "core/principle_registry.py",
    "constitution_builder":  "core/constitution_builder.py",
    "friction_chamber":      "core/friction_chamber.py",
    "ppd_tracker":           "core/ppd_tracker.py",
    "gravity_detector":      "core/gravity_detector.py",
    "internal_parliament":   "core/internal_parliament.py",
    "organ_factory":         "core/organ_factory.py",
    "tissue_memory":         "core/tissue_memory.py",
    "transmutation_engine":  "core/transmutation_engine.py",
    "experiment_forge":      "core/experiment_forge.py",
    "metabolism_controller": "core/metabolism_controller.py",
}


def _carregar_log() -> list:
    if not os.path.exists(_LOG_PATH):
        return []
    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
            return dados if isinstance(dados, list) else []
    except Exception:
        return []


def _salvar_log(entradas: list):
    try:
        with open(_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(entradas[-200:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("METAMORFOSE_V3", f"Erro ao salvar log: {e}")


def verificar_modulos() -> dict:
    """Verifica se todos os módulos das Fases 31-36 existem."""
    status = {}
    for nome, caminho in _MODULOS_ESPERADOS.items():
        caminho_abs = os.path.join(_ROOT, caminho.replace("/", os.sep))
        status[nome] = os.path.exists(caminho_abs)
    ativos = sum(1 for v in status.values() if v)
    total  = len(status)
    info("METAMORFOSE_V3", f"Módulos verificados: {ativos}/{total} ativos")
    return status


def _coletar_genealogia() -> dict:
    """Lê dados da genealogia cognitiva usando resumo()."""
    try:
        from core.nucleo_vivo.cognitive_genealogy import resumo
        r = resumo()
        return {
            "total_nos":     r.get("total_nos", 0),
            "total_arestas": r.get("total_arestas", 0),
            "orfaos":        r.get("orfaos", 0),
        }
    except Exception:
        pass
    # Fallback — lê direto do JSON
    livro = os.path.join(_ROOT, "livro_genealogia.json")
    if os.path.exists(livro):
        try:
            with open(livro, "r", encoding="utf-8") as f:
                dados = json.load(f)
                nos = dados.get("nos", {})
                return {
                    "total_nos":     len(nos) if isinstance(nos, dict) else 0,
                    "total_arestas": len(dados.get("arestas", [])),
                    "orfaos":        len(dados.get("orfaos", [])),
                }
        except Exception:
            pass
    return {"total_nos": 0, "total_arestas": 0, "orfaos": 0}


def _coletar_amendments() -> dict:
    """Lê resumo do self_amendment usando resumo()."""
    try:
        from core.nucleo_vivo.self_amendment import resumo, listar_pendentes
        r = resumo()
        pendentes = listar_pendentes()
        return {
            "pendentes":  r.get("pendentes", 0),
            "aplicadas":  r.get("aplicadas", 0),
            "rejeitadas": r.get("rejeitadas", 0),
            "ultimas_pendentes": [p.get("descricao", "")[:80] for p in pendentes[-3:]],
        }
    except Exception:
        pass
    livro = os.path.join(_ROOT, "livro_amendments.json")
    if os.path.exists(livro):
        try:
            with open(livro, "r", encoding="utf-8") as f:
                dados = json.load(f)
                return {
                    "pendentes":  len([p for p in dados.get("propostas", []) if p.get("status") == "pendente"]),
                    "aplicadas":  len(dados.get("aplicadas", [])),
                    "rejeitadas": len(dados.get("rejeitadas", [])),
                    "ultimas_pendentes": [],
                }
        except Exception:
            pass
    return {"pendentes": 0, "aplicadas": 0, "rejeitadas": 0, "ultimas_pendentes": []}


def _coletar_metamorphosis() -> dict:
    """Lê portfolio de metamorfoses."""
    try:
        from core.metamorphosis_tracker import consultar_portfolio
        r = consultar_portfolio()
        return {
            "total":    int(r.get("total", 0)),
            "estaveis": int(r.get("estaveis", 0)),
            "frageis":  int(r.get("frageis", 0)),
        }
    except Exception:
        return {"total": 0, "estaveis": 0, "frageis": 0}


def _coletar_parlamento() -> dict:
    """Lê memória do parlamento usando total()."""
    try:
        from core.nucleo_vivo.parliament_memory import parliament_memory
        total   = parliament_memory.total()
        ultimos = parliament_memory.get_ultimos_debates(1)
        ultimo  = ultimos[-1] if ultimos else {}
        return {"total_votos": total, "ultimo": ultimo}
    except Exception:
        pass
    # Fallback — lê do livro_parlamento.json
    livro = os.path.join(_ROOT, "livro_parlamento.json")
    if os.path.exists(livro):
        try:
            with open(livro, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, dict):
                    total = sum(v.get("vitorias", 0) for v in dados.values()
                                if isinstance(v, dict))
                    return {"total_votos": total, "ultimo": {}}
        except Exception:
            pass
    return {"total_votos": 0, "ultimo": {}}


def gerar_relatorio() -> dict:
    """Gera relatório unificado de evolução do sistema."""
    timestamp = datetime.now().isoformat()

    modulos_status = verificar_modulos()
    genealogia     = _coletar_genealogia()
    amendments     = _coletar_amendments()
    metamorphosis  = _coletar_metamorphosis()
    parlamento     = _coletar_parlamento()

    ativos        = sum(1 for v in modulos_status.values() if v)
    total         = len(modulos_status)
    score_modulos = round(ativos / total, 3)

    n_aplicadas    = int(amendments.get("aplicadas", 0))
    n_metamorfoses = int(metamorphosis.get("total", 0))
    n_nos          = int(genealogia.get("total_nos", 0))
    n_votos        = int(parlamento.get("total_votos", 0))

    score_evolucao = min(1.0, round(
        (n_aplicadas * 0.3 + n_metamorfoses * 0.3 + n_nos * 0.2 + n_votos * 0.2) / 10, 3
    ))

    relatorio = {
        "timestamp":      timestamp,
        "fase":           36,
        "score_modulos":  score_modulos,
        "score_evolucao": score_evolucao,
        "modulos": {
            "ativos": ativos,
            "total":  total,
            "status": modulos_status,
        },
        "genealogia": {
            "nos":      n_nos,
            "relacoes": int(genealogia.get("total_arestas", 0)),
            "orfaos":   int(genealogia.get("orfaos", 0)),
        },
        "amendments": {
            "pendentes":  int(amendments.get("pendentes", 0)),
            "aplicadas":  n_aplicadas,
            "rejeitadas": int(amendments.get("rejeitadas", 0)),
        },
        "metamorphosis": {
            "total":    n_metamorfoses,
            "estaveis": int(metamorphosis.get("estaveis", 0)),
            "frageis":  int(metamorphosis.get("frageis", 0)),
        },
        "parlamento": {
            "total_votos": n_votos,
            "ultimo":      parlamento.get("ultimo", {}),
        },
    }

    entradas = _carregar_log()
    entradas.append(relatorio)
    _salvar_log(entradas)

    info("METAMORFOSE_V3",
         f"Relatório | modulos={score_modulos:.0%} | evolucao={score_evolucao:.0%} | "
         f"nos={n_nos} | amendments={n_aplicadas} | metamorfoses={n_metamorfoses}")

    return relatorio


def imprimir_relatorio(relatorio: dict = None) -> str:
    """Retorna string formatada do relatório."""
    if relatorio is None:
        relatorio = gerar_relatorio()

    linhas = [
        "=" * 60,
        f"  RELATÓRIO DE METAMORFOSE v3 — Fase 36",
        f"  {relatorio['timestamp'][:19]}",
        "=" * 60,
        f"  Score Módulos : {relatorio['score_modulos']*100:.1f}%  "
        f"({relatorio['modulos']['ativos']}/{relatorio['modulos']['total']} ativos)",
        f"  Score Evolução: {relatorio['score_evolucao']*100:.1f}%",
        "-" * 60,
        f"  Genealogia    : {relatorio['genealogia']['nos']} nós | "
        f"{relatorio['genealogia']['relacoes']} relações",
        f"  Amendments    : {relatorio['amendments']['aplicadas']} aplicadas | "
        f"{relatorio['amendments']['pendentes']} pendentes",
        f"  Metamorfoses  : {relatorio['metamorphosis']['total']} total | "
        f"{relatorio['metamorphosis']['estaveis']} estáveis",
        f"  Parlamento    : {relatorio['parlamento']['total_votos']} votos",
        "-" * 60,
        "  MÓDULOS:",
    ]

    for nome, ativo in relatorio["modulos"]["status"].items():
        icone = "✅" if ativo else "❌"
        linhas.append(f"    {icone} {nome}")

    linhas.append("=" * 60)
    return "\n".join(linhas)


def consolidar_fase36() -> dict:
    """DoD (Definition of Done) da Fase 36."""
    relatorio = gerar_relatorio()

    dod = {
        "modulos_completos":    relatorio["score_modulos"] >= 0.85,
        "genealogia_ativa":     relatorio["genealogia"]["nos"] > 0,
        "parlamento_ativo":     relatorio["parlamento"]["total_votos"] > 0,
        "pipeline_operacional": os.path.exists(
            os.path.join(_ROOT, "core", "pipeline.py")
        ),
        "backup_existente": any(
            f.endswith(".zip")
            for f in os.listdir(os.path.join(_ROOT, ".."))
            if os.path.isfile(os.path.join(_ROOT, "..", f))
        ),
    }

    aprovado   = all(dod.values())
    dod["aprovado"]  = aprovado
    dod["timestamp"] = datetime.now().isoformat()

    status = "✅ APROVADO" if aprovado else "⚠️ PENDÊNCIAS"
    info("METAMORFOSE_V3", f"DoD Fase 36: {status}")
    for k, v in dod.items():
        if k not in ("aprovado", "timestamp"):
            icone = "✅" if v else "❌"
            info("METAMORFOSE_V3", f"  {icone} {k}: {v}")

    return dod


def processar(msg: str = "", resposta: str = "") -> None:
    """Chamado pelo pipeline — gera relatório a cada 50 interações."""
    try:
        entradas = _carregar_log()
        if len(entradas) % 50 == 0:
            gerar_relatorio()
    except Exception as e:
        from core.logger import debug
        debug("METAMORFOSE_V3", f"processar: {e}")