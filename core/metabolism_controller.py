"""
core/metabolism_controller.py
Fase 29 — Metabolismos do Sistema.

Correção Fase 35:
- _EMBRIONARIO_MIN aumentado de 3 para 6 — evita incubacao crônica
- Timeout de incubacao: se metabolismo=incubacao por mais de 48h sem mudança,
  força transição para exploracao
- PPD limiar de ruptura aumentado de 0.65 para 0.72 — menos sensível
- Fricções recentes precisam ter contagem >= 5 (antes era 4) para ruptura
"""

import os
import json
from datetime import datetime, timedelta
from core.logger import info, debug, warn

# ── LIMIARES DE DETECÇÃO ──────────────────────────────────────────────────────
_PPD_RUPTURA          = 0.72   # antes 0.65 — menos sensível
_PPD_PODA             = 0.55
_FRICCAO_RUPTURA      = 5      # antes 4 — precisa ser mais persistente
_FRICCAO_PODA         = 3
_EMBRIONARIO_MIN      = 6      # antes 3 — evita incubacao crônica
_CONSOLIDACAO_MUSCULAR = 3
_FRICCAO_JANELA_DIAS  = 7
_INCUBACAO_TIMEOUT_H  = 48     # horas máximas em incubacao antes de forçar exploracao

_ESTADO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "estado_local.json"
)

# ── INSTRUÇÕES POR METABOLISMO ────────────────────────────────────────────────
_INSTRUCOES = {
    "exploracao": (
        "\n[METABOLISMO: EXPLORAÇÃO] "
        "Território novo detectado. Expanda possibilidades, faça perguntas revelatórias, "
        "mapeie o que ainda não está definido. Prefira profundidade a resolução imediata."
    ),
    "consolidacao": (
        "\n[METABOLISMO: CONSOLIDAÇÃO] "
        "Ganhos recentes precisam ser fixados. Comprima, organize, confirme o que já funciona. "
        "Evite adicionar complexidade nova agora."
    ),
    "poda": (
        "\n[METABOLISMO: PODA] "
        "Complexidade acumulada alta. Priorize eliminar sobre adicionar. "
        "Se algo ficou bonito mas inútil, diga diretamente. Resposta curta e cirúrgica."
    ),
    "ruptura": (
        "\n[METABOLISMO: RUPTURA] "
        "Padrão improdutivo persistente detectado. O formato atual falhou. "
        "Confronte a estrutura antiga. Proponha mudança real, não refinamento. "
        "Desconforto produtivo é necessário aqui."
    ),
    "incubacao": (
        "\n[METABOLISMO: INCUBAÇÃO] "
        "Algo novo e frágil está se formando. Observe sem forçar conclusão. "
        "Proteja o embrião — não aja com força total agora. Responda com leveza."
    ),
}

_DESCRICOES = {
    "exploracao":   "expande e mapeia território novo",
    "consolidacao": "fixa e organiza ganhos recentes",
    "poda":         "descarta complexidade acumulada",
    "ruptura":      "confronta estrutura antiga improdutiva",
    "incubacao":    "protege capacidades frágeis emergentes",
}


# ── TIMEOUT DE INCUBAÇÃO ──────────────────────────────────────────────────────

def _verificar_timeout_incubacao() -> bool:
    """
    Retorna True se o sistema está em incubacao há mais de _INCUBACAO_TIMEOUT_H horas.
    Nesse caso, força transição para exploracao.
    """
    try:
        if not os.path.exists(_ESTADO_PATH):
            return False
        with open(_ESTADO_PATH, "r", encoding="utf-8") as f:
            estado = json.load(f)
        ultimo_metabolismo = estado.get("ultimo_metabolismo", {})
        if ultimo_metabolismo.get("tipo") != "incubacao":
            return False
        desde = ultimo_metabolismo.get("desde", "")
        if not desde:
            return False
        dt = datetime.fromisoformat(desde)
        horas = (datetime.now() - dt).total_seconds() / 3600
        if horas >= _INCUBACAO_TIMEOUT_H:
            warn("METABOLISMO", f"Timeout incubacao: {horas:.1f}h >= {_INCUBACAO_TIMEOUT_H}h → forçando exploracao")
            return True
    except Exception:
        pass
    return False


def _registrar_metabolismo(metabolismo: str):
    """Registra o metabolismo atual no estado_local.json para controle de timeout."""
    try:
        estado = {}
        if os.path.exists(_ESTADO_PATH):
            with open(_ESTADO_PATH, "r", encoding="utf-8") as f:
                estado = json.load(f)

        ultimo = estado.get("ultimo_metabolismo", {})
        # Só atualiza o timestamp se o metabolismo mudou
        if ultimo.get("tipo") != metabolismo:
            estado["ultimo_metabolismo"] = {
                "tipo":  metabolismo,
                "desde": datetime.now().isoformat(),
            }
            with open(_ESTADO_PATH, "w", encoding="utf-8") as f:
                json.dump(estado, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── DETECÇÃO ──────────────────────────────────────────────────────────────────

def detectar_metabolismo() -> str:
    """
    Detecta o metabolismo ativo baseado no estado atual do sistema.
    Usa apenas fricções RECENTES (últimos 7 dias).
    Aplica timeout de incubacao para evitar estado crônico.
    """
    ppd      = _obter_ppd()
    friccoes = _obter_friccoes_recentes()
    tecidos  = _obter_tecidos()
    forge    = _obter_forge()

    n_friccoes_ruptura = sum(
        1 for f in friccoes if f["contagem"] >= _FRICCAO_RUPTURA
    )

    # ── RUPTURA: PPD alto + fricção RECENTE persistente ──────────────────────
    if ppd >= _PPD_RUPTURA and n_friccoes_ruptura > 0:
        debug("METABOLISMO", f"ruptura | ppd={ppd:.2f} | criticas={n_friccoes_ruptura}")
        metabolismo = "ruptura"
        _registrar_metabolismo(metabolismo)
        return metabolismo

    # ── PODA: PPD médio + muitos embrionários ou experimentos rejeitados ─────
    embrionarios = tecidos.get("embrionario", 0)
    rejeitados   = forge.get("rejeitados", 0)
    if ppd >= _PPD_PODA and (embrionarios >= 4 or rejeitados >= 2):
        debug("METABOLISMO", f"poda | ppd={ppd:.2f} | embrionarios={embrionarios}")
        metabolismo = "poda"
        _registrar_metabolismo(metabolismo)
        return metabolismo

    # ── CONSOLIDAÇÃO: musculares em crescimento + PPD baixo ──────────────────
    muscular  = tecidos.get("muscular", 0)
    aprovados = forge.get("aprovados", 0)
    if muscular >= _CONSOLIDACAO_MUSCULAR or aprovados >= 1:
        debug("METABOLISMO", f"consolidacao | muscular={muscular} | aprovados={aprovados}")
        metabolismo = "consolidacao"
        _registrar_metabolismo(metabolismo)
        return metabolismo

    # ── INCUBAÇÃO: experimentos ativos ou embrionários (limiar maior) ─────────
    ativos = forge.get("ativos", 0)
    if ativos >= 1 or embrionarios >= _EMBRIONARIO_MIN:
        # Verifica timeout — se ficou muito tempo em incubacao, força exploracao
        if _verificar_timeout_incubacao():
            metabolismo = "exploracao"
            _registrar_metabolismo(metabolismo)
            return metabolismo
        debug("METABOLISMO", f"incubacao | ativos={ativos} | embrionarios={embrionarios}")
        metabolismo = "incubacao"
        _registrar_metabolismo(metabolismo)
        return metabolismo

    # ── EXPLORAÇÃO: fallback ──────────────────────────────────────────────────
    debug("METABOLISMO", "exploracao (fallback)")
    metabolismo = "exploracao"
    _registrar_metabolismo(metabolismo)
    return metabolismo


def instrucao_metabolismo(metabolismo: str = "") -> str:
    """
    Retorna instrução de fisiologia para injetar no prompt do LLM.
    Se metabolismo não for passado, detecta automaticamente.
    """
    if not metabolismo:
        metabolismo = detectar_metabolismo()
    return _INSTRUCOES.get(metabolismo, "")


def estado_atual() -> dict:
    """Retorna diagnóstico completo do metabolismo atual."""
    metabolismo = detectar_metabolismo()
    ppd         = _obter_ppd()
    friccoes    = _obter_friccoes_recentes()
    tecidos     = _obter_tecidos()
    forge       = _obter_forge()

    resultado = {
        "metabolismo":               metabolismo,
        "descricao":                 _DESCRICOES.get(metabolismo, ""),
        "ppd":                       ppd,
        "friccoes_recentes_criticas": len(friccoes),
        "tecidos":                   tecidos,
        "forge":                     forge,
    }

    info("METABOLISMO", (
        f"Metabolismo={metabolismo} | ppd={ppd:.2f} | "
        f"friccoes_recentes={len(friccoes)} | "
        f"muscular={tecidos.get('muscular', 0)} | "
        f"embrionario={tecidos.get('embrionario', 0)} | "
        f"forge_ativos={forge.get('ativos', 0)}"
    ))

    return resultado


# ── FONTES DE DADOS ───────────────────────────────────────────────────────────

def _obter_ppd() -> float:
    try:
        from core.ppd_tracker import calcular_ppd
        ppd = calcular_ppd()
        return ppd if ppd >= 0 else 0.0
    except Exception:
        return 0.0


def _obter_friccoes_recentes() -> list:
    """
    Retorna apenas fricções com atividade nos últimos _FRICCAO_JANELA_DIAS dias.
    """
    try:
        from core.friction_chamber import padroes_criticos
        todos  = padroes_criticos(limiar=2)
        agora  = datetime.now()
        limite = agora - timedelta(days=_FRICCAO_JANELA_DIAS)
        recentes = []
        for f in todos:
            ultima = f.get("ultima_vez") or f.get("ultima_vez_str", "")
            if not ultima:
                continue
            try:
                dt = datetime.fromisoformat(ultima)
                if dt >= limite:
                    recentes.append(f)
            except Exception:
                pass
        return recentes
    except Exception:
        return []


def _obter_tecidos() -> dict:
    try:
        from core.tissue_memory import resumo
        return resumo()
    except Exception:
        return {}


def _obter_forge() -> dict:
    try:
        from core.experiment_forge import resumo
        return resumo()
    except Exception:
        return {}