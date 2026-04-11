import os
import json
import time
import re
import requests
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from core.logger import info, warn, erro, debug

CONTROLE_FILE = "controle.json"
MAX_TAVILY    = 10
RESET_HORAS   = 24
SERPAPI_KEY   = os.getenv("SERPAPI_KEY")

# ── POOL DE TAVILY ────────────────────────────────────────
try:
    from tavily import TavilyClient
    TAVILY_KEYS = [k for k in [
        os.getenv("TAVILY_API_KEY"),
        os.getenv("TAVILY_API_KEY_2"),
        os.getenv("TAVILY_API_KEY_3"),
    ] if k]
    tavily_clientes = [TavilyClient(api_key=k) for k in TAVILY_KEYS]
    info("TAVILY", f"{len(tavily_clientes)} chave(s) configurada(s)")
except Exception as e:
    tavily_clientes = []
    erro("TAVILY", f"Erro ao inicializar: {e}")

info("SERPAPI", "Configurado" if bool(SERPAPI_KEY) else "Sem chave")

# ── CONTROLE DIÁRIO ───────────────────────────────────────
def carregar_controle() -> dict:
    try:
        with open(CONTROLE_FILE, "r") as f:
            dados = json.load(f)
        agora = time.time()
        ultimo_reset = dados.get("timestamp", 0)
        if agora - ultimo_reset > RESET_HORAS * 3600:
            info("CONTROLE", "24h passadas — resetando contadores Tavily")
            dados = {
                "tavily_1":  0,
                "tavily_2":  0,
                "tavily_3":  0,
                "timestamp": agora,
                "data":      datetime.now().strftime("%Y-%m-%d")
            }
            with open(CONTROLE_FILE, "w") as f:
                json.dump(dados, f, indent=2)
        return dados
    except (FileNotFoundError, json.JSONDecodeError):
        dados = {
            "tavily_1":  0,
            "tavily_2":  0,
            "tavily_3":  0,
            "timestamp": time.time(),
            "data":      datetime.now().strftime("%Y-%m-%d")
        }
        salvar_controle(dados)
        return dados

def salvar_controle(dados: dict):
    try:
        with open(CONTROLE_FILE, "w") as f:
            json.dump(dados, f, indent=2)
    except Exception as e:
        erro("CONTROLE", f"Erro ao salvar: {e}")

def get_tavily_disponivel():
    if not tavily_clientes:
        return None, None
    dados = carregar_controle()
    for i, chave in enumerate(["tavily_1", "tavily_2", "tavily_3"]):
        if i >= len(tavily_clientes):
            break
        if dados.get(chave, 0) < MAX_TAVILY:
            return tavily_clientes[i], chave
    warn("TAVILY", "Todas as chaves atingiram o limite diário!")
    return None, None

def registrar_uso_tavily(chave: str):
    dados = carregar_controle()
    dados[chave] = dados.get(chave, 0) + 1
    salvar_controle(dados)
    num = int(chave.split("_")[1])
    info("TAVILY", f"Chave {num} — Uso {dados[chave]}/{MAX_TAVILY} hoje")

def tavily_disponivel() -> bool:
    cliente, _ = get_tavily_disponivel()
    return cliente is not None or bool(SERPAPI_KEY)

# ── CACHE ─────────────────────────────────────────────────
CACHE_TAVILY = {}
MAX_CACHE    = 500

def _limpar_cache():
    while len(CACHE_TAVILY) > MAX_CACHE:
        CACHE_TAVILY.pop(next(iter(CACHE_TAVILY)))

# ── EXTRAÇÃO DE KEYWORDS ──────────────────────────────────
def extrair_query_busca(texto: str, max_chars: int = 300) -> str:
    texto = re.sub(r'[^\w\s]', ' ', texto)
    palavras = texto.split()
    keywords = []
    total = 0
    for p in palavras:
        if len(p) < 3:
            continue
        if total + len(p) > max_chars:
            break
        keywords.append(p)
        total += len(p) + 1
    return " ".join(keywords[:15])

# ── BUSCA ─────────────────────────────────────────────────
def buscar_serpapi(query: str) -> str:
    if not bool(SERPAPI_KEY):
        return ""
    try:
        info("SERPAPI", f"Buscando: {query}")
        r = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "api_key": SERPAPI_KEY, "num": 3},
            timeout=10
        )
        data = r.json()
        if "organic_results" in data:
            partes = [
                item.get("snippet", "")
                for item in data["organic_results"][:3]
                if item.get("snippet")
            ]
            resposta = " ".join(partes)[:400]
            info("SERPAPI", f"OK ({len(resposta)} chars)")
            return resposta
        return ""
    except Exception as e:
        erro("SERPAPI", f"Erro: {e}")
        return ""

def buscar_online(query: str) -> str:
    query = extrair_query_busca(query)
    agora = time.time()
    _limpar_cache()

    if query in CACHE_TAVILY:
        if agora - CACHE_TAVILY[query]["t"] < 600:
            debug("TAVILY", f"Cache hit: {query}")
            return CACHE_TAVILY[query]["r"]

    cliente, chave = get_tavily_disponivel()
    if cliente:
        try:
            info("TAVILY", f"Buscando ({chave}): {query}")
            resultado = cliente.search(
                query=query,
                max_results=2,
                search_depth="basic",
                include_answer=True
            )
            resposta = resultado.get("answer", "")
            if not resposta:
                partes = [
                    r.get("content", "")[:200]
                    for r in resultado.get("results", [])
                    if r.get("content", "")
                ]
                resposta = " ".join(partes)[:400]
            if resposta and len(resposta.strip()) >= 20:
                registrar_uso_tavily(chave)
                CACHE_TAVILY[query] = {"r": resposta, "t": agora}
                info("TAVILY", f"OK ({len(resposta)} chars)")
                return resposta
        except Exception as e:
            erro("TAVILY", f"Erro: {e}")

    info("TAVILY", "Indisponivel — tentando SerpAPI...")
    resposta = buscar_serpapi(query)
    if resposta:
        CACHE_TAVILY[query] = {"r": resposta, "t": agora}
    return resposta