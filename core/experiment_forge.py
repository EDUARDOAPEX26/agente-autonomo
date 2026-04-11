"""
core/experiment_forge.py
Fase 28 — Forno de Experimentos.
"""
import json, os, threading
from datetime import datetime
from core.logger import info, warn, debug

FORGE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "livro_experimentos.json")
_cache = {"dados": None}
_lock  = threading.Lock()
_MIN_INTERACOES  = 3
_MAX_INTERACOES  = 10
_SCORE_APROVACAO = 0.75
_SCORE_REJEICAO  = 0.60
_ERROS_GRAVES    = {"vazamento", "contradicao"}

def _carregar():
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(FORGE_PATH):
        _cache["dados"] = {"experimentos": [], "historico": []}
        return _cache["dados"]
    try:
        with open(FORGE_PATH, "r", encoding="utf-8") as f:
            _cache["dados"] = json.load(f)
            return _cache["dados"]
    except Exception:
        _cache["dados"] = {"experimentos": [], "historico": []}
        return _cache["dados"]

def _salvar(dados):
    try:
        with open(FORGE_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("FORGE", f"Erro ao salvar: {e}")

def iniciar_experimento(mutacao_id):
    try:
        from core.transmutation_engine import listar, atualizar_status
    except ImportError:
        warn("FORGE", "transmutation_engine nao disponivel")
        return False
    propostas = [m for m in listar("proposta") if m.get("id") == mutacao_id]
    if not propostas:
        return False
    mutacao = propostas[0]
    atualizar_status(mutacao_id, "em_teste")
    with _lock:
        dados = _carregar()
        ids_ativos = {e.get("mutacao_id") for e in dados["experimentos"] if e.get("status") == "ativo"}
        if mutacao_id in ids_ativos:
            return False
        dados["experimentos"].append({
            "mutacao_id": mutacao_id, "nome": mutacao.get("nome",""),
            "tipo": mutacao.get("tipo",""), "status": "ativo",
            "iniciado_em": datetime.now().isoformat(), "interacoes": [],
            "score_medio": None, "decisao": None,
        })
        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()
    info("FORGE", f"Experimento iniciado: [{mutacao['tipo']}] {mutacao['nome']}")
    return True

def registrar_interacao(score, erro_tipo):
    with _lock:
        dados = _carregar()
        ativos = [e for e in dados["experimentos"] if e.get("status") == "ativo"]
        if not ativos:
            return
        agora = datetime.now().isoformat()
        for exp in ativos:
            exp["interacoes"].append({"timestamp": agora, "score": score, "erro_tipo": erro_tipo})
        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()

def avaliar_experimentos():
    try:
        from core.transmutation_engine import atualizar_status as te_atualizar
    except ImportError:
        return []
    with _lock:
        dados    = _carregar()
        ativos   = [e for e in dados["experimentos"] if e.get("status") == "ativo"]
        decisoes = []
        for exp in ativos:
            interacoes  = exp.get("interacoes", [])
            n           = len(interacoes)
            if n < _MIN_INTERACOES:
                continue
            scores       = [i["score"] for i in interacoes]
            erros        = [i["erro_tipo"] for i in interacoes]
            score_medio  = round(sum(scores)/n, 3)
            erros_graves = sum(1 for e in erros if e in _ERROS_GRAVES)
            forcar       = n >= _MAX_INTERACOES
            exp["score_medio"] = score_medio
            decisao = None
            if erros_graves >= 2 or (forcar and score_medio < _SCORE_REJEICAO):
                decisao = "rejeitada"
                exp["status"] = "rejeitado"; exp["decisao"] = decisao
                te_atualizar(exp["mutacao_id"], "rejeitada")
                warn("FORGE", f"REJEITADO: {exp['nome']} | score={score_medio:.2f}")
            elif score_medio >= _SCORE_APROVACAO or (forcar and score_medio >= _SCORE_REJEICAO):
                decisao = "consolidada"
                exp["status"] = "aprovado"; exp["decisao"] = decisao
                te_atualizar(exp["mutacao_id"], "consolidada")
                info("FORGE", f"CONSOLIDADO: {exp['nome']} | score={score_medio:.2f}")
                try:
                    from core.tissue_memory import construir
                    construir()
                except Exception:
                    pass
            if decisao:
                decisoes.append({"mutacao_id": exp["mutacao_id"], "nome": exp["nome"],
                    "decisao": decisao, "score_medio": score_medio, "n": n})
                dados["historico"].append({**decisoes[-1], "decidido_em": datetime.now().isoformat()})
        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()
    return decisoes

def processar(score=1.0, erro_tipo="ok"):
    try:
        dados  = _carregar()
        ativos = [e for e in dados.get("experimentos",[]) if e.get("status") == "ativo"]
        if not ativos:
            from core.transmutation_engine import listar
            propostas = listar("proposta")
            if propostas:
                iniciar_experimento(propostas[0]["id"])
    except Exception:
        pass
    registrar_interacao(score, erro_tipo)
    decisoes = avaliar_experimentos()
    for d in decisoes:
        info("FORGE", f"Decisao: {d['nome']} → {d['decisao']} (score={d['score_medio']:.2f}, n={d['n']})")
    return decisoes

def resumo():
    dados     = _carregar()
    ativos    = [e for e in dados.get("experimentos",[]) if e.get("status")=="ativo"]
    aprovados = [e for e in dados.get("historico",[]) if e.get("decisao")=="consolidada"]
    rejeitados= [e for e in dados.get("historico",[]) if e.get("decisao")=="rejeitada"]
    return {"ativos": len(ativos), "aprovados": len(aprovados), "rejeitados": len(rejeitados),
            "experimentos_ativos": [{"nome": e["nome"], "n": len(e.get("interacoes",[]))} for e in ativos]}