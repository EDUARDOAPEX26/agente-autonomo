"""
ui/app.py — Agente Autônomo v5.1 / Fase 16

Melhorias sobre v5.0:
  • MAX_LLM_CALLS: teto de 2 chamadas LLM por janela de 60 s (barreira extra)
  • Label de budget LLM visível na interface
  • lock_railway separado do lock_router (sem deadlock)
  • UI mais limpa: fundo branco, cores consistentes
  • Todos os recursos preservados: memory/books sync, Railway bypass,
    Tavily, GitHub, graceful shutdown
"""

import tkinter as tk
from tkinter import scrolledtext
import threading
import time
import signal
import sys

from core.logger   import info, warn, erro
from core.pipeline import executar_pipeline
from core.memory   import get_memoria, salvar_memoria, contexto_memoria, resumir_conversa
from core.books    import _cache_livros, _sync_contador, salvar_livro_github
from core.llm      import status_apis
from integrations.github_client import GITHUB_TOKEN
from integrations.tavily_client import carregar_controle, MAX_TAVILY
from integrations.railway_client import (
    consultar_railway, enviar_tarefa_railway, railway_status
)

# ── ESTADO GLOBAL ─────────────────────────────────────────────────────────────

APP_ATIVO    = True
lock_router  = threading.Lock()
lock_railway = threading.Lock()

# ── BUDGET LLM ────────────────────────────────────────────────────────────────

MAX_LLM_CALLS   = 2
_llm_count      = 0
_llm_janela_ini = time.time()
_LLM_SEG        = 60


def _budget_ok() -> bool:
    global _llm_count, _llm_janela_ini
    agora = time.time()
    if agora - _llm_janela_ini > _LLM_SEG:
        _llm_count      = 0
        _llm_janela_ini = agora
    if _llm_count >= MAX_LLM_CALLS:
        warn("BUDGET", f"Teto LLM atingido ({MAX_LLM_CALLS}/{_LLM_SEG}s)")
        return False
    return True


def _registrar_llm():
    global _llm_count
    _llm_count += 1
    info("BUDGET", f"LLM calls na janela: {_llm_count}/{MAX_LLM_CALLS}")


def _restantes() -> int:
    agora = time.time()
    if agora - _llm_janela_ini > _LLM_SEG:
        return MAX_LLM_CALLS
    return max(0, MAX_LLM_CALLS - _llm_count)


# ── SAFE UI ───────────────────────────────────────────────────────────────────

def safe_ui(callback):
    try:
        if APP_ATIVO and janela.winfo_exists():
            janela.after(0, callback)
    except Exception:
        pass


# ── GRACEFUL SHUTDOWN ─────────────────────────────────────────────────────────

def sincronizar_tudo():
    from integrations.github_client import salvar_memoria_github
    memoria = get_memoria()
    if memoria:
        info("SHUTDOWN", "Sincronizando memória...")
        try:
            salvar_memoria_github(memoria)
        except Exception as e:
            erro("SHUTDOWN", f"Erro memória: {e}")
    for assunto, livro in list(_cache_livros.items()):
        if _sync_contador.get(assunto, 0) > 0:
            try:
                salvar_livro_github(livro)
                info("SHUTDOWN", f"Livro '{assunto}' sync OK")
            except Exception as e:
                erro("SHUTDOWN", f"Erro livro '{assunto}': {e}")
    info("SHUTDOWN", "Sync concluído")


def ao_fechar_janela():
    global APP_ATIVO
    APP_ATIVO = False
    sincronizar_tudo()
    try:
        if janela.winfo_exists():
            janela.destroy()
    except Exception as e:
        warn("SHUTDOWN", str(e))


def handler_signal(signum, frame):
    info("SHUTDOWN", f"Signal {signum}")
    ao_fechar_janela()
    sys.exit(0)


# ── STATUS ────────────────────────────────────────────────────────────────────

