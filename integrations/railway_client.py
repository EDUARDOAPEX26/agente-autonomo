import os
import requests
from dotenv import load_dotenv
load_dotenv()
from core.logger import info, warn, erro
from core.system_state import atualizar_estado

# Render substituiu o Railway
RAILWAY_URL = os.getenv("RENDER_URL", "https://agente-autonomo.onrender.com")

railway_status = {"online": False, "ciclo": 0, "cpu": 0, "mem": 0, "objetivo": "", "ultima_tarefa": ""}

def consultar_railway():
    try:
        r = requests.get(f"{RAILWAY_URL}/status", timeout=8)
        if r.status_code == 200:
            dados = r.json()
            railway_status.update({
                "online":        True,
                "ciclo":         dados.get("ciclo", 0),
                "cpu":           dados.get("cpu", 0),
                "mem":           dados.get("mem", 0),
                "objetivo":      dados.get("objetivo", ""),
                "ultima_tarefa": dados.get("ultima_tarefa", ""),
                "tavily_uso":    dados.get("tavily_uso", 0),
            })
            info("RENDER", f"Online — Ciclo {dados.get('ciclo')} | CPU {dados.get('cpu')}% | Mem {dados.get('mem')}%")
            atualizar_estado(railway_ok=True)
            return
    except Exception as e:
        warn("RENDER", f"Offline: {e}")
    railway_status["online"] = False
    atualizar_estado(railway_ok=False)

def enviar_tarefa_railway(tarefa: str):
    try:
        r = requests.post(
            f"{RAILWAY_URL}/tarefa",
            json={"tarefa": tarefa, "dados": {}},
            timeout=10
        )
        if r.status_code == 200:
            dados = r.json()
            info("RENDER", f"Tarefa enviada: {tarefa} → {dados.get('status')}")
            return dados
    except Exception as e:
        erro("RENDER", f"Erro ao enviar tarefa: {e}")
    return None