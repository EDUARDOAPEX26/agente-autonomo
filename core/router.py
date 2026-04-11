import re
import unicodedata
import threading
from core.logger import info, warn

def normalizar(texto: str) -> str:
    t = texto.lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t

CACHE_DECISAO = {}
lock_cache = threading.Lock()

def _exa_disponivel():
    try:
        from integrations.exa_client import exa_disponivel
        return exa_disponivel()
    except:
        return False

# ── FASE 16-A: PERGUNTAS INTERNAS — nunca acionar busca web ──────────────────
# "fase 12", "erro 500", "3 chaves", "quantas apis" são perguntas do sistema
_PADROES_INTERNOS = [
    r"\bfase \d+\b",
    r"\berro \d+\b",
    r"\bv\d+\.\d+\b",
    r"\bversao \d+\b",
    r"\bversão \d+\b",
    r"quantas? (api|chave|model|livro|fase)",
    r"qual (model|api|chave|fase|livro)",
    r"como funciona (sua|o|a)\b",
    r"o que (e|é) a fase",
    r"quais livros",
    r"quem te criou",
    r"quantas chaves",
]

PALAVRAS_BLOQUEIO = [
    "explique", "como fazer", "crie", "gere", "codigo", "piada", "historia",
    "ola", "oi", "tudo bem", "obrigado", "valeu", "ok", "certo",
    "voce e", "quem e voce", "me ajuda", "pode me",
]

PALAVRAS_BUSCA = [
    "hoje", "agora", "atual", "recente", "ultima", "novo", "novidade",
    "noticia", "noticias", "cotacao", "preco", "valor", "dolar", "bitcoin",
    "clima", "temperatura", "resultado", "placar", "jogo", "partida",
    "guerra", "conflito", "eleicao", "presidente", "governo",
    "hackathon", "evento", "lancamento", "versao",
    "taxa", "juros", "selic", "ibovespa", "bolsa",
    # merchant: compra/preco em loja
    "custa", "custo", "comprar", "frete", "desconto", "oferta",
    "disponivel", "estoque", "entrega",
]

# Padrao generico merchant: "custa/vale/preco na/no [loja]"
_PADRAO_MERCHANT = re.compile(
    r"(custa|vale|custo|frete|desconto|comprar|disponivel|estoque)"
)

def precisa_busca_web(pergunta: str, get_groq_cliente=None, google_cliente=None) -> tuple[bool, str]:
    """
    Router — EXA prioridade, Tavily fallback.
    Fase 16-A: bloqueia perguntas internas com regex antes de checar PALAVRAS_BUSCA.
    """
    p = normalizar(pergunta)

    with lock_cache:
        if p in CACHE_DECISAO:
            return CACHE_DECISAO[p]

    # ── FASE 16-A: bloqueia perguntas internas ────────────────────────────────
    for padrao in _PADROES_INTERNOS:
        if re.search(padrao, p):
            info("ROUTER", f"Pergunta interna bloqueada: {pergunta[:60]}")
            with lock_cache:
                CACHE_DECISAO[p] = (False, "")
            return False, ""

    # Bloqueia saudações — usa palavra inteira para evitar match parcial
    # Ex: "oi" dentro de "bitcoin" não deve ser bloqueado
    p_espacado = f" {p} "
    if any(f" {x} " in p_espacado for x in PALAVRAS_BLOQUEIO):
        with lock_cache:
            CACHE_DECISAO[p] = (False, "")
        return False, ""

    # Pergunta muito curta — provavelmente saudação ou comando simples
    if len(pergunta.strip()) < 15:
        with lock_cache:
            CACHE_DECISAO[p] = (False, "")
        return False, ""

    # Verifica se tem palavra que indica dado atual
    precisa = any(x in p for x in PALAVRAS_BUSCA)

    if not precisa:
        with lock_cache:
            CACHE_DECISAO[p] = (False, "")
        return False, ""

    # Precisa buscar — EXA primeiro, Tavily fallback
    if _exa_disponivel():
        info("ROUTER", f"EXA — {pergunta[:60]}")
        with lock_cache:
            CACHE_DECISAO[p] = (True, "exa")
        return True, "exa"

    warn("ROUTER", "EXA indisponivel — Tavily")
    with lock_cache:
        CACHE_DECISAO[p] = (True, "tavily")
    return True, "tavily"


# Compatibilidade com código antigo
def precisa_tavily(pergunta: str, get_groq_cliente=None, google_cliente=None) -> bool:
    precisa, _ = precisa_busca_web(pergunta, get_groq_cliente, google_cliente)
    return precisa


def pergunta_sobre_railway(pergunta: str) -> bool:
    """
    Fase 16-A: só dispara para comandos reais do Railway.
    Não captura qualquer frase com 'api' ou 'status'.
    """
    if not pergunta:
        return False
    p = normalizar(pergunta)
    # Termos específicos do Railway — lista restrita
    termos_railway = [
        "railway status", "status do agente", "agente nuvem",
        "agente em nuvem", "resumir_agora", "buscar_licoes",
        "status_resumo", "ciclo do agente", "cpu do agente",
        "memoria do agente", "deploy",
    ]
    return any(x in p for x in termos_railway)


def limpar_resposta(texto: str) -> str:
    if not texto:
        return ""
    texto = texto.strip()
    texto = "\n".join(l for l in texto.splitlines() if l.strip())
    return texto