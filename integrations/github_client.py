import os
import json
import base64
import requests
from dotenv import load_dotenv
load_dotenv()

from core.logger import info, warn, erro

GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
GITHUB_REPO    = "EDUARDOAPEX26/agente-autonomo"
GITHUB_FILE    = "memoria_chat.json"
GITHUB_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

def carregar_memoria_github() -> dict:
    if not GITHUB_TOKEN:
        warn("GITHUB", "Token não configurado — usando memória local")
        return None
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        r = requests.get(url, headers=GITHUB_HEADERS, timeout=8)
        if r.status_code == 200:
            conteudo = base64.b64decode(r.json()["content"]).decode("utf-8")
            dados = json.loads(conteudo)
            info("GITHUB", f"Memória carregada ({dados.get('total_conversas', 0)} conversas)")
            return dados
        warn("GITHUB", "Arquivo não encontrado — iniciando do zero")
        return None
    except Exception as e:
        erro("GITHUB", f"Erro ao carregar: {e}")
        return None

def salvar_memoria_github(memoria: dict):
    if not GITHUB_TOKEN:
        return
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        r = requests.get(url, headers=GITHUB_HEADERS, timeout=8)
        sha = r.json().get("sha", "") if r.status_code == 200 else ""
        conteudo = base64.b64encode(
            json.dumps(memoria, ensure_ascii=False, indent=2).encode("utf-8")
        ).decode("utf-8")
        payload = {
            "message": f"update memoria — {memoria.get('total_conversas', 0)} conversas",
            "content": conteudo,
        }
        if sha:
            payload["sha"] = sha
        r2 = requests.put(url, headers=GITHUB_HEADERS, json=payload, timeout=10)
        if r2.status_code in (200, 201):
            info("GITHUB", f"Memória sincronizada ({memoria.get('total_conversas', 0)} conversas)")
        else:
            erro("GITHUB", f"Erro ao salvar: {r2.status_code}")
    except Exception as e:
        erro("GITHUB", f"Erro ao sincronizar: {e}")