import os
from datetime import datetime
from dotenv import load_dotenv
from core.logger import info, debug, erro, warn

# ── CARREGA O.env ───────────────────────────────────────────────────────────
load_dotenv()

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────

SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY")
SAMBANOVA_BASE_URL = os.getenv("SAMBANOVA_BASE_URL", "https://api.sambanova.ai/v1")
SAMBANOVA_MODEL = os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct") # único lugar

MAX_ERROS = 3

sambanova_status = {
    "disponivel": bool(SAMBANOVA_API_KEY),
    "ultima_verificacao": None,
    "erros_consecutivos": 0,
}

# ── CLIENTE ───────────────────────────────────────────────────────────────────

def get_sambanova_cliente():
    """Retorna cliente OpenAI-compatível apontando para SambaNova."""
    if not SAMBANOVA_API_KEY:
        raise ValueError("SAMBANOVA_API_KEY não configurada no.env")
    try:
        from openai import OpenAI
        return OpenAI(api_key=SAMBANOVA_API_KEY, base_url=SAMBANOVA_BASE_URL)
    except ImportError:
        erro("SAMBANOVA", "Biblioteca 'openai' não instalada. Execute: pip install openai")
        raise
    except Exception as e:
        erro("SAMBANOVA", f"Erro ao inicializar cliente: {e}")
        raise

# ── CONTROLE DE ERROS ─────────────────────────────────────────────────────────

def _registrar_erro(contexto: str, e: Exception):
    sambanova_status["erros_consecutivos"] += 1
    sambanova_status["ultima_verificacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    debug("SAMBANOVA", f"{contexto}: {e}")
    if sambanova_status["erros_consecutivos"] >= MAX_ERROS:
        sambanova_status["disponivel"] = False
        erro("SAMBANOVA", f"API desabilitada após {MAX_ERROS} erros consecutivos")

def _registrar_sucesso():
    sambanova_status["erros_consecutivos"] = 0
    sambanova_status["ultima_verificacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")

# ── FUNÇÕES PÚBLICAS ──────────────────────────────────────────────────────────

def testar_sambanova() -> bool:
    """Teste rápido de disponibilidade. Retorna True se OK."""
    if not SAMBANOVA_API_KEY:
        debug("SAMBANOVA", "API key não configurada")
        return False
    try:
        cliente = get_sambanova_cliente()
        r = cliente.chat.completions.create(
            model=SAMBANOVA_MODEL,
            messages=[{"role": "user", "content": "ok"}],
            max_tokens=1,
            temperature=0,
        )
        if r.choices:
            _registrar_sucesso()
            info("SAMBANOVA", "API disponível e respondendo")
            return True
    except Exception as e:
        _registrar_erro("Teste falhou", e)
    return False

def consultar_sambanova(pergunta: str, max_tokens: int = 3, temperature: float = 0) -> str:
    """
    Consulta rápida — ideal para decisões do Router (ex: 'Precisa de Tavily?').
    Retorna string vazia em caso de falha (sem exceção — compatível com o router).
    """
    if not sambanova_status["disponivel"]:
        debug("SAMBANOVA", "API desabilitada — pulando")
        return ""
    try:
        cliente = get_sambanova_cliente()
        r = cliente.chat.completions.create(
            model=SAMBANOVA_MODEL,
            messages=[{"role": "user", "content": pergunta}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if r.choices:
            texto = r.choices[0].message.content.strip()
            _registrar_sucesso()
            debug("SAMBANOVA", f"Router respondeu: {texto[:50]}")
            return texto
    except Exception as e:
        _registrar_erro("Consulta rápida falhou", e)
    return ""

def consultar_sambanova_chat(mensagens: list, max_tokens: int = 200, temperature: float = 0.3) -> tuple:
    """
    Chat completo com histórico — mesmo padrão de retorno do llm.py: (texto, "SAMBANOVA") ou (None, "ERRO").
    """
    if not sambanova_status["disponivel"]:
        debug("SAMBANOVA", "API desabilitada — pulando")
        return None, "ERRO"
    try:
        cliente = get_sambanova_cliente()
        r = cliente.chat.completions.create(
            model=SAMBANOVA_MODEL,
            messages=mensagens,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if r.choices:
            texto = r.choices[0].message.content.strip()
            _registrar_sucesso()
            info("SAMBANOVA", f"Chat respondido ({len(texto)} chars)")
            return texto, "SAMBANOVA"
    except Exception as e:
        _registrar_erro("Chat falhou", e)
    return None, "ERRO"

def reabilitar_sambanova():
    """Reabilita a API após período de desabilitação."""
    if SAMBANOVA_API_KEY:
        sambanova_status["disponivel"] = True
        sambanova_status["erros_consecutivos"] = 0
        info("SAMBANOVA", "API reabilitada para novas tentativas")
    else:
        warn("SAMBANOVA", "Não é possível reabilitar sem API key configurada")