def atualizar_status():
    try:
        if not janela.winfo_exists():
            return

        memoria  = get_memoria()
        controle = carregar_controle()
        tv1 = controle.get("tavily_1", 0)
        tv2 = controle.get("tavily_2", 0)
        tv3 = controle.get("tavily_3", 0)
        gh_ok = "OK" if GITHUB_TOKEN else "SEM TOKEN"

        if railway_status["online"]:
            rw_txt = f"☁ ON | ciclo {railway_status['ciclo']} | CPU {railway_status['cpu']}%"
            rw_cor = "#0A6EC7"
        else:
            rw_txt = "☁ RAILWAY offline"
            rw_cor = "#DC2626"

        label_railway.config(text=rw_txt, fg=rw_cor)

        s = " | ".join(
            f"{n.upper()}:{'OK' if v['ativa'] else 'ERR'}"
            for n, v in status_apis.items()
        )
        label_status.config(
            text=(
                f"GH:{gh_ok} | "
                f"TV1:{tv1}/{MAX_TAVILY} TV2:{tv2}/{MAX_TAVILY} TV3:{tv3}/{MAX_TAVILY} | "
                f"{s} | Conv:{memoria['total_conversas']}"
            )
        )

        r = _restantes()
        cor_b = "#1D9E75" if r > 0 else "#DC2626"
        label_budget.config(text=f"LLM: {r} rest.", fg=cor_b)

    except Exception:
        pass


def atualizar_railway_async():
    while APP_ATIVO:
        try:
            if not janela.winfo_exists():
                break
            with lock_railway:
                consultar_railway()
            safe_ui(atualizar_status)
        except Exception as e:
            warn("THREAD", f"Railway: {e}")
            break
        for _ in range(60):
            if not APP_ATIVO:
                break
            time.sleep(1)


# ── UI HELPERS ────────────────────────────────────────────────────────────────

def _chat_insert(texto, tag=None):
    try:
        if not chat.winfo_exists():
            return
        chat.config(state=tk.NORMAL)
        if tag:
            chat.insert(tk.END, texto, tag)
        else:
            chat.insert(tk.END, texto)
        chat.see(tk.END)
        chat.config(state=tk.DISABLED)
    except Exception:
        pass


def _finalizar(resposta, api_usada):
    try:
        if not chat.winfo_exists():
            return

        if api_usada in ("groq", "google", "sambanova", "huggingface"):
            _registrar_llm()

        chat.config(state=tk.NORMAL)
        chat.delete("end-2l", "end-1l")
        chat.insert(tk.END, "Agente: ", "prefixo")
        chat.insert(tk.END, f"{resposta}", "resposta")
        sufixo = f"  [{api_usada}]\n\n" if api_usada not in ("groq", "google") else "\n\n"
        chat.insert(tk.END, sufixo, "api_tag")
        chat.see(tk.END)
        chat.config(state=tk.DISABLED)

        botao.config(state=tk.NORMAL)
        entrada.config(state=tk.NORMAL)
        entrada.focus()
        atualizar_status()

    except Exception:
        pass


# ── ENVIO ─────────────────────────────────────────────────────────────────────

def enviar(event=None):
    msg = entrada.get().strip()
    if not msg:
        return "break"

    entrada.delete(0, tk.END)
    botao.config(state=tk.DISABLED)
    entrada.config(state=tk.DISABLED)

    _chat_insert(f"Você: {msg}\n", "usuario")
    _chat_insert("Processando...\n", "pensando")

    threading.Thread(target=_processar, args=(msg,), daemon=True).start()
    return "break"


# ── PROCESSAMENTO ─────────────────────────────────────────────────────────────

def _processar(msg):
    with lock_router:
        try:
            # Railway bypass
            if msg.lower().startswith("railway "):
                tarefa = msg[8:].strip()
                safe_ui(lambda: _chat_insert("☁ Enviando ao Railway...\n", "buscando"))
                with lock_railway:
                    if not railway_status["online"]:
                        consultar_railway()
                if railway_status["online"]:
                    resultado = enviar_tarefa_railway(tarefa)
                    if resultado and resultado.get("status") == "ok":
                        retorno  = resultado.get("resultado", "")
                        resposta = retorno if retorno else f"Tarefa '{tarefa}' executada."
                    else:
                        resposta = "Railway recebeu mas houve problema."
                else:
                    resposta = "Railway offline no momento."
                safe_ui(lambda: _finalizar(resposta, "RAILWAY"))
                return

            # Aviso de budget (não bloqueia — pipeline decide internamente)
            if not _budget_ok():
                safe_ui(lambda: _chat_insert(
                    "⚠ Budget LLM atingido — priorizando cache/heurística.\n", "aviso"
                ))

            # Pipeline central
            resposta, api_usada = executar_pipeline(msg)
            safe_ui(lambda: _finalizar(resposta, api_usada))

        except Exception as e:
            erro("PIPELINE", str(e))
            safe_ui(lambda: _finalizar("Erro ao processar. Tente novamente.", "SISTEMA"))


