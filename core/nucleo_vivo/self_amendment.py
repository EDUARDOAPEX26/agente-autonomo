# core/nucleo_vivo/self_amendment.py
# Fase 35/36 — Auto-Amendment (Auto-Modificação)
# O núcleo pode propor mudanças em si mesmo de forma auditável e reversível.

import json
import os
import threading
from datetime import datetime
from core.logger import info, warn, debug

_AMENDMENTS_PATH = "livro_amendments.json"
_lock = threading.Lock()

# Limiares para propor mutação
_DOR_LIMIAR = 0.65
_PPD_LIMIAR = 0.60
_FRICCAO_LIMIAR = 3
_INTERVALO_MIN_H = 6

def _carregar():
    if not os.path.exists(_AMENDMENTS_PATH):
        return {"propostas": [], "aplicadas": [], "rejeitadas": []}
    try:
        with open(_AMENDMENTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"propostas": [], "aplicadas": [], "rejeitadas": []}

def _salvar(dados):
    try:
        with open(_AMENDMENTS_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("SELF_AMENDMENT", f"Erro ao salvar: {e}")

def _pode_propor():
    dados = _carregar()
    propostas = dados.get("propostas", [])
    if not propostas:
        return True
    ultima = propostas[-1].get("timestamp", "")
    if not ultima:
        return True
    try:
        dt = datetime.fromisoformat(ultima)
        horas = (datetime.now() - dt).total_seconds() / 3600
        if horas < _INTERVALO_MIN_H:
            debug("SELF_AMENDMENT", f"Intervalo mínimo não atingido ({horas:.1f}h)")
            return False
    except Exception:
        pass
    return True

def avaliar():
    """Avalia se deve propor uma mutação."""
    dor = 0.0
    ppd = 0.0
    regime = "equilibrio"
    friccoes = 0

    # Tenta ler dor do SovereignWill
    try:
        from core.nucleo_vivo.sovereign_will import SovereignWill
        sw = SovereignWill()
        dor = getattr(sw, "dor_acumulada", 0.0)
    except Exception:
        pass

    # Tenta ler PPD
    try:
        from core.ppd_tracker import calcular_ppd
        ppd = calcular_ppd()
    except Exception:
        pass

    # Tenta ler regime atual
    try:
        from core.nucleo_vivo.parliament_integration import parliament_integration
        regime = parliament_integration.ultimo_regime or "equilibrio"
    except Exception:
        pass

    # Tenta ler fricções críticas
    try:
        from core.friction_chamber import padroes_criticos
        friccoes = len(padroes_criticos(limiar=4))
    except Exception:
        pass

    estado = {
        "dor": round(dor, 2),
        "ppd": round(ppd, 2),
        "regime": regime,
        "friccoes": friccoes
    }

    deve_propor = (
        dor >= _DOR_LIMIAR or
        (ppd >= _PPD_LIMIAR and friccoes >= _FRICCAO_LIMIAR)
    )

    if deve_propor and not _pode_propor():
        deve_propor = False
        motivo = "Intervalo mínimo entre propostas não atingido"
    elif deve_propor:
        motivo = f"dor={dor:.2f} | ppd={ppd:.2f} | regime={regime} | friccoes={friccoes}"
    else:
        motivo = "Condições não atingidas"

    info("SELF_AMENDMENT", f"Avaliação: deve_propor={deve_propor} | {motivo}")
    return {"deve_propor": deve_propor, "motivo": motivo, "estado": estado}

def propor():
    """Gera uma proposta de mutação."""
    avaliacao = avaliar()
    if not avaliacao["deve_propor"]:
        return {}

    # Aqui você pode expandir com lógica mais sofisticada no futuro
    proposta = {
        "id": f"amendment_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "status": "pendente",
        "descricao": "Revisão geral dos pesos das facções ou princípios",
        "justificativa": f"Estado atual: {avaliacao['motivo']}",
        "estado_sistema": avaliacao["estado"]
    }

    with _lock:
        dados = _carregar()
        dados["propostas"].append(proposta)
        _salvar(dados)

    info("SELF_AMENDMENT", f"Proposta gerada: {proposta['id']}")
    return proposta

def listar_pendentes():
    dados = _carregar()
    return [p for p in dados.get("propostas", []) if p.get("status") == "pendente"]

def resumo():
    dados = _carregar()
    return {
        "pendentes": len([p for p in dados.get("propostas", []) if p.get("status") == "pendente"]),
        "aplicadas": len(dados.get("aplicadas", [])),
        "rejeitadas": len(dados.get("rejeitadas", [])),
    }

def processar(msg: str = "", resposta: str = ""):
    """Chamado pelo pipeline após cada interação."""
    try:
        r = resumo()
        if r["pendentes"] >= 3:
            debug("SELF_AMENDMENT", "Muitas propostas pendentes — aguardando aprovação")
            return
        avaliacao = avaliar()
        if avaliacao["deve_propor"]:
            propor()
    except Exception as e:
        debug("SELF_AMENDMENT", f"processar falhou: {e}")

# Instância global
self_amendment = None