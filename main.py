import threading
import requests
from dotenv import load_dotenv
load_dotenv()

from integrations.github_client import carregar_memoria_github, GITHUB_TOKEN
from integrations.tavily_client import carregar_controle, MAX_TAVILY
from integrations.railway_client import RAILWAY_URL
from integrations.groq_client import GROQ_KEYS
from core.memory import inicializar_memoria
from core.logger import info, warn, erro

# ── SANIDADE NO BOOT ──────────────────────────────────────────────────────────

def verificar_sanidade() -> dict:
    resultado = {
        "groq":      False,
        "github":    False,
        "render":    False,
        "tavily":    False,
        "sambanova": False,
        "serpapi":   False,
        "exa":       False,
    }

    try:
        from integrations.groq_client import GROQ_KEYS
        if GROQ_KEYS:
            resultado["groq"] = True
            info("SANIDADE", "GROQ OK")
        else:
            warn("SANIDADE", "GROQ sem chaves configuradas")
    except Exception as e:
        warn("SANIDADE", f"GROQ falhou: {e}")

    try:
        if GITHUB_TOKEN:
            r = requests.get(
                "https://api.github.com/repos/EDUARDOAPEX26/agente-autonomo",
                headers={"Authorization": f"token {GITHUB_TOKEN}"},
                timeout=6,
            )
            if r.status_code == 200:
                resultado["github"] = True
                info("SANIDADE", "GITHUB OK")
    except Exception as e:
        warn("SANIDADE", f"GITHUB falhou: {e}")

    try:
        r = requests.get(f"{RAILWAY_URL}/ping", timeout=15)
        if r.status_code == 200:
            resultado["render"] = True
            info("SANIDADE", "RENDER OK")
        else:
            warn("SANIDADE", f"RENDER respondeu {r.status_code}")
    except Exception as e:
        warn("SANIDADE", f"RENDER falhou: {e}")

    try:
        from integrations.tavily_client import tavily_disponivel
        if tavily_disponivel():
            resultado["tavily"] = True
            info("SANIDADE", "TAVILY OK")
    except Exception as e:
        warn("SANIDADE", f"TAVILY falhou: {e}")

    try:
        from integrations.sambanova_cliente import testar_sambanova
        if testar_sambanova():
            resultado["sambanova"] = True
            info("SANIDADE", "SAMBANOVA OK")
        else:
            warn("SANIDADE", "SAMBANOVA sem resposta")
    except Exception as e:
        warn("SANIDADE", f"SAMBANOVA falhou: {e}")

    try:
        import os
        serpapi_key = os.getenv("SERPAPI_KEY")
        if serpapi_key:
            resultado["serpapi"] = True
            info("SANIDADE", "SERPAPI OK")
        else:
            warn("SANIDADE", "SERPAPI sem chave")
    except Exception as e:
        warn("SANIDADE", f"SERPAPI falhou: {e}")

    try:
        from integrations.exa_client import testar_exa
        if testar_exa():
            resultado["exa"] = True
            info("SANIDADE", "EXA OK")
        else:
            warn("SANIDADE", "EXA sem resposta ou sem chave")
    except Exception as e:
        warn("SANIDADE", f"EXA falhou: {e}")

    return resultado


def resumo_sanidade(s: dict) -> str:
    icones = {True: "OK", False: "ERRO"}
    partes = [f"{icones[v]} {k.upper()}" for k, v in s.items()]
    return "Boot: " + " | ".join(partes)


# ── DESPERTADOR RENDER (a cada 14 min) ───────────────────────────────────────

def _despertador_render():
    import time
    while True:
        time.sleep(14 * 60)
        try:
            r = requests.get(f"{RAILWAY_URL}/ping", timeout=15)
            if r.status_code == 200:
                info("RENDER", "Ping keepalive OK")
            else:
                warn("RENDER", f"Ping keepalive {r.status_code}")
        except Exception as e:
            warn("RENDER", f"Ping keepalive falhou: {e}")


# ── INICIALIZACAO ─────────────────────────────────────────────────────────────

