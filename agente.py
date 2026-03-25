"""
AGENTE AUTÔNOMO — Railway Cloud Agent v4.1
Fases implementadas: 1 (graceful shutdown), 11 (memória negativa), 12 (resumo por importância)
TF-IDF nativo no endpoint /buscar
"""

import time
import random
import psutil
import requests
import json
import os
import base64
import threading
import math
import uuid
import signal
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

# ── LOG ESTRUTURADO ────────────────────────────────────────────────────────────
def log(modulo: str, msg: str, nivel: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}][{nivel}][{modulo}] {msg}", flush=True)

def warn(modulo: str, msg: str): log(modulo, msg, "WARN")
def erro(modulo: str, msg: str): log(modulo, msg, "ERRO")
def debug(modulo: str, msg: str): log(modulo, msg, "DEBUG")

# ── CHAVES E CONFIG ────────────────────────────────────────────────────────────
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
GITHUB_REPO    = "EDUARDOAPEX26/agente-autonomo"
GITHUB_FILE    = "memoria_chat.json"
GITHUB_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

GROQ_KEY_1   = os.getenv("GROQ_API_KEY")
GROQ_KEY_2   = os.getenv("GROQ_API_KEY_2")
GOOGLE_KEY   = os.getenv("GOOGLE_API_KEY") or os.getenv("CHAVE_API_DO_GOOGLE")
CEREBRAS_KEY = os.getenv("CEREBRAS_API_KEY")
MODELO_GROQ  = "llama-3.1-8b-instant"
MODELO_GEM   = "gemini-2.0-flash"

MAX_TAVILY       = 10
RESET_HORAS      = 24
CONTROLE_FILE    = "controle.json"
SYNC_A_CADA      = 10
MAX_LOG_LINHAS   = 2000
LOG_REDUCAO      = 1000

# ── FASE 1: GRACEFUL SHUTDOWN ──────────────────────────────────────────────────
_encerrando = {"v": False}

def _handle_shutdown(sig, frame):
    if _encerrando["v"]:
        return
    _encerrando["v"] = True
    log("SHUTDOWN", f"Signal {sig} recebido — sincronizando...")
    mem = get_memoria_compartilhada()
    salvar_memoria_github(mem)
    log("SHUTDOWN", "Sync concluído")

signal.signal(signal.SIGINT,  _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)

# ── FASTAPI ────────────────────────────────────────────────────────────────────
app = FastAPI()

estado = {
    "ciclo":         0,
    "objetivo":      "iniciando",
    "cpu":           0.0,
    "mem":           0.0,
    "ultima_tarefa": "",
    "online":        True,
}

class TarefaPayload(BaseModel):
    tarefa:  str
    dados:   dict = {}

@app.get("/ping")
def ping():
    return {"pong": True}

@app.get("/status")
def status():
    controle = carregar_controle()
    livro_l  = _carregar_livro_local("licoes")
    resumo   = _carregar_livro_local("resumo")
    return {
        "ciclo":                estado["ciclo"],
        "objetivo":             estado["objetivo"],
        "cpu":                  estado["cpu"],
        "mem":                  estado["mem"],
        "ultima_tarefa":        estado["ultima_tarefa"],
        "tavily_uso":           controle.get("tavily_uso", 0),
        "tavily_max":           MAX_TAVILY,
        "online":               True,
        "timestamp":            datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "total_licoes":         len(livro_l.get("licoes", [])),
        "resumo_ultima_geracao": resumo.get("meta", {}).get("ultima_geracao", "nunca"),
    }

@app.get("/memoria")
def get_memoria_endpoint():
    try:
        with open("memoria.txt", "r", encoding="utf-8") as f:
            linhas = f.readlines()[-50:]
        entradas = []
        for linha in linhas:
            try:
                entradas.append(json.loads(linha))
            except:
                entradas.append({"raw": linha.strip()})
        mem = get_memoria_compartilhada()
        return {
            "total_log":       len(linhas),
            "ultimas":         entradas,
            "total_conversas": mem.get("total_conversas", 0),
            "total_tarefas":   mem.get("total_tarefas", 0),
        }
    except:
        return {"total_log": 0, "ultimas": []}

@app.post("/tarefa")
def executar_tarefa_endpoint(payload: TarefaPayload):
    tarefa = payload.tarefa
    dados  = payload.dados

    if tarefa == "registrar_licao":
        msg_usuario   = dados.get("mensagem_usuario", "")
        ultima_resp   = dados.get("ultima_resposta", "")
        if msg_usuario:
            licao = _extrair_licao_via_llm(msg_usuario, ultima_resp)
            if licao:
                registrar_licao(licao["gatilho"], ultima_resp, licao)
                return {"status": "ok", "licao_registrada": True, "gatilho": licao["gatilho"]}
        return {"status": "ok", "licao_registrada": False}

    if tarefa == "buscar_licoes":
        pergunta  = dados.get("pergunta", "")
        licoes    = buscar_licoes_relevantes(pergunta)
        instrucao = formatar_licoes_para_prompt(licoes)
        return {"status": "ok", "instrucao
