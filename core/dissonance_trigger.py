# core/dissonance_trigger.py
"""Fase 20 — Motor de Coerência Cognitiva."""

import json, os, threading
from datetime import datetime
from core.logger import info, warn, debug

_BASE = os.path.dirname(os.path.dirname(__file__))
_HISTORICO_PATH = os.path.join(_BASE, "livro_dissonancia.json")
_MODO_PADRAO = "medium"
_LIMIARES = {"off": None, "light": None, "medium": 0.6, "deep": 0.4}
_COOLDOWN_MINUTOS = 30
_ultimo_aviso = {}
_lock = threading.Lock()


def _carregar_historico():
    if not os.path.exists(_HISTORICO_PATH): return []
    try:
        with open(_HISTORICO_PATH, "r", encoding="utf-8") as f: return json.load(f)
    except: return []


def _salvar_historico(entradas):
    try:
        with open(_HISTORICO_PATH, "w", encoding="utf-8") as f:
            json.dump(entradas[-200:], f, ensure_ascii=False, indent=2)
    except Exception as e: warn("DISSONANCIA", f"Erro: {e}")


def _registrar_intervencao(msg, conflito, aviso):
    entrada = {"timestamp": datetime.now().isoformat(), "msg": msg[:200],
               "dominio": conflito.get("dominio",""), "tipo": conflito.get("tipo",""),
               "intensidade": conflito.get("intensidade",0),
               "texto_ref": conflito.get("texto_ref","")[:100], "aviso": aviso[:300]}
    h = _carregar_historico(); h.append(entrada)
    threading.Thread(target=_salvar_historico, args=(h,), daemon=True).start()


def _em_cooldown(dominio):
    with _lock:
        ultimo = _ultimo_aviso.get(dominio)
        if ultimo is None: return False
        return (datetime.now() - ultimo).total_seconds() / 60 < _COOLDOWN_MINUTOS


def _marcar_cooldown(dominio):
    with _lock: _ultimo_aviso[dominio] = datetime.now()


def _gerar_aviso(conflito):
    tipo = conflito.get("tipo","crenca")
    texto_ref = conflito.get("texto_ref","")[:120]
    intensidade = conflito.get("intensidade",0)
    prefixo = "Nota" if tipo == "principio" else "Observacao"
    tom = ("Isso parece entrar em conflito direto com" if intensidade >= 0.75
           else "Isso pode estar em tensao com" if intensidade >= 0.55
           else "Isso contrasta um pouco com")
    ref = f'"{texto_ref}"' if texto_ref else f"seu criterio de {conflito.get('dominio','')}"
    return f"{prefixo}: {tom} {ref}."


def verificar_dissonancia(msg, modo=_MODO_PADRAO):
    if modo == "off": return None
    limiar = _LIMIARES.get(modo, 0.6)
    try:
        from core.belief_tracker import listar_ativas as lc
        from core.principle_registry import listar_ativos as lp
        from core.contradiction_engine import detectar_conflitos, conflito_mais_grave
        crencas = lc(); principios = lp()
        if not crencas and not principios: return None
        conflitos = detectar_conflitos(msg, crencas, principios, min_intensidade=limiar or 0.4)
        if not conflitos: return None
        conflito = conflito_mais_grave(conflitos)
        if not conflito: return None
        dominio = conflito.get("dominio","")
        intensidade = conflito.get("intensidade",0)
        if modo == "light":
            info("DISSONANCIA", f"[light] {dominio} | {intensidade:.2f}")
            _registrar_intervencao(msg, conflito, "registrado_sem_aviso")
            return None
        if _em_cooldown(dominio): return None
        if limiar and intensidade < limiar: return None
        aviso = _gerar_aviso(conflito)
        _marcar_cooldown(dominio)
        _registrar_intervencao(msg, conflito, aviso)
        warn("DISSONANCIA", f"Intervencao: {dominio} | {conflito['tipo']} | {intensidade:.2f}")
        return aviso
    except ImportError as e:
        debug("DISSONANCIA", f"Modulo nao disponivel: {e}"); return None
    except Exception as e:
        warn("DISSONANCIA", f"Erro: {e}"); return None


def stats_dissonancia():
    h = _carregar_historico()
    if not h: return {"total": 0, "por_dominio": {}, "por_tipo": {}}
    from collections import defaultdict
    pd, pt = defaultdict(int), defaultdict(int)
    for e in h:
        pd[e.get("dominio","?")] += 1; pt[e.get("tipo","?")] += 1
    return {"total": len(h), "por_dominio": dict(pd), "por_tipo": dict(pt),
            "ultima": h[-1].get("timestamp","") if h else ""}