# FASE 41 — Restaura livros do GitHub antes de inicializar
try:
    from integrations.github_memory import restaurar_todos
    info("GITHUB_MEM", "Restaurando livros do GitHub...")
    threading.Thread(target=restaurar_todos, daemon=True).start()
except Exception as e:
    warn("GITHUB_MEM", f"Restauração falhou: {e}")

memoria = inicializar_memoria(carregar_memoria_github)
controle_inicial = carregar_controle()

info("INICIO", f"{memoria['total_conversas']} conversas anteriores")
info("INICIO", f"Tavily 1: {controle_inicial.get('tavily_1', 0)}/{MAX_TAVILY}")
info("INICIO", f"GitHub: {'configurado' if GITHUB_TOKEN else 'sem token'}")
info("INICIO", f"Render: {RAILWAY_URL}")
info("INICIO", f"Modelo: llama-3.3-70b-versatile ({len(GROQ_KEYS)} chaves)")

info("SANIDADE", "Verificando APIs...")
sanidade = verificar_sanidade()
info("SANIDADE", resumo_sanidade(sanidade))

# Inicia despertador em background
threading.Thread(target=_despertador_render, daemon=True).start()
info("RENDER", "Despertador iniciado — ping a cada 14 min")


# ── FUNCAO DE TAREFA ──────────────────────────────────────────────────────────

def adicionar_tarefa_local(nome_tarefa: str, dados: dict = None) -> dict:
    if dados is None:
        dados = {}
    try:
        payload = {"tarefa": nome_tarefa, "dados": dados}
        r = requests.post(f"{RAILWAY_URL}/tarefa", json=payload, timeout=10)
        if r.status_code == 200:
            info("TASK", f"Tarefa '{nome_tarefa}' enviada")
            return r.json()
        else:
            warn("TASK", f"Status {r.status_code}")
            return {"erro": f"status {r.status_code}"}
    except Exception as e:
        erro("TASK", str(e))
        return {"erro": str(e)}


# ── SHUTDOWN COM SINCRONIZAÇÃO ────────────────────────────────────────────────

def _shutdown_sincronizar():
    """Sincroniza livros com GitHub antes de fechar."""
    try:
        from integrations.github_memory import sincronizar_todos
        info("GITHUB_MEM", "Sincronizando livros antes de fechar...")
        sincronizar_todos()
        info("GITHUB_MEM", "Sincronização concluída.")
    except Exception as e:
        warn("GITHUB_MEM", f"Sincronização no shutdown falhou: {e}")


# ── UI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from ui.app import janela, chat, atualizar_status, atualizar_railway_async

    def _inserir_seguro(texto, tag=None):
        try:
            if chat.winfo_exists():
                if tag:
                    chat.insert("end", texto, tag)
                else:
                    chat.insert("end", texto)
        except Exception:
            pass

    def _on_fechar():
        """Chamado quando o usuário fecha a janela."""
        _shutdown_sincronizar()
        janela.destroy()

    if memoria["total_conversas"] > 0:
        _inserir_seguro(
            f"Memoria carregada: {memoria['total_conversas']} conversas\n\n",
            "buscando"
        )

    avisos = {
        "groq":      "GROQ indisponivel",
        "github":    "GitHub inacessivel",
        "render":    "Render offline",
        "tavily":    "Tavily esgotado",
        "sambanova": "SambaNova indisponivel",
        "serpapi":   "SerpAPI sem chave",
        "exa":       "EXA sem chave ou indisponivel",
    }
    for chave, msg in avisos.items():
        if not sanidade.get(chave):
            _inserir_seguro(f"! {msg}\n", "pensando")

    if all(sanidade.values()):
        _inserir_seguro("Todas APIs OK\n\n", "buscando")

    atualizar_status()
    threading.Thread(target=atualizar_railway_async, daemon=True).start()

    # Registra o shutdown ao fechar a janela
    janela.protocol("WM_DELETE_WINDOW", _on_fechar)

    janela.mainloop()