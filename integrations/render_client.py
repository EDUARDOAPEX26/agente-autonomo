"""
integrations/render_client.py
Cliente de integração com o agente Cerebras no Render.
Fallback do Railway — mesma interface do railway_client.
"""
import os
import time
import requests
from dotenv import load_dotenv
load_dotenv()
from core.logger import info, warn, erro

RENDER_URL = os.getenv("RENDER_URL", "https://agente-autonomo.onrender.com")

render_status = {
    "online":       False,
    "ultima_tarefa": "",
    "modelo":       "llama3.1-8b (Cerebras)",
}


def consultar_render() -> bool:
    """Verifica se o Render está online. Retorna True/False."""
    for tentativa in range(3):
        try:
            r = requests.get(f"{RENDER_URL}/", timeout=8)
            if r.status_code == 200:
                dados = r.json()
                render_status["online"] = True
                info("RENDER", f"Online — {dados.get('servidor', 'Cerebras')}")
                return True
        except Exception as e:
            warn("RENDER", f"Tentativa {tentativa+1}/3 falhou: {e}")
            if tentativa < 2:
                time.sleep(1)
    render_status["online"] = False
    warn("RENDER", "Offline após 3 tentativas")
    return False


def enviar_tarefa_render(mensagem: str, tarefa: str = "responder") -> dict | None:
    """
    Envia mensagem ao agente Cerebras no Render.
    Retorna dict com 'resultado' ou None se falhar.
    """
    try:
        r = requests.post(
            f"{RENDER_URL}/tarefa",
            json={"tarefa": tarefa, "dados": {"mensagem": mensagem}},
            timeout=30
        )
        if r.status_code == 200:
            dados = r.json()
            render_status["ultima_tarefa"] = mensagem[:60]
            info("RENDER", f"Resposta OK — {len(dados.get('resultado',''))} chars")
            return dados
    except Exception as e:
        erro("RENDER", f"Erro ao enviar tarefa: {e}")
    return None


def render_disponivel() -> bool:
    return render_status.get("online", False)