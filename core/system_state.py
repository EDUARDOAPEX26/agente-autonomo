# core/system_state.py
import time

SYSTEM_STATE = {
    "modo": "normal",           # normal | degradado | critico
    "railway_falhas_consec": 0,
    "ultima_atualizacao": time.time()
}

def atualizar_estado(railway_ok: bool):
    """Atualiza modo baseado em falhas consecutivas do Railway"""
    if railway_ok:
        SYSTEM_STATE["railway_falhas_consec"] = 0
        if SYSTEM_STATE["modo"] != "critico":
            SYSTEM_STATE["modo"] = "normal"
    else:
        SYSTEM_STATE["railway_falhas_consec"] += 1
        if SYSTEM_STATE["railway_falhas_consec"] >= 3:
            SYSTEM_STATE["modo"] = "degradado"
        if SYSTEM_STATE["railway_falhas_consec"] >= 10:
            SYSTEM_STATE["modo"] = "critico"
    SYSTEM_STATE["ultima_atualizacao"] = time.time()

def pode_refletir() -> bool:
    """Só permite reflexão se não estivermos em modo degradado/crítico"""
    return SYSTEM_STATE["modo"] == "normal"