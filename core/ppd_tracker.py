"""
core/ppd_tracker.py
Fase 23 — PPD: Pressão de Potência Dissipada.

Mede o quanto existe de inteligência, desejo, visão e energia no sistema
do usuário — mas que não está virando transformação real.

PPD alto = energia vazando em análise, complexidade, dúvida ou perfeccionismo.
PPD baixo = energia se convertendo em mudança real.

Quando PPD ultrapassa limiar → pipeline muda de papel:
  de "assistente explicador" → para "compressor de destino"
"""

import json
import os
import threading
from datetime import datetime, timedelta
from core.logger import info, warn, debug

PPD_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_ppd.json"
)

_cache = {"dados": None}
_lock  = threading.Lock()

# ── SINAIS QUE AUMENTAM O PPD (potência vazando) ─────────────────────────────
_SINAIS_DISSIPACAO = [
    # análise sem conclusão
    "por outro lado", "mas também", "depende de", "ainda estou pensando",
    "preciso analisar", "mais uma opção", "e se", "talvez",
    # complexidade acumulada
    "ficou complexo", "muita coisa", "difícil de manter", "preciso refatorar",
    "acumulou", "débito técnico", "bagunça", "confuso",
    # repetição de padrão
    "de novo", "mais uma vez", "ainda não", "continua igual",
    "voltou", "não mudou", "mesmo problema",
    # perfeccionismo paralisante
    "não está bom", "precisa melhorar", "ainda falta", "não está pronto",
    "quase lá", "falta pouco mas",
]

# ── SINAIS QUE DIMINUEM O PPD (potência virando transformação) ────────────────
_SINAIS_TRANSFORMACAO = [
    # decisão tomada
    "decidi", "fechei", "bati martelo", "vou fazer", "já fiz",
    "terminei", "entregou", "concluído", "pronto",
    # mudança real
    "mudei", "novo padrão", "aprendi", "não vou mais", "agora faço",
    "transformei", "virei", "consegui",
    # ação concreta
    "rodei", "testei", "publiquei", "implementei", "executei",
    "coloquei em produção", "subiu", "funcionou",
]

# ── LIMIARES ─────────────────────────────────────────────────────────────────
_PPD_CRITICO  = 0.7   # >= 70% das interações recentes com dissipação
_PPD_ALTO     = 0.5   # >= 50%
_JANELA_DIAS  = 7     # analisa últimos 7 dias
_JANELA_MIN   = 5     # mínimo de interações para calcular


# ── PERSISTÊNCIA ─────────────────────────────────────────────────────────────

def _carregar() -> list:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(PPD_PATH):
        _cache["dados"] = []
        return []
    try:
        with open(PPD_PATH, "r", encoding="utf-8") as f:
            _cache["dados"] = json.load(f)
            return _cache["dados"]
    except Exception:
        _cache["dados"] = []
        return []


def _salvar(dados: list):
    try:
        with open(PPD_PATH, "w", encoding="utf-8") as f:
            json.dump(dados[-500:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("PPD", f"Erro ao salvar: {e}")


# ── ANÁLISE ───────────────────────────────────────────────────────────────────

def _analisar_texto(texto: str) -> str:
    """Classifica uma interação como 'dissipacao', 'transformacao' ou 'neutro'."""
    t = texto.lower()
    score_dissipacao    = sum(1 for s in _SINAIS_DISSIPACAO    if s in t)
    score_transformacao = sum(1 for s in _SINAIS_TRANSFORMACAO if s in t)

    if score_transformacao > score_dissipacao:
        return "transformacao"
    if score_dissipacao > 0:
        return "dissipacao"
    return "neutro"


def registrar(msg: str, resposta: str = ""):
    """Registra uma interação e classifica seu impacto no PPD."""
    texto = msg + " " + resposta
    tipo  = _analisar_texto(texto)

    entrada = {
        "timestamp": datetime.now().isoformat(),
        "tipo":      tipo,
        "trecho":    msg[:100],
    }

    with _lock:
        dados = _carregar()
        dados.append(entrada)
        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()

    if tipo == "dissipacao":
        debug("PPD", f"Dissipação registrada: {msg[:50]}")
    elif tipo == "transformacao":
        debug("PPD", f"Transformação registrada: {msg[:50]}")

    return tipo


def calcular_ppd() -> float:
    """
    Calcula PPD atual: proporção de interações com dissipação nos últimos N dias.
    Retorna valor 0.0 (toda transformação) a 1.0 (toda dissipação).
    Retorna -1.0 se não há dados suficientes.
    """
    dados    = _carregar()
    corte    = datetime.now() - timedelta(days=_JANELA_DIAS)
    recentes = [
        e for e in dados
        if _ts(e.get("timestamp", "")) >= corte
    ]

    if len(recentes) < _JANELA_MIN:
        return -1.0

    dissipacoes    = sum(1 for e in recentes if e.get("tipo") == "dissipacao")
    transformacoes = sum(1 for e in recentes if e.get("tipo") == "transformacao")
    total          = len(recentes)

    ppd = dissipacoes / total
    debug("PPD", f"PPD={ppd:.2f} | {dissipacoes} dissip | {transformacoes} transf | {total} total")
    return round(ppd, 3)


def _ts(iso: str) -> datetime:
    try:
        return datetime.fromisoformat(iso)
    except Exception:
        return datetime.min


# ── PAPEL DO AGENTE ───────────────────────────────────────────────────────────

def papel_agente() -> str:
    """
    Retorna o papel recomendado para o agente baseado no PPD atual.

    Papéis:
      "explicador"  — PPD baixo/normal, modo padrão
      "acelerador"  — PPD médio, foca em ação prática
      "compressor"  — PPD crítico, comprime para o essencial
    """
    ppd = calcular_ppd()

    if ppd < 0:
        return "explicador"  # dados insuficientes
    if ppd >= _PPD_CRITICO:
        info("PPD", f"PPD crítico ({ppd:.0%}) — modo compressor ativado")
        return "compressor"
    if ppd >= _PPD_ALTO:
        info("PPD", f"PPD alto ({ppd:.0%}) — modo acelerador ativado")
        return "acelerador"

    return "explicador"


def instrucao_papel(papel: str) -> str:
    """
    Retorna instrução para o LLM baseada no papel atual.
    Injetada no contexto do prompt.
    """
    if papel == "compressor":
        return (
            "\n[MODO COMPRESSOR ATIVO]\n"
            "O usuário está em ciclo de dissipação de energia. "
            "Responda com NO MÁXIMO 2 frases. "
            "Não analise. Não explique. "
            "Comprima para a essência ou exija uma ação concreta e pequena."
        )
    if papel == "acelerador":
        return (
            "\n[MODO ACELERADOR]\n"
            "Priorize ação sobre análise. "
            "Se possível, termine com uma pergunta que force escolha binária."
        )
    return ""


def resumo() -> dict:
    """Retorna resumo do estado atual do PPD."""
    ppd   = calcular_ppd()
    papel = papel_agente()

    dados    = _carregar()
    corte    = datetime.now() - timedelta(days=_JANELA_DIAS)
    recentes = [e for e in dados if _ts(e.get("timestamp", "")) >= corte]

    return {
        "ppd":             ppd if ppd >= 0 else "insuficiente",
        "papel":           papel,
        "interacoes_7d":   len(recentes),
        "dissipacoes_7d":  sum(1 for e in recentes if e.get("tipo") == "dissipacao"),
        "transformacoes_7d": sum(1 for e in recentes if e.get("tipo") == "transformacao"),
    }