# ── JANELA ────────────────────────────────────────────────────────────────────

janela = tk.Tk()
janela.title("Agente Autônomo v5.1 — Fase 16")
janela.geometry("720x720")
janela.configure(bg="#FFFFFF")
janela.minsize(500, 450)

# Barra de status (topo)
frame_status = tk.Frame(janela, bg="#F3F4F6", pady=4, padx=10)
frame_status.pack(fill=tk.X)

label_railway = tk.Label(
    frame_status, text="☁ RAILWAY: conectando...",
    fg="#888888", bg="#F3F4F6", font=("Segoe UI", 9)
)
label_railway.pack(side=tk.LEFT)

label_budget = tk.Label(
    frame_status, text=f"LLM: {MAX_LLM_CALLS} rest.",
    fg="#1D9E75", bg="#F3F4F6", font=("Segoe UI", 9, "bold")
)
label_budget.pack(side=tk.RIGHT)

label_status = tk.Label(
    frame_status, text="",
    fg="#555555", bg="#F3F4F6", font=("Segoe UI", 8)
)
label_status.pack(side=tk.LEFT, padx=12)

tk.Frame(janela, bg="#E5E7EB", height=1).pack(fill=tk.X)

# Chat
chat = scrolledtext.ScrolledText(
    janela,
    wrap=tk.WORD,
    font=("Segoe UI", 11),
    bg="#F9FAFB",
    fg="#1A1A1A",
    relief=tk.FLAT,
    bd=0,
    padx=12,
    pady=8,
    state=tk.DISABLED,
    cursor="arrow",
)
chat.pack(padx=8, pady=(6, 0), fill=tk.BOTH, expand=True)

chat.tag_config("usuario",  foreground="#0A6EC7", font=("Segoe UI", 11, "bold"))
chat.tag_config("prefixo",  foreground="#1A1A1A", font=("Segoe UI", 11, "bold"))
chat.tag_config("resposta", foreground="#1A1A1A", font=("Segoe UI", 11))
chat.tag_config("api_tag",  foreground="#AAAAAA", font=("Segoe UI", 9))
chat.tag_config("pensando", foreground="#AAAAAA", font=("Segoe UI", 10, "italic"))
chat.tag_config("buscando", foreground="#0A6EC7", font=("Segoe UI", 10, "italic"))
chat.tag_config("aviso",    foreground="#D97706", font=("Segoe UI", 10, "italic"))

tk.Frame(janela, bg="#E5E7EB", height=1).pack(fill=tk.X, padx=8, pady=(4, 0))

# Entrada
frame_input = tk.Frame(janela, bg="#FFFFFF", pady=8, padx=8)
frame_input.pack(fill=tk.X)

entrada = tk.Entry(
    frame_input,
    font=("Segoe UI", 11),
    bg="#FFFFFF",
    fg="#1A1A1A",
    relief=tk.FLAT,
    bd=1,
    highlightthickness=1,
    highlightbackground="#D1D5DB",
    highlightcolor="#0A6EC7",
    insertbackground="#1A1A1A",
)
entrada.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 8))
entrada.bind("<Return>",   enviar)
entrada.bind("<KP_Enter>", enviar)
entrada.focus()

botao = tk.Button(
    frame_input,
    text="Enviar",
    command=enviar,
    font=("Segoe UI", 10),
    bg="#0A6EC7",
    fg="#FFFFFF",
    activebackground="#0856A0",
    activeforeground="#FFFFFF",
    relief=tk.FLAT,
    padx=14,
    pady=6,
    cursor="hand2",
    bd=0,
)
botao.pack(side=tk.RIGHT)

# Init
janela.protocol("WM_DELETE_WINDOW", ao_fechar_janela)
signal.signal(signal.SIGINT,  handler_signal)
signal.signal(signal.SIGTERM, handler_signal)

threading.Thread(target=atualizar_railway_async, daemon=True).start()

_chat_insert("Agente pronto. Digite sua mensagem abaixo.\n", "api_tag")

janela.mainloop()