"""
AGENTE AUTÔNOMO — Railway Cloud Agent v4.2
Fases implementadas: 1 (graceful shutdown), 11 (memória negativa), 12 (resumo por importância)
TF-IDF nativo no endpoint /buscar
v4.2: EXA como fallback do Tavily + HuggingFace como fallback de LLM
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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "EDUARDOAPEX26/agente-autonomo"
GITHUB_FILE = "memoria_chat.json"
GITHUB_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

GROQ_KEY_1 = os.getenv("GROQ_API_KEY")
GROQ_KEY_2 = os.getenv("GROQ_API_KEY_2")
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("CHAVE_API_DO_GOOGLE")
CEREBRAS_KEY = os.getenv("CEREBRAS_API_KEY")
HUGGING_KEY = os.getenv("HUGGING_API_KEY")
EXA_KEY = os.getenv("EXA_API_KEY")

MODELO_GROQ = "llama-3.1-8b-instant"
MODELO_GEM = "gemini-2.0-flash"

MAX_TAVILY = 10
RESET_HORAS = 24
CONTROLE_FILE = "controle.json"
SYNC_A_CADA = 10
MAX_LOG_LINHAS = 2000
LOG_REDUCAO = 1000

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

signal.signal(signal.SIGINT, _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)

# ── FASTAPI ────────────────────────────────────────────────────────────────────
app = FastAPI()

estado = {
    "ciclo": 0,
    "objetivo": "iniciando",
    "cpu": 0.0,
    "mem": 0.0,
    "ultima_tarefa": "",
    "online": True,
}

class TarefaPayload(BaseModel):
    tarefa: str
    dados: dict = {}

@app.get("/ping")
def ping():
    return {"pong": True}

@app.get("/status")
def status():
    controle = carregar_controle()
    livro_l = _carregar_livro_local("licoes")
    resumo = _carregar_livro_local("resumo")
    return {
        "ciclo": estado["ciclo"],
        "objetivo": estado["objetivo"],
        "cpu": estado["cpu"],
        "mem": estado["mem"],
        "ultima_tarefa": estado["ultima_tarefa"],
        "tavily_uso": controle.get("tavily_uso", 0),
        "tavily_max": MAX_TAVILY,
        "online": True,
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "total_licoes": len(livro_l.get("licoes", [])),
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
            "total_log": len(linhas),
            "ultimas": entradas,
            "total_conversas": mem.get("total_conversas", 0),
            "total_tarefas": mem.get("total_tarefas", 0),
        }
    except:
        return {"total_log": 0, "ultimas": []}

@app.post("/tarefa")
def executar_tarefa_endpoint(payload: TarefaPayload):
    tarefa = payload.tarefa
    dados = payload.dados

    if tarefa == "registrar_licao":
        msg_usuario = dados.get("mensagem_usuario", "")
        ultima_resp = dados.get("ultima_resposta", "")
        if msg_usuario:
            licao = _extrair_licao_via_llm(msg_usuario, ultima_resp)
            if licao:
                registrar_licao(licao["gatilho"], ultima_resp, licao)
                return {"status": "ok", "licao_registrada": True, "gatilho": licao["gatilho"]}
        return {"status": "ok", "licao_registrada": False}

    if tarefa == "buscar_licoes":
        pergunta = dados.get("pergunta", "")
        licoes = buscar_licoes_relevantes(pergunta)
        instrucao = formatar_licoes_para_prompt(licoes)
        return {"status": "ok", "instrucao_prompt": instrucao, "total": len(licoes)}

    if tarefa == "buscar_resumo":
        pergunta = dados.get("pergunta", "")
        ctx = buscar_resumo_relevante(pergunta)
        return {"status": "ok", "contexto": ctx}

    if tarefa == "resumir_agora":
        threading.Thread(target=executar_sumarizacao, daemon=True).start()
        return {"status": "ok", "mensagem": "Sumarização iniciada em background"}

    if tarefa == "status_resumo":
        resumo = _carregar_livro_local("resumo")
        meta = resumo.get("meta", {})
        blocos = resumo.get("blocos", {})
        return {
            "status": "ok",
            "ultima_geracao": meta.get("ultima_geracao", "nunca"),
            "ciclos_completos": meta.get("ciclos_completos", 0),
            "total_processadas": meta.get("total_entradas_processadas", 0),
            "itens_por_bloco": {b: len(v) for b, v in blocos.items()},
        }

    try:
        cpu, mem = estado_sistema()
        resultado = executar_tarefa_com_retorno(tarefa, "tarefa remota", contar_registros(), cpu, mem)
        return {"status": "ok", "tarefa": tarefa, "executada": True, "resultado": resultado}
    except Exception as e:
        return {"status": "erro", "tarefa": tarefa, "erro": str(e)}

@app.get("/licoes")
def listar_licoes_endpoint():
    livro = _carregar_livro_local("licoes")
    licoes = [l for l in livro.get("licoes", []) if l.get("status") == "ativo"]
    return {"total": len(licoes), "licoes": sorted(licoes, key=lambda x: x.get("confianca", 0), reverse=True)}

@app.get("/resumo/{bloco}")
def get_resumo_bloco(bloco: str):
    blocos_validos = {"decisoes", "bugs", "correcoes", "limitacoes", "insights"}
    if bloco not in blocos_validos:
        return {"erro": f"Bloco inválido. Use: {blocos_validos}"}
    resumo = _carregar_livro_local("resumo")
    itens = resumo.get("blocos", {}).get(bloco, [])
    return {"bloco": bloco, "total": len(itens), "itens": itens}

# ── ENDPOINT /buscar — TF-IDF ─────────────────────────────────────────────────
_cache_busca: dict = {}
BUSCA_CACHE_TTL = 600

@app.get("/buscar")
def buscar(query: str, assunto: str = "geral", top_n: int = 5):
    chave_cache = f"{assunto}:{query}"
    agora = time.time()
    if chave_cache in _cache_busca:
        e = _cache_busca[chave_cache]
        if agora - e["ts"] < BUSCA_CACHE_TTL:
            return {"assunto": assunto, "query": query, "resultados": e["resultado"], "cache": True}
    if len(_cache_busca) > 300:
        _cache_busca.clear()
    livro = _carregar_livro_local(assunto)
    if not livro or not livro.get("entradas"):
        return {"assunto": assunto, "query": query, "resultados": [], "cache": False}
    resultados = _buscar_tfidf(query, livro["entradas"], top_n)
    _cache_busca[chave_cache] = {"resultado": resultados, "ts": agora}
    return {"assunto": assunto, "query": query, "resultados": resultados, "cache": False}

@app.get("/livros")
def listar_livros():
    assuntos = ["railway", "groq", "tavily", "hackathons", "eduardo", "codigo", "memoria", "geral"]
    return {a: _carregar_livro_local(a).get("total_entradas", 0) for a in assuntos}

# ── TF-IDF ────────────────────────────────────────────────────────────────────
def _tokenizar(texto: str) -> list:
    texto = texto.lower()
    for ch in ".,;:!?()[]{}\"'\n\r":
        texto = texto.replace(ch, " ")
    return [t for t in texto.split() if len(t) > 2]

def _calcular_tf(tokens: list) -> dict:
    tf = defaultdict(int)
    for t in tokens:
        tf[t] += 1
    total = len(tokens) or 1
    return {t: c / total for t, c in tf.items()}

def _construir_indice(entradas: list) -> dict:
    n_docs = len(entradas)
    if n_docs == 0:
        return {}
    tfs = []
    for e in entradas:
        texto = f"{e.get('texto_indexado', '')} {e.get('pergunta', '')} {e.get('resposta', '')}"
        tfs.append(_calcular_tf(_tokenizar(texto)))
    df = defaultdict(int)
    for tf in tfs:
        for termo in tf:
            df[termo] += 1
    idf = {t: math.log((n_docs + 1) / (c + 1)) + 1 for t, c in df.items()}
    vetores = [{t: tf[t] * idf.get(t, 1.0) for t in tf} for tf in tfs]
    return {"vetores": vetores, "idf": idf}

def _similaridade_cosseno(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    comuns = set(a) & set(b)
    if not comuns:
        return 0.0
    dot = sum(a[t] * b[t] for t in comuns)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

def _buscar_tfidf(query: str, entradas: list, top_n: int = 5) -> list:
    if not entradas:
        return []
    indice = _construir_indice(entradas)
    if not indice:
        return entradas[:top_n]
    tf_q = _calcular_tf(_tokenizar(query))
    vetor_q = {t: tf_q[t] * indice["idf"].get(t, 1.0) for t in tf_q}
    scores = []
    for i, vetor in enumerate(indice["vetores"]):
        score = _similaridade_cosseno(vetor_q, vetor) + entradas[i].get("confianca", 0.7) * 0.05
        scores.append((score, i))
    scores.sort(reverse=True)
    return [{
        "data": entradas[i].get("data", ""),
        "pergunta": entradas[i].get("pergunta", "")[:150],
        "resposta": entradas[i].get("resposta", "")[:150],
        "confianca": entradas[i].get("confianca", 0.7),
        "origem": entradas[i].get("origem", "local"),
        "score": round(score, 4),
    } for score, i in scores[:top_n]]

# ── LIVROS ────────────────────────────────────────────────────────────────────
_cache_livros_local: dict = {}
LIVRO_CACHE_TTL = 120

def _carregar_livro_local(assunto: str) -> dict:
    agora = time.time()
    cached = _cache_livros_local.get(assunto)
    if cached and agora - cached.get("_ts", 0) < LIVRO_CACHE_TTL:
        return cached
    if not GITHUB_TOKEN:
        return {}
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/livro_{assunto}.json"
        r = requests.get(url, headers=GITHUB_HEADERS, timeout=8)
        if r.status_code == 200:
            livro = json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
            livro["_ts"] = agora
            _cache_livros_local[assunto] = livro
            return livro
    except Exception as e:
        debug("LIVRO", f"Erro ao carregar '{assunto}': {e}")
    return {}

def _salvar_livro_github(assunto: str, livro: dict):
    if not GITHUB_TOKEN:
        return
    livro_sem_ts = {k: v for k, v in livro.items() if k != "_ts"}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/livro_{assunto}.json"
    for tentativa in range(3):
        try:
            r = requests.get(url, headers=GITHUB_HEADERS, timeout=8)
            sha = r.json().get("sha", "") if r.status_code == 200 else ""
            conteudo = base64.b64encode(json.dumps(livro_sem_ts, ensure_ascii=False, indent=2).encode()).decode()
            payload = {"message": f"railway: update livro_{assunto}", "content": conteudo}
            if sha:
                payload["sha"] = sha
            r2 = requests.put(url, headers=GITHUB_HEADERS, json=payload, timeout=10)
            if r2.status_code in (200, 201):
                log("LIVRO", f"'{assunto}' salvo no GitHub")
                _cache_livros_local.pop(assunto, None)
                return
            elif r2.status_code == 409:
                warn("LIVRO", f"Conflito 409 em '{assunto}' — tentativa {tentativa + 1}/3")
                time.sleep(1)
            else:
                erro("LIVRO", f"Erro ao salvar '{assunto}': {r2.status_code}")
                return
        except Exception as e:
            erro("LIVRO", f"Exceção ao salvar '{assunto}': {e}")
            return
    erro("LIVRO", f"Falhou após 3 tentativas — '{assunto}' não salvo")

# ── MEMÓRIA COMPARTILHADA ─────────────────────────────────────────────────────
_memoria_compartilhada = None
ciclos_desde_sync = {"n": 0}

def carregar_memoria_github() -> dict:
    if not GITHUB_TOKEN:
        return None
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        r = requests.get(url, headers=GITHUB_HEADERS, timeout=8)
        if r.status_code == 200:
            dados = json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
            log("GITHUB", f"Memória carregada — {dados.get('total_conversas', 0)} conversas")
            return dados
    except Exception as e:
        erro("GITHUB", f"Erro ao carregar: {e}")
    return None

def salvar_memoria_github(memoria: dict):
    if not GITHUB_TOKEN:
        return
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    for tentativa in range(3):
        try:
            r = requests.get(url, headers=GITHUB_HEADERS, timeout=8)
            sha = r.json().get("sha", "") if r.status_code == 200 else ""
            conteudo = base64.b64encode(json.dumps(memoria, ensure_ascii=False, indent=2).encode()).decode()
            payload = {
                "message": f"agente-nuvem: {memoria.get('total_tarefas', 0)} tarefas",
                "content": conteudo,
            }
            if sha:
                payload["sha"] = sha
            r2 = requests.put(url, headers=GITHUB_HEADERS, json=payload, timeout=10)
            if r2.status_code in (200, 201):
                log("GITHUB", f"Sincronizado — {memoria.get('total_tarefas', 0)} tarefas")
                return
            elif r2.status_code == 409:
                warn("GITHUB", f"Conflito 409 — tentativa {tentativa + 1}/3")
                time.sleep(1)
            else:
                erro("GITHUB", f"Erro: {r2.status_code}")
                return
        except Exception as e:
            erro("GITHUB", f"Exceção: {e}")
            return
    erro("GITHUB", "Falhou após 3 tentativas")

def get_memoria_compartilhada() -> dict:
    global _memoria_compartilhada
    if _memoria_compartilhada is None:
        _memoria_compartilhada = {"resumo": "", "aprendizados": [], "total_conversas": 0, "total_tarefas": 0}
    return _memoria_compartilhada

def registrar_tarefa_na_memoria(tarefa: str, resultado: str):
    global _memoria_compartilhada
    mem = get_memoria_compartilhada()
    mem["total_tarefas"] = mem.get("total_tarefas", 0) + 1
    mem["aprendizados"].append({
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "origem": "nuvem",
        "tarefa": tarefa[:100],
        "resultado": resultado[:200],
    })
    if len(mem["aprendizados"]) > 20:
        mem["aprendizados"] = mem["aprendizados"][-20:]
    _memoria_compartilhada = mem

def sincronizar_github_se_necessario():
    ciclos_desde_sync["n"] += 1
    if ciclos_desde_sync["n"] >= SYNC_A_CADA:
        ciclos_desde_sync["n"] = 0
        mem = get_memoria_compartilhada()
        threading.Thread(target=salvar_memoria_github, args=(mem,), daemon=True).start()

# ── LLM (GROQ ch1 → ch2 → Gemini → Cerebras → HuggingFace) ──────────────────
_groq_chave_ativa = {"k": 1}

def chamar_llm(prompt: str, max_tokens: int = 300, system: str = "") -> str:
    chaves = [k for k in [GROQ_KEY_1, GROQ_KEY_2] if k]
    chaves_ordem = chaves[_groq_chave_ativa["k"] - 1:] + chaves[:_groq_chave_ativa["k"] - 1]

    for i, chave in enumerate(chaves_ordem):
        try:
            from groq import Groq
            client = Groq(api_key=chave)
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
            r = client.chat.completions.create(
                model=MODELO_GROQ, messages=msgs, max_tokens=max_tokens
            )
            _groq_chave_ativa["k"] = chaves.index(chave) + 1
            return r.choices[0].message.content.strip()
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                warn("LLM", f"GROQ chave {i+1} limite — tentando próxima")
            else:
                debug("LLM", f"GROQ chave {i+1} falhou: {e}")

    # Fallback Gemini
    if GOOGLE_KEY:
        try:
            payload = {"contents": [{"parts": [{"text": f"{system}\n\n{prompt}" if system else prompt}]}]}
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO_GEM}:generateContent?key={GOOGLE_KEY}",
                json=payload, timeout=15
            )
            r.raise_for_status()
            txt = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if txt:
                warn("LLM", "Usando Gemini como fallback")
                return txt.strip()
        except Exception as e:
            erro("LLM", f"Gemini falhou: {e}")

    # Fallback Cerebras
    if CEREBRAS_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=CEREBRAS_KEY, base_url="https://api.cerebras.ai/v1")
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
            r = client.chat.completions.create(
                model="llama3.1-8b", messages=msgs, max_tokens=max_tokens
            )
            warn("LLM", "Usando Cerebras como fallback")
            return r.choices[0].message.content.strip()
        except Exception as e:
            erro("LLM", f"Cerebras falhou: {e}")

    # Fallback HuggingFace
    if HUGGING_KEY:
        try:
            headers = {"Authorization": f"Bearer {HUGGING_KEY}"}
            texto_completo = f"{system}\n\n{prompt}" if system else prompt
            payload = {"inputs": texto_completo, "parameters": {"max_new_tokens": max_tokens, "return_full_text": False}}
            r = requests.post(
                "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.1",
                headers=headers, json=payload, timeout=20
            )
            r.raise_for_status()
            resultado = r.json()
            if isinstance(resultado, list) and resultado:
                txt = resultado[0].get("generated_text", "").strip()
                if txt:
                    warn("LLM", "Usando HuggingFace (Mistral-7B) como fallback de emergência")
                    return txt
        except Exception as e:
            erro("LLM", f"HuggingFace falhou: {e}")

    return "Nenhuma API disponível no momento."

# ── TAVILY + EXA ──────────────────────────────────────────────────────────────
try:
    from tavily import TavilyClient
    TAVILY_KEY = os.getenv("TAVILY_API_KEY") or os.getenv("TAVLY_API_KEY")
    tavily_client = TavilyClient(api_key=TAVILY_KEY) if TAVILY_KEY else None
    log("TAVILY", "Conectado" if tavily_client else "Chave não encontrada")
except Exception as e:
    tavily_client = None
    log("TAVILY", f"Erro: {e}", "WARN")

def carregar_controle() -> dict:
    try:
        with open(CONTROLE_FILE, "r") as f:
            dados = json.load(f)
        if time.time() - dados.get("timestamp", 0) > RESET_HORAS * 3600:
            novo = {"tavily_uso": 0, "timestamp": time.time()}
            salvar_controle(novo)
            return novo
        return dados
    except:
        return {"tavily_uso": 0, "timestamp": time.time()}

def salvar_controle(dados: dict):
    try:
        with open(CONTROLE_FILE, "w") as f:
            json.dump(dados, f, indent=2)
    except Exception as e:
        erro("CONTROLE", str(e))

def pode_usar_tavily() -> bool:
    dados = carregar_controle()
    if dados["tavily_uso"] >= MAX_TAVILY:
        return False
    dados["tavily_uso"] += 1
    salvar_controle(dados)
    log("TAVILY", f"Uso {dados['tavily_uso']}/{MAX_TAVILY}")
    return True

CACHE_TAVILY: dict = {}

def buscar_exa(query: str) -> str:
    if not EXA_KEY:
        return ""
    try:
        headers = {"x-api-key": EXA_KEY, "Content-Type": "application/json"}
        payload = {"query": query, "numResults": 2, "useAutoprompt": True, "type": "neural"}
        r = requests.post("https://api.exa.ai/search", headers=headers, json=payload, timeout=15)
        r.raise_for_status()
        resultados = r.json().get("results", [])
        if resultados:
            texto = resultados[0].get("text", "") or resultados[0].get("title", "")
            if texto:
                warn("EXA", f"Resultado obtido para: {query[:50]}")
                return texto[:400]
    except Exception as e:
        erro("EXA", f"Falhou: {e}")
    return ""

def buscar_tavily(query: str) -> str:
    agora = time.time()
    if query in CACHE_TAVILY and agora - CACHE_TAVILY[query]["t"] < 600:
        return CACHE_TAVILY[query]["r"]

    # Tenta Tavily primeiro
    if tavily_client and pode_usar_tavily():
        try:
            r = tavily_client.search(query=query, max_results=2, search_depth="basic", include_answer=True)
            resposta = r.get("answer") or (r.get("results", [{"content": ""}])[0].get("content", "")[:300])
            if resposta:
                CACHE_TAVILY[query] = {"r": resposta, "t": agora}
                return resposta
        except Exception as e:
            warn("TAVILY", f"Erro: {e} — tentando EXA")

    # Fallback EXA quando Tavily falha ou cota esgotada
    warn("TAVILY", "Cota atingida ou falha — usando EXA como fallback")
    resposta_exa = buscar_exa(query)
    if resposta_exa:
        CACHE_TAVILY[query] = {"r": resposta_exa, "t": agora}
        return resposta_exa

    return "Limite de buscas atingido e EXA indisponível."

# ── FASE 11: MEMÓRIA NEGATIVA ─────────────────────────────────────────────────
PADROES_CORRECAO = [
    "não é assim", "isso está errado", "você errou", "errou de novo",
    "já falei isso", "já disse isso", "não faça isso", "não faça mais isso",
    "isso é um erro", "não funciona assim", "correção:", "corrigindo:",
    "na verdade", "você entendeu errado", "isso não é correto",
    "você inventou", "está confundindo", "não foi isso",
    "lembre-se que", "nunca faça", "nunca mais faça", "não repita",
    "anti-padrão", "antipadrão", "evite isso",
]

PADROES_ENSINO = [
    "lembre que", "guarde isso", "regra:", "importante:",
    "salva isso", "anota:", "para o futuro:", "a partir de agora",
    "sempre faça", "toda vez que", "quando eu pedir",
]

def detectar_correcao(msg: str) -> bool:
    m = msg.lower()
    return any(p in m for p in PADROES_CORRECAO)

def detectar_ensino(msg: str) -> bool:
    m = msg.lower()
    return any(p in m for p in PADROES_ENSINO)

def _extrair_licao_via_llm(msg_usuario: str, resposta_errada: str) -> dict | None:
    prompt = (
        f"O usuário fez uma correção. Extraia as informações em JSON.\n"
        f"Mensagem do usuário: \"{msg_usuario[:300]}\"\n"
        f"Resposta errada anterior do agente: \"{resposta_errada[:200]}\"\n\n"
        f"Retorne APENAS este JSON sem explicações:\n"
        f"{{\"gatilho\": \"em que situação isso acontece (máx 15 palavras)\","
        f"\"erro\": \"o que o agente fez de errado (máx 20 palavras)\","
        f"\"correto\": \"o que o agente deve fazer (máx 20 palavras)\","
        f"\"tipo\": \"correcao|anti_padrao|ensino\"}}"
    )
    try:
        import re
        resposta = chamar_llm(prompt, max_tokens=150)
        match = re.search(r'\{[^}]+\}', resposta, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        debug("LICAO", f"Extração via LLM falhou: {e}")
    return None

def _verificar_promocao_licao(licao: dict) -> bool:
    if licao.get("promovida_para_identidade"):
        return False
    if licao.get("confirmacoes", 1) >= 2:
        try:
            fmt = "%d/%m/%Y %H:%M"
            primeira = datetime.strptime(licao.get("primeira_ocorrencia", ""), fmt)
            ultima = datetime.strptime(licao.get("ultima_ocorrencia", ""), fmt)
            if (ultima - primeira) <= timedelta(days=30):
                licao["promovida_para_identidade"] = True
                warn("LICAO", f"PROMOÇÃO → identidade_agente.json: '{licao.get('gatilho','')[:60]}'")
                return True
        except Exception:
            pass
    return False

def registrar_licao(gatilho: str, resposta_errada: str, dados_llm: dict | None = None) -> None:
    livro = _carregar_livro_local("licoes")
    if not livro:
        livro = {"assunto": "licoes", "licoes": [], "total_licoes": 0, "ultima_atualizacao": ""}

    tipo_licao = (dados_llm or {}).get("tipo", "correcao")
    confianca = 0.98 if tipo_licao == "anti_padrao" else (0.92 if tipo_licao == "ensino" else 0.95)

    for licao in livro.get("licoes", []):
        if licao.get("status") != "ativo":
            continue
        sim = _sim_jaccard(gatilho, licao.get("gatilho", ""))
        if sim >= 0.85:
            licao["confirmacoes"] = licao.get("confirmacoes", 1) + 1
            licao["confianca"] = min(0.99, licao.get("confianca", confianca) + 0.01)
            licao["ultima_ocorrencia"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            _verificar_promocao_licao(licao)
            log("LICAO", f"Lição REFORÇADA (c={licao['confianca']:.2f}, {licao['confirmacoes']}x): '{gatilho[:60]}'")
            livro["ultima_atualizacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            _cache_livros_local.pop("licoes", None)
            threading.Thread(target=_salvar_livro_github, args=("licoes", livro), daemon=True).start()
            return

    nova = {
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "gatilho": gatilho[:120],
        "erro_cometido": (dados_llm or {}).get("erro", resposta_errada[:100]),
        "comportamento_correto": (dados_llm or {}).get("correto", ""),
        "resposta_errada": resposta_errada[:200],
        "tipo": tipo_licao,
        "confianca": confianca,
        "origem": "correcao_usuario",
        "confirmacoes": 1,
        "primeira_ocorrencia": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "ultima_ocorrencia": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "promovida_para_identidade": False,
        "status": "ativo",
    }
    livro.setdefault("licoes", []).append(nova)
    livro["total_licoes"] = livro.get("total_licoes", 0) + 1
    livro["ultima_atualizacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    if len(livro["licoes"]) > 100:
        livro["licoes"].sort(key=lambda x: (x.get("confianca", 0), x.get("ultima_ocorrencia", "")), reverse=True)
        livro["licoes"] = livro["licoes"][:100]

    tag = {"anti_padrao": "ANTI-PADRÃO", "ensino": "ENSINO"}.get(tipo_licao, "CORREÇÃO")
    warn("LICAO", f"{tag} registrada (c={confianca:.2f}): '{gatilho[:80]}'")
    _cache_livros_local.pop("licoes", None)
    threading.Thread(target=_salvar_livro_github, args=("licoes", livro), daemon=True).start()

def buscar_licoes_relevantes(pergunta: str, top_n: int = 3) -> list:
    livro = _carregar_livro_local("licoes")
    licoes = [l for l in livro.get("licoes", []) if l.get("status") == "ativo"]
    if not licoes:
        return []

    def _score(l):
        sim = _sim_jaccard(pergunta, l.get("gatilho", ""))
        bonus_tipo = 10.0 if l.get("tipo") == "anti_padrao" else 0.0
        return bonus_tipo + sim + l.get("confianca", 0.95) * 0.3

    licoes.sort(key=_score, reverse=True)
    return licoes[:top_n]

def formatar_licoes_para_prompt(licoes: list) -> str:
    if not licoes:
        return ""
    linhas = ["MEMÓRIA NEGATIVA — erros anteriores a evitar:"]
    for l in licoes:
        tag = {"anti_padrao": "ANTI-PADRÃO", "ensino": "ENSINO"}.get(l.get("tipo"), "CORREÇÃO")
        conf = l.get("confirmacoes", 1)
        linhas.append(
            f" [{tag}][{conf}x] Quando: '{l.get('gatilho','')}' | "
            f"NÃO: '{l.get('erro_cometido','')}' | "
            f"FAÇA: '{l.get('comportamento_correto','')}'"
        )
    return "\n".join(linhas)

# ── FASE 12: RESUMO POR IMPORTÂNCIA ──────────────────────────────────────────
GATILHO_ENTRADAS = 30
GATILHO_HORAS = 24
MAX_ITENS_BLOCO = 20

_estado_resumo = {
    "ultima_sumarizacao_ts": 0.0,
    "entradas_desde_ultimo": 0,
}

def _deve_sumarizar() -> bool:
    horas = (time.time() - _estado_resumo["ultima_sumarizacao_ts"]) / 3600
    return (
        _estado_resumo["entradas_desde_ultimo"] >= GATILHO_ENTRADAS or
        horas >= GATILHO_HORAS
    )

def _resumo_vazio() -> dict:
    return {
        "meta": {
            "versao": "1.0",
            "gerado_por": "railway_agente",
            "ultima_geracao": None,
            "total_entradas_processadas": 0,
            "ciclos_completos": 0,
        },
        "blocos": {
            "decisoes": [],
            "bugs": [],
            "correcoes": [],
            "limitacoes": [],
            "insights": [],
        },
    }

PROMPT_CLASSIFICAR_LOTE = """Analise estas entradas de memória de um agente de IA e classifique cada uma.
Para cada entrada, retorne um objeto no array JSON.

Entradas:
{entradas}

Responda APENAS com um array JSON, sem explicações:
[
  {{
    "indice": 0,
    "bloco": "decisoes|bugs|correcoes|limitacoes|insights|irrelevante",
    "resumo": "resumo em máximo 20 palavras",
    "importancia": 0.0,
    "manter": true
  }}
]

Regras de importância (distribua realisticamente — máx 20% pode ser >= 0.9):
- 0.9+ → decisões arquiteturais, correções do usuário confirmadas
- 0.7-0.9 → bugs resolvidos, insights comportamentais relevantes
- 0.5-0.7 → limitações técnicas, observações gerais
- < 0.5 → não manter (manter=false)
"""

def _classificar_lote(entradas_texto: list) -> list:
    if not entradas_texto:
        return []
    texto_formatado = "\n".join([f"{i}: {t[:200]}" for i, t in enumerate(entradas_texto)])
    prompt = PROMPT_CLASSIFICAR_LOTE.format(entradas=texto_formatado)
    try:
        import re
        resposta = chamar_llm(prompt, max_tokens=600)
        match = re.search(r'\[.*?\]', resposta, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        debug("RESUMO", f"Classificação em lote falhou: {e}")
    return []

def executar_sumarizacao():
    log("RESUMO", "Iniciando ciclo de sumarização...")
    memoria = carregar_memoria_github() or {}
    aprendizados = memoria.get("aprendizados", [])
    if len(aprendizados) < 5:
        log("RESUMO", "Poucas entradas — pulando ciclo")
        return
    resumo = _carregar_livro_local("resumo")
    if not resumo or "blocos" not in resumo:
        resumo = _resumo_vazio()
    lote_tamanho = 10
    novas_por_bloco = {b: [] for b in resumo["blocos"]}
    total_processadas = 0
    entradas_para_processar = aprendizados[-50:]
    for i in range(0, len(entradas_para_processar), lote_tamanho):
        lote = entradas_para_processar[i:i + lote_tamanho]
        textos = [
            f"{e.get('pergunta', e.get('tarefa', ''))[:100]} → {e.get('resposta', e.get('resultado', ''))[:100]}"
            for e in lote
        ]
        classificacoes = _classificar_lote(textos)
        for clf in classificacoes:
            if not clf.get("manter", False):
                continue
            bloco = clf.get("bloco", "irrelevante")
            if bloco not in novas_por_bloco:
                continue
            idx = clf.get("indice", 0)
            if idx >= len(lote):
                continue
            e_orig = lote[idx]
            item = {
                "id": f"{bloco[:3]}_{uuid.uuid4().hex[:5]}",
                "resumo": clf.get("resumo", "")[:100],
                "data": e_orig.get("data", datetime.now().strftime("%d/%m/%Y")),
                "importancia": round(clf.get("importancia", 0.5), 2),
            }
            novas_por_bloco[bloco].append(item)
        total_processadas += len(lote)
    for bloco, novos in novas_por_bloco.items():
        todos = resumo["blocos"][bloco] + novos
        todos.sort(key=lambda x: x.get("importancia", 0), reverse=True)
        resumo["blocos"][bloco] = todos[:MAX_ITENS_BLOCO]
    resumo["meta"]["ultima_geracao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    resumo["meta"]["total_entradas_processadas"] = resumo["meta"].get("total_entradas_processadas", 0) + total_processadas
    resumo["meta"]["ciclos_completos"] = resumo["meta"].get("ciclos_completos", 0) + 1
    _salvar_livro_github("resumo", resumo)
    _estado_resumo["ultima_sumarizacao_ts"] = time.time()
    _estado_resumo["entradas_desde_ultimo"] = 0
    total_itens = sum(len(v) for v in resumo["blocos"].values())
    log("RESUMO", f"Ciclo {resumo['meta']['ciclos_completos']} completo — {total_processadas} entradas → {total_itens} itens")

def buscar_resumo_relevante(pergunta: str, top_n: int = 5) -> str:
    resumo = _carregar_livro_local("resumo")
    if not resumo:
        return ""
    linhas = []
    emojis = {"decisoes": "🎯", "bugs": "🐛", "correcoes": "✏️", "limitacoes": "⛔", "insights": "💡"}
    for bloco, itens in resumo.get("blocos", {}).items():
        for item in itens:
            if _sim_jaccard(pergunta, item.get("resumo", "")) > 0.20:
                emoji = emojis.get(bloco, "•")
                linhas.append(f"{emoji} [{bloco.upper()}] {item['resumo']}")
    linhas = linhas[:top_n]
    return ("RESUMO DO HISTÓRICO RELEVANTE:\n" + "\n".join(linhas)) if linhas else ""

# ── SIMILARIDADE JACCARD ──────────────────────────────────────────────────────
def _sim_jaccard(a: str, b: str) -> float:
    wa = set(w for w in a.lower().split() if len(w) >= 3)
    wb = set(w for w in b.lower().split() if len(w) >= 3)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)

# ── APRENDIZADO DE APIs ───────────────────────────────────────────────────────
APRENDIZADO_FILE = "aprendizado.json"

def carregar_aprendizado() -> dict:
    try:
        with open(APRENDIZADO_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def salvar_aprendizado(dados: dict):
    try:
        with open(APRENDIZADO_FILE, "w") as f:
            json.dump(dados, f, indent=2)
    except:
        pass

def registrar_resultado_api(nome: str, tarefa: str, sucesso: bool, tempo: float):
    dados = carregar_aprendizado()
    chave = f"{nome}:{tarefa}"
    if chave not in dados:
        dados[chave] = {"sucesso": 0, "falha": 0, "tempo_total": 0.0, "usos": 0}
    dados[chave]["usos"] += 1
    dados[chave]["tempo_total"] += tempo
    if sucesso:
        dados[chave]["sucesso"] += 1
    else:
        dados[chave]["falha"] += 1
    salvar_aprendizado(dados)

# ── TAREFAS ───────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "Voce e um agente autonomo rodando em nuvem. "
    "Responda sempre em portugues brasileiro. "
    "Seja direto e tecnico. Maximo 2 frases. "
    "NUNCA invente dados, precos, cotacoes ou fatos. "
    "Se nao tiver certeza, diga que nao tem a informacao."
)

objetivos = [
    "otimizar desempenho do sistema",
    "monitorar recursos e memoria",
    "manter o sistema estavel",
    "analisar e limpar dados antigos",
    "gerar relatorios de atividade",
    "buscar cotacao do dolar hoje",
    "buscar noticias de tecnologia hoje",
]

tarefas_possiveis = [
    "monitorar sistema", "limpar memoria", "gerar relatorio",
    "verificar sistema", "analisar memoria", "registrar atividade",
    "mostrar hora", "buscar cotacao dolar", "buscar noticias tech",
]

PALAVRAS_WEB = [
    "cotacao", "cotação", "preco", "preço", "valor",
    "dolar", "dólar", "bitcoin", "euro",
    "noticia", "notícia", "clima", "temperatura",
    "resultado", "placar", "taxa", "juros", "selic",
]

PALAVRAS_BLOQUEIO = [
    "explique", "o que e", "o que é", "como funciona",
    "como fazer", "exemplo", "crie", "gere", "codigo", "código",
]

CACHE_DECISAO: dict = {}

def precisa_tavily(pergunta: str) -> bool:
    p = pergunta.lower().strip()

    if p in CACHE_DECISAO:
        return CACHE_DECISAO[p]

    if any(x in p for x in PALAVRAS_WEB) and any(x in p for x in ["hoje", "agora", "atual", "tempo real", "neste momento"]):
        CACHE_DECISAO[p] = True
        log("ROUTER", "Assunto importante + contexto atual — busca web SIM")
        return True

    if any(x in p for x in PALAVRAS_BLOQUEIO):
        CACHE_DECISAO[p] = False
        log("ROUTER", "Palavra de bloqueio — busca web NAO")
        return False

    try:
        r = chamar_llm(
            f"A tarefa precisa de dados atualizados da internet? Responda APENAS SIM ou NAO.\nTarefa: {pergunta}",
            max_tokens=3
        )
        decisao = "SIM" in r.upper()
        CACHE_DECISAO[p] = decisao
        log("ROUTER", f"LLM decidiu: {'SIM' if decisao else 'NAO'}")
        return decisao
    except Exception as e:
        erro("ROUTER", f"Falha ao consultar LLM: {e}")
        CACHE_DECISAO[p] = False
        return False

def estado_sistema():
    return round(psutil.cpu_percent(interval=1), 1), round(psutil.virtual_memory().percent, 1)

def contar_registros() -> int:
    try:
        with open("memoria.txt", "r", encoding="utf-8") as f:
            return len(f.readlines())
    except:
        return 0

def salvar_log(tarefa: str, conteudo: str):
    try:
        with open("memoria.txt", "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "time": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "tarefa": tarefa, "resultado": conteudo[:200]
            }, ensure_ascii=False) + "\n")
    except Exception as e:
        erro("LOG", str(e))

def limitar_memoria():
    try:
        with open("memoria.txt", "r", encoding="utf-8") as f:
            linhas = f.readlines()
        if len(linhas) > MAX_LOG_LINHAS:
            with open("memoria.txt", "w", encoding="utf-8") as f:
                f.writelines(linhas[-LOG_REDUCAO:])
            log("MEMORIA", f"Log reduzido para {LOG_REDUCAO} linhas")
    except:
        pass

def ler_memoria_decisao() -> dict:
    resultado = {"tarefas_frequentes": [], "tarefas_evitar": [], "busca_recente": False}
    try:
        with open("memoria.txt", "r", encoding="utf-8") as f:
            linhas = f.readlines()[-100:]
        contagem, falhas = {}, {}
        for linha in linhas:
            try:
                e = json.loads(linha)
                t = e.get("tarefa", "")
                contagem[t] = contagem.get(t, 0) + 1
                if any(x in e.get("resultado", "").lower() for x in ["falhou", "erro", "nenhuma api"]):
                    falhas[t] = falhas.get(t, 0) + 1
                if t in ("buscar cotacao dolar", "buscar noticias tech"):
                    resultado["busca_recente"] = True
            except:
                continue
        total = len(linhas)
        resultado["tarefas_frequentes"] = [t for t, n in contagem.items() if total > 0 and n / total > 0.3]
        resultado["tarefas_evitar"] = [t for t, n in falhas.items() if n >= 3]
    except:
        pass
    return resultado

def avaliar_tarefa(t: str) -> int:
    pesos = {
        "monitorar sistema": 4, "limpar memoria": 3, "gerar relatorio": 3,
        "verificar sistema": 3, "analisar memoria": 2, "registrar atividade": 2,
        "mostrar hora": 1, "buscar cotacao dolar": 5, "buscar noticias tech": 4,
    }
    return pesos.get(t, 0)

def avaliar_tarefa_com_memoria(t: str, mem: dict) -> int:
    peso = avaliar_tarefa(t)
    if t in mem.get("tarefas_frequentes", []):
        peso -= 2
    if t in mem.get("tarefas_evitar", []):
        peso -= 3
    if mem.get("busca_recente") and t in ("buscar cotacao dolar", "buscar noticias tech"):
        peso -= 2
    return max(peso, 0)

def planejar_tarefas(objetivo: str) -> list:
    try:
        import ast
        r = chamar_llm(
            f"Objetivo: '{objetivo}'. Escolha 3 tarefas desta lista e responda APENAS "
            f"com uma lista Python válida de strings, sem explicações: {tarefas_possiveis}",
            max_tokens=80
        )
        tarefas = ast.literal_eval(r)
        if isinstance(tarefas, list):
            return [t.lower().strip() for t in tarefas]
    except:
        pass
    return ["monitorar sistema", "registrar atividade", "verificar sistema"]

def executar_tarefa_com_retorno(tarefa: str, objetivo: str, registros: int, cpu: float, mem: float) -> str:
    agora = datetime.now().strftime("%H:%M:%S")
    contexto = f"Objetivo: {objetivo} | Registros: {registros} | CPU: {cpu}% | Mem: {mem}%"
    resultado = ""

    if tarefa in ("buscar cotacao dolar", "buscar noticias tech"):
        queries = {
            "buscar cotacao dolar": "cotacao dolar hoje brasil real",
            "buscar noticias tech": "noticias tecnologia inteligencia artificial hoje",
        }
        query = queries[tarefa]
        resultado = buscar_tavily(query) if precisa_tavily(query) else chamar_llm(f"Execute sem dados da internet: '{tarefa}'.", max_tokens=100, system=SYSTEM_PROMPT)
    elif tarefa == "mostrar hora":
        resultado = agora
    elif tarefa == "monitorar sistema":
        resultado = f"CPU: {cpu}% | Mem: {mem}%"
    elif tarefa == "verificar sistema":
        resultado = chamar_llm(f"CPU: {cpu}%, Memoria: {mem}%, Hora: {agora}. O sistema esta saudavel?", max_tokens=100, system=SYSTEM_PROMPT)
    elif tarefa == "registrar atividade":
        resultado = f"Atividade registrada as {agora}"
    elif tarefa == "analisar memoria":
        resultado = chamar_llm(f"Tenho {registros} registros. Objetivo: {objetivo}. O que devo fazer?", max_tokens=100, system=SYSTEM_PROMPT)
    elif tarefa == "limpar memoria":
        try:
            open("memoria.txt", "w", encoding="utf-8").close()
            resultado = "Memoria limpa com sucesso"
        except Exception as e:
            resultado = f"Erro ao limpar: {e}"
    elif tarefa == "gerar relatorio":
        resultado = chamar_llm(f"Gere um resumo tecnico de {registros} registros do agente em nuvem.", max_tokens=150, system=SYSTEM_PROMPT)
    else:
        resultado = chamar_llm(f"Execute: '{tarefa}'. Contexto: {contexto}", max_tokens=150, system=SYSTEM_PROMPT)

    if resultado:
        salvar_log(tarefa, resultado)
        registrar_tarefa_na_memoria(tarefa, resultado)
        _estado_resumo["entradas_desde_ultimo"] += 1

    return resultado or "Tarefa executada sem resultado."

# ── LOOP PRINCIPAL ────────────────────────────────────────────────────────────
def loop_agente():
    global _memoria_compartilhada

    contador = 0
    objetivo = random.choice(objetivos)
    tarefas = []
    ultima_tarefa = None

    log("MAIN", "=" * 52)
    log("MAIN", " AGENTE AUTÔNOMO EM NUVEM — v4.2")
    log("MAIN", f" Tavily   : {'OK' if tavily_client else 'INDISPONÍVEL'}")
    log("MAIN", f" EXA      : {'configurado' if EXA_KEY else 'sem chave'}")
    log("MAIN", f" GitHub   : {'configurado' if GITHUB_TOKEN else 'sem token'}")
    log("MAIN", f" Cerebras : {'configurado' if CEREBRAS_KEY else 'sem chave'}")
    log("MAIN", f" HuggingFace : {'configurado' if HUGGING_KEY else 'sem chave'}")
    log("MAIN", f" TF-IDF   : ativo — endpoint /buscar disponível")
    log("MAIN", f" Fase11   : memória negativa ativa")
    log("MAIN", f" Fase12   : resumo por importância ativo")
    log("MAIN", "=" * 52)

    dados_github = carregar_memoria_github()
    if dados_github:
        _memoria_compartilhada = dados_github
        _memoria_compartilhada.setdefault("total_tarefas", 0)
    else:
        _memoria_compartilhada = {"resumo": "", "aprendizados": [], "total_conversas": 0, "total_tarefas": 0}

    log("MAIN", f"Objetivo inicial: {objetivo}")

    while not _encerrando["v"]:
        try:
            contador += 1
            registros = contar_registros()

            if contador % 20 == 0:
                objetivo = random.choice(objetivos)
                log("OBJETIVO", f"Novo: {objetivo}")

            cpu, mem = estado_sistema()
            estado.update({"ciclo": contador, "objetivo": objetivo, "cpu": cpu, "mem": mem})

            log("RAILWAY", f"Online — Ciclo {contador} | CPU {cpu}% | Mem {mem}%")

            limitar_memoria()
            memoria_decisao = ler_memoria_decisao()

            if not tarefas:
                tarefas.extend(planejar_tarefas(objetivo))
            if cpu > 70:
                tarefas.append("analisar memoria")
            if mem > 70:
                tarefas.append("limpar memoria")
            if contador % 30 == 0:
                tarefas.append("buscar cotacao dolar")

            tarefas.append(random.choice(tarefas_possiveis))

            melhor = max(tarefas, key=lambda t: avaliar_tarefa_com_memoria(t, memoria_decisao))
            if melhor == ultima_tarefa and len(tarefas) > 1:
                outros = [t for t in tarefas if t != melhor]
                melhor = max(outros, key=lambda t: avaliar_tarefa_com_memoria(t, memoria_decisao))

            log("TAREFA", f"Executando: {melhor}")
            resultado = executar_tarefa_com_retorno(melhor, objetivo, registros, cpu, mem)
            log("TAREFA", resultado[:120])
            tarefas.remove(melhor)
            ultima_tarefa = melhor
            estado["ultima_tarefa"] = melhor

            sincronizar_github_se_necessario()

            if _deve_sumarizar():
                log("RESUMO", "Gatilho atingido — iniciando sumarização em background")
                threading.Thread(target=executar_sumarizacao, daemon=True).start()

            time.sleep(60)

        except Exception as e:
            erro("LOOP", str(e))
            time.sleep(15)

    log("MAIN", "Loop encerrado.")

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    thread = threading.Thread(target=loop_agente, daemon=True)
    thread.start()
    porta = int(os.getenv("PORT", 8080))
    log("MAIN", f"Servidor iniciando na porta {porta}")
    uvicorn.run(app, host="0.0.0.0", port=porta)
