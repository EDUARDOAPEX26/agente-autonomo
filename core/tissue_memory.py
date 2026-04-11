"""
core/tissue_memory.py
Fase 27 — Memória Viva em Tecidos.
CORREÇÃO: livro_crencas.json pode ser lista [] — normaliza antes de iterar.
"""
import json, os, threading
from datetime import datetime
from core.logger import info, warn, debug

TECIDOS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "livro_tecidos.json")
_cache = {"dados": None}
_lock  = threading.Lock()
_contador = {"n": 0}

_TECIDOS = ["ossatura", "muscular", "cicatricial", "inflamado", "fantasma", "embrionario"]

def _carregar() -> dict:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(TECIDOS_PATH):
        _cache["dados"] = {t: [] for t in _TECIDOS}
        return _cache["dados"]
    try:
        with open(TECIDOS_PATH, "r", encoding="utf-8") as f:
            _cache["dados"] = json.load(f)
            return _cache["dados"]
    except Exception:
        _cache["dados"] = {t: [] for t in _TECIDOS}
        return _cache["dados"]

def _salvar(dados):
    try:
        with open(TECIDOS_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("TECIDOS", f"Erro ao salvar: {e}")

def _classificar_entrada(entrada):
    contagem  = entrada.get("contagem", 1)
    stability = entrada.get("stability", 0.5)
    ativa     = entrada.get("ativa", entrada.get("ativo", True))
    custo     = entrada.get("custo", "baixo")
    erro_tipo = entrada.get("erro_tipo", "ok")
    if not ativa and custo == "alto":
        return "cicatricial"
    if not ativa and custo != "alto":
        return "fantasma"
    if erro_tipo in ("consenso_fraco", "contradicao", "vazamento"):
        return "inflamado"
    if contagem >= 5 and stability >= 0.8:
        return "ossatura"
    if contagem >= 3 and stability >= 0.6:
        return "muscular"
    if contagem <= 2:
        return "embrionario"
    return "muscular"

def _to_dict(raw) -> dict:
    """Normaliza lista ou dict para dict indexado por id."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {str(i): v for i, v in enumerate(raw) if isinstance(v, dict)}
    return {}

def construir():
    base = os.path.dirname(os.path.dirname(__file__))
    def _load(nome, default):
        p = os.path.join(base, nome)
        if not os.path.exists(p):
            return default
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    crencas_raw    = _load("livro_crencas.json", {})
    principios_raw = _load("livro_principios.json", {})
    metamorfoses   = _load("livro_metamorfoses.json", [])

    # Normaliza: aceita lista ou dict
    crencas    = _to_dict(crencas_raw)
    principios = _to_dict(principios_raw)

    try:
        from core.stability_index import calcular_stability
    except Exception:
        calcular_stability = lambda e: e.get("stability", 0.5)

    tecidos = {t: [] for t in _TECIDOS}
    adicionados = 0

    for e in list(crencas.values()) + list(principios.values()):
        if not isinstance(e, dict):
            continue
        s = calcular_stability(e)
        entrada = {**e, "stability": s}
        tecido = _classificar_entrada(entrada)
        ids = [x.get("id") for x in tecidos[tecido]]
        if e.get("id") not in ids:
            tecidos[tecido].append({
                "id":       e.get("id", ""),
                "texto":    e.get("texto", "")[:200],
                "dominio":  e.get("dominio", "outro"),
                "stability": s,
                "contagem": e.get("contagem", 1),
            })
            adicionados += 1

    if isinstance(metamorfoses, list):
        for m in metamorfoses:
            if not isinstance(m, dict):
                continue
            tecido = "cicatricial" if m.get("custo") == "alto" else "fantasma"
            tecidos[tecido].append({
                "id":     m.get("id", ""),
                "texto":  m.get("texto_novo", "")[:200],
                "custo":  m.get("custo", "baixo"),
                "fonte":  "metamorfose",
            })
            adicionados += 1

    with _lock:
        _cache["dados"] = tecidos
        threading.Thread(target=_salvar, args=(tecidos,), daemon=True).start()

    info("TECIDOS", (
        f"ossatura={len(tecidos['ossatura'])} | "
        f"muscular={len(tecidos['muscular'])} | "
        f"embrionario={len(tecidos['embrionario'])} | "
        f"total={adicionados}"
    ))
    return tecidos

def consultar(tecido):
    return _carregar().get(tecido, [])

def resumo():
    dados = _carregar()
    return {t: len(dados.get(t, [])) for t in _TECIDOS}

def processar(msg="", resposta=""):
    _contador["n"] += 1
    if _contador["n"] % 10 == 0:
        try:
            construir()
        except Exception as e:
            warn("TECIDOS", f"Erro ao construir: {e}")