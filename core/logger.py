import os
import json
import threading
from datetime import datetime

# ── NÍVEIS ────────────────────────────────────────────────
DEBUG = 10
INFO  = 20
WARN  = 30
ERROR = 40

NIVEL_NOMES = {DEBUG: "DEBUG", INFO: "INFO", WARN: "WARN", ERROR: "ERROR"}

# ── CONFIGURAÇÃO ──────────────────────────────────────────
NIVEL_MINIMO  = INFO        # Muda para DEBUG para ver tudo
LOG_FILE      = "agente.log"
MAX_LOG_LINES = 500         # Rotação automática
_lock         = threading.Lock()

# Módulos que podem ser silenciados individualmente
MODULOS_ATIVOS = {
    "CHAT":       True,
    "ROUTER":     True,
    "MEMORY":     True,
    "LIVRO":      True,
    "LLM":        True,
    "GROQ":       True,
    "GOOGLE":     True,
    "TAVILY":     True,
    "SERPAPI":    True,
    "CONTROLE":   True,
    "GITHUB":     True,
    "RAILWAY":    True,
    "INICIO":     True,
    "API":        True,
    "AVISO":      True,
    "ERRO":       True,
}

# ── FUNÇÃO PRINCIPAL ──────────────────────────────────────
def log(modulo: str, mensagem: str, nivel: int = INFO):
    if nivel < NIVEL_MINIMO:
        return
    if not MODULOS_ATIVOS.get(modulo, True):
        return

    agora    = datetime.now().strftime("%H:%M:%S")
    nivel_str = NIVEL_NOMES.get(nivel, "INFO")
    linha    = f"[{agora}][{nivel_str}][{modulo}] {mensagem}"

    with _lock:
        print(linha)
        _salvar_log(linha)

def _salvar_log(linha: str):
    try:
        # Lê linhas existentes
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                linhas = f.readlines()
        except FileNotFoundError:
            linhas = []

        # Rotação: mantém só as últimas MAX_LOG_LINES
        if len(linhas) >= MAX_LOG_LINES:
            linhas = linhas[-(MAX_LOG_LINES - 1):]

        linhas.append(linha + "\n")

        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(linhas)
    except Exception:
        pass  # log nunca deve quebrar o sistema

# ── ATALHOS POR NÍVEL ─────────────────────────────────────
def debug(modulo: str, mensagem: str):
    log(modulo, mensagem, DEBUG)

def info(modulo: str, mensagem: str):
    log(modulo, mensagem, INFO)

def warn(modulo: str, mensagem: str):
    log(modulo, mensagem, WARN)

def erro(modulo: str, mensagem: str):
    log(modulo, mensagem, ERROR)

# ── UTILITÁRIO: silenciar módulo ──────────────────────────
def silenciar(modulo: str):
    MODULOS_ATIVOS[modulo] = False

def ativar(modulo: str):
    MODULOS_ATIVOS[modulo] = True