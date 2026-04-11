"""
core/book_raciocinio.py
Memória de raciocínio — lê e escreve livro_raciocinio.json.
Sem Chroma, sem subprocess, sem dependências externas.
Busca por similaridade simples de palavras.

Fase 17-A: registra escopo, latencia_ms e api_usada.
Fase 17-B: escopo_deve_usar_llm() — ajuste adaptativo de limiares por escopo.
"""
import json
import os
import threading
from datetime import datetime
from core.logger import info, debug, warn

RACIOCINIO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_raciocinio.json"
)
_cache = {"dados": None}
_lock  = threading.Lock()


def _carregar() -> list:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(RACIOCINIO_PATH):
        _cache["dados"] = []
        return []
    try:
        with open(RACIOCINIO_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
            _cache["dados"] = dados if isinstance(dados, list) else []
            return _cache["dados"]
    except Exception as e:
        warn("RACIOCINIO", f"Erro ao carregar: {e}")
        _cache["dados"] = []
        return []


def _salvar(entradas: list):
    try:
        with open(RACIOCINIO_PATH, "w", encoding="utf-8") as f:
            json.dump(entradas, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("RACIOCINIO", f"Erro ao salvar: {e}")


def buscar(pergunta: str, threshold: int = 2) -> dict | None:
    """
    Busca por similaridade de palavras.
    Retorna a entrada mais relevante ou None.
    threshold: mínimo de palavras em comum para considerar match.
    """
    entradas = _carregar()
    if not entradas:
        return None
    p = set(w for w in pergunta.lower().split() if len(w) > 3)
    melhor = None
    melhor_comuns = 0
    for entrada in entradas:
        texto = entrada.get("pergunta", "").lower()
        palavras = set(w for w in texto.split() if len(w) > 3)
        comuns = len(p & palavras)
        if comuns >= threshold and comuns > melhor_comuns:
            melhor_comuns = comuns
            melhor = entrada
    if melhor:
        debug("RACIOCINIO", f"Match encontrado ({melhor_comuns} palavras): {melhor.get('pergunta','')[:50]}")
    return melhor


def registrar(pergunta: str, estrategia: str, erro_tipo: str,
              correcao: str = "", score: float = 0.5,
              escopo: str = "", latencia_ms: int = 0, api_usada: str = ""):
    """
    Registra uma experiência de raciocínio.
    Fase 17-A: inclui escopo, latencia_ms e api_usada.
    """
    with _lock:
        entradas = _carregar()
        nova = {
            "pergunta":    pergunta[:200],
            "estrategia":  estrategia,
            "erro_tipo":   erro_tipo or "ok",
            "correcao":    correcao[:200] if correcao else "",
            "score":       round(score, 2),
            "escopo":      escopo,
            "latencia_ms": latencia_ms,
            "api_usada":   api_usada,
            "timestamp":   datetime.now().isoformat(),
        }
        entradas.append(nova)
        if len(entradas) > 500:
            entradas = entradas[-500:]
        _cache["dados"] = entradas
        threading.Thread(target=_salvar, args=(entradas,), daemon=True).start()
        info("RACIOCINIO", (
            f"Registrado: escopo={escopo} | api={api_usada} | "
            f"latencia={latencia_ms}ms | erro_tipo={erro_tipo} | score={score}"
        ))


# ── FASE 17-B — AJUSTE ADAPTATIVO DE LIMIARES ────────────────────────────────

# Quantas interações recentes analisar por escopo
_JANELA_17B = 10
# Taxa de erro que força uso de LLM (acima disso, early exit é desativado)
_LIMIAR_ERRO_ALTO = 0.4   # 40% de erros → sempre usa LLM
# Taxa de acerto que confirma early exit confiável
_LIMIAR_ACERTO_ALTO = 0.8  # 80% de acertos → early exit liberado


def escopo_deve_usar_llm(escopo: str) -> bool:
    """
    Fase 17-B — lê o histórico recente do escopo e decide se o early exit
    deve ser desativado temporariamente.

    Retorna True se o histórico mostra muitos erros → pipeline usa LLM.
    Retorna False se o histórico mostra acertos consistentes → early exit OK.

    Regras:
      - Menos de 3 entradas para o escopo → não há dados suficientes → False
        (mantém comportamento padrão, não penaliza o que não conhece)
      - Taxa de erro >= 40% nas últimas N interações → True (força LLM)
      - Taxa de acerto >= 80% → False (early exit confiável)
      - Entre 40% e 80% → False (usa early exit com cautela, valuator decide)
    """
    entradas = _carregar()
    if not entradas:
        return False

    # Filtra só as entradas do escopo pedido, mais recentes primeiro
    do_escopo = [
        e for e in reversed(entradas)
        if e.get("escopo") == escopo
    ][:_JANELA_17B]

    n = len(do_escopo)
    if n < 3:
        debug("17-B", f"escopo={escopo} | dados insuficientes ({n}) — early exit mantido")
        return False

    erros = sum(
        1 for e in do_escopo
        if e.get("erro_tipo", "ok") not in ("ok", "aceitar", "aceitar_com_cautela")
        or e.get("score", 1.0) < 0.6
    )
    taxa_erro = erros / n

    if taxa_erro >= _LIMIAR_ERRO_ALTO:
        warn("17-B", (
            f"escopo={escopo} | {erros}/{n} erros recentes ({taxa_erro:.0%}) "
            f"— early exit DESATIVADO, usando LLM"
        ))
        return True

    debug("17-B", (
        f"escopo={escopo} | {erros}/{n} erros ({taxa_erro:.0%}) "
        f"— early exit OK"
    ))
    return False