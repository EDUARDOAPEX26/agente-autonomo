import time
import random
import psutil
import requests
import json
import os
import base64
import threading
from datetime import datetime
from fastapi import FastAPI
import uvicorn

# ── FASTAPI ──────────────────────────────────────────────
app = FastAPI()

estado = {
    "ciclo":         0,
    "objetivo":      "iniciando",
    "cpu":           0.0,
    "mem":           0.0,
    "ultima_tarefa": "",
    "tavily_uso":    0,
    "online":        True,
}

@app.get("/status")
def status():
    controle = carregar_controle()
    return {
        "ciclo":         estado["ciclo"],
        "objetivo":      estado["objetivo"],
        "cpu":           estado["cpu"],
        "mem":           estado["mem"],
        "ultima_tarefa": estado["ultima_tarefa"],
        "tavily_uso":    controle.get("tavily_uso", 0),
        "tavily_max":    MAX_TAVILY,
        "online":        True,
        "timestamp":     datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }

@app.get("/memoria")
def get_memoria_endpoint():
    """Retorna as últimas 50 entradas do log interno + resumo da memória compartilhada."""
    try:
        with open("memoria.txt", "r", encoding="utf-8") as f:
            linhas = f.readlines()[-50:]
        entradas = []
        for linha in linhas:
            try:
                entradas.append(json.loads(linha))
            except:
                entradas.append({"raw": linha.strip()})

        mem_compartilhada = get_memoria_compartilhada()
        return {
            "total_log":          len(linhas),
            "ultimas":            entradas,
            "total_conversas":    mem_compartilhada.get("total_conversas", 0),
            "total_tarefas":      mem_compartilhada.get("total_tarefas", 0),
        }
    except:
        return {"total_log": 0, "ultimas": []}

@app.post("/tarefa")
def executar_tarefa_remota(tarefa: str, objetivo: str = "tarefa remota"):
    try:
        cpu, mem = estado_sistema()
        executar_tarefa(tarefa, objetivo, contar_registros(), cpu, mem)
        return {"status": "ok", "tarefa": tarefa, "executada": True}
    except Exception as e:
        return {"status": "erro", "tarefa": tarefa, "erro": str(e)}

@app.get("/ping")
def ping():
    return {"pong": True}

# ── CHAVES ───────────────────────────────────────────────
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
GITHUB_REPO    = "EDUARDOAPEX26/agente-autonomo"
GITHUB_FILE    = "memoria_chat.json"
GITHUB_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

APIS = [
    {"nome": "Groq",        "tipo": "groq",   "chave": os.getenv("GROQ_API_KEY"),    "modelo": "llama-3.1-8b-instant"},
    {"nome": "Gemini",      "tipo": "gemini", "chave": os.getenv("GEMINI_API_KEY"),  "modelo": "gemini-1.5-flash"},
    {"nome": "HuggingFace", "tipo": "hf",     "chave": os.getenv("HUGGING_API_KEY"), "modelo": "mistralai/Mistral-7B-Instruct-v0.3"},
]

# ── MEMÓRIA COMPARTILHADA (GITHUB) ────────────────────────
# Mesma estrutura do chat.py local:
# { "resumo": "", "aprendizados": [], "total_conversas": 0, "total_tarefas": 0 }

_memoria_compartilhada = None
SYNC_A_CADA_CICLOS = 10  # sincroniza GitHub a cada 10 ciclos
ciclos_desde_sync  = {"n": 0}

def carregar_memoria_github() -> dict:
    if not GITHUB_TOKEN:
        print("[GITHUB] Token nao configurado")
        return None
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        r = requests.get(url, headers=GITHUB_HEADERS, timeout=8)
        if r.status_code == 200:
            conteudo = base64.b64decode(r.json()["content"]).decode("utf-8")
            dados = json.loads(conteudo)
            print(f"[GITHUB] Memoria carregada — {dados.get('total_conversas', 0)} conversas | {dados.get('total_tarefas', 0)} tarefas")
            return dados
        print("[GITHUB] Arquivo nao encontrado — iniciando do zero")
        return None
    except Exception as e:
        print(f"[GITHUB] Erro ao carregar: {e}")
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
            "message": f"agente-nuvem: {memoria.get('total_tarefas', 0)} tarefas | {memoria.get('total_conversas', 0)} conversas",
            "content": conteudo,
        }
        if sha:
            payload["sha"] = sha

        r2 = requests.put(url, headers=GITHUB_HEADERS, json=payload, timeout=10)
        if r2.status_code in (200, 201):
            print(f"[GITHUB] Sincronizado — {memoria.get('total_tarefas', 0)} tarefas | {memoria.get('total_conversas', 0)} conversas")
        else:
            print(f"[GITHUB] Erro ao salvar: {r2.status_code}")
    except Exception as e:
        print(f"[GITHUB] Erro: {e}")

def get_memoria_compartilhada() -> dict:
    global _memoria_compartilhada
    if _memoria_compartilhada is None:
        _memoria_compartilhada = {"resumo": "", "aprendizados": [], "total_conversas": 0, "total_tarefas": 0}
    return _memoria_compartilhada

def registrar_tarefa_na_memoria(tarefa: str, resultado: str):
    """Registra tarefa executada na memória compartilhada."""
    global _memoria_compartilhada
    mem = get_memoria_compartilhada()
    mem["total_tarefas"] = mem.get("total_tarefas", 0) + 1
    mem["aprendizados"].append({
        "data":     datetime.now().strftime("%d/%m/%Y %H:%M"),
        "origem":   "nuvem",
        "tarefa":   tarefa[:100],
        "resultado": resultado[:200],
    })
    # Mantém só os últimos 20 aprendizados
    if len(mem["aprendizados"]) > 20:
        mem["aprendizados"] = mem["aprendizados"][-20:]
    _memoria_compartilhada = mem

def sincronizar_github_se_necessario():
    """Sincroniza com GitHub a cada SYNC_A_CADA_CICLOS ciclos."""
    ciclos_desde_sync["n"] += 1
    if ciclos_desde_sync["n"] >= SYNC_A_CADA_CICLOS:
        ciclos_desde_sync["n"] = 0
        mem = get_memoria_compartilhada()
        threading.Thread(
            target=salvar_memoria_github,
            args=(mem,),
            daemon=True
        ).start()

# ── TAVILY ───────────────────────────────────────────────
try:
    from tavily import TavilyClient
    TAVILY_KEY    = os.getenv("TAVILY_API_KEY")
    tavily_client = TavilyClient(api_key=TAVILY_KEY) if TAVILY_KEY else None
    print(f"[TAVILY] {'Conectado' if tavily_client else 'Chave nao encontrada'}")
except Exception as e:
    tavily_client = None
    print(f"[TAVILY] Erro: {e}")

# ── CONTROLE TAVILY ───────────────────────────────────────
CONTROLE_FILE = "controle.json"
MAX_TAVILY    = 10
RESET_HORAS   = 24

def carregar_controle() -> dict:
    try:
        with open(CONTROLE_FILE, "r") as f:
            dados = json.load(f)
        if time.time() - dados.get("timestamp", 0) > RESET_HORAS * 3600:
            print(f"[CONTROLE] {RESET_HORAS}h passadas — resetando Tavily")
            return {"tavily_uso": 0, "timestamp": time.time(), "data": datetime.now().strftime("%Y-%m-%d")}
        return dados
    except:
        return {"tavily_uso": 0, "timestamp": time.time(), "data": datetime.now().strftime("%Y-%m-%d")}

def salvar_controle(dados: dict):
    try:
        with open(CONTROLE_FILE, "w") as f:
            json.dump(dados, f, indent=2)
    except Exception as e:
        print(f"[CONTROLE] Erro: {e}")

def pode_usar_tavily() -> bool:
    dados = carregar_controle()
    if dados["tavily_uso"] >= MAX_TAVILY:
        print(f"[TAVILY] Limite atingido.")
        return False
    dados["tavily_uso"] += 1
    salvar_controle(dados)
    print(f"[TAVILY] Uso {dados['tavily_uso']}/{MAX_TAVILY} hoje")
    return True

# ── CACHE ─────────────────────────────────────────────────
CACHE_DECISAO = {}
CACHE_TAVILY  = {}
MAX_CACHE     = 500

def limpar_cache_se_cheio():
    if len(CACHE_DECISAO) > MAX_CACHE:
        CACHE_DECISAO.clear()
    if len(CACHE_TAVILY) > MAX_CACHE:
        CACHE_TAVILY.clear()

# ── PALAVRAS-CHAVE ────────────────────────────────────────
PALAVRAS_WEB = [
    "cotacao", "cotação", "preco", "preço", "valor",
    "dolar", "dólar", "bitcoin", "euro", "real",
    "noticia", "notícia", "noticias", "notícias",
    "clima", "temperatura", "chuva",
    "resultado", "placar", "jogo", "partida",
    "taxa", "juros", "selic", "ibovespa",
]

PALAVRAS_BLOQUEIO = [
    "explique", "o que e", "o que é", "como funciona",
    "como fazer", "exemplo", "crie", "gere", "codigo",
    "código", "me ajude", "explica", "defina",
]

# ── ROUTER ───────────────────────────────────────────────
def precisa_tavily(pergunta: str) -> bool:
    p = pergunta.lower().strip()
    limpar_cache_se_cheio()

    if p in CACHE_DECISAO:
        return CACHE_DECISAO[p]

    if any(x in p for x in PALAVRAS_BLOQUEIO):
        CACHE_DECISAO[p] = False
        return False

    if any(x in p for x in PALAVRAS_WEB):
        print("[ROUTER] Palavra-chave web — Tavily SIM")
        CACHE_DECISAO[p] = True
        return True

    prompt = (
        "A tarefa precisa de dados atualizados da internet "
        "(preco, cotacao, noticias, clima, resultados)?\n"
        "Responda APENAS SIM ou NAO.\n\n"
        f"Tarefa: {pergunta}"
    )

    try:
        from groq import Groq
        api = next((a for a in APIS if a["tipo"] == "groq" and a["chave"]), None)
        if not api:
            raise Exception("Groq indisponivel")
        client = Groq(api_key=api["chave"])
        r = client.chat.completions.create(
            model=api["modelo"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3, temperature=0
        )
        decisao = "SIM" in r.choices[0].message.content.strip().upper()
        CACHE_DECISAO[p] = decisao
        return decisao
    except Exception as e:
        print(f"[ROUTER] GROQ falhou: {e}")

    CACHE_DECISAO[p] = False
    return False

# ── BUSCA TAVILY ──────────────────────────────────────────
def buscar_tavily(query: str) -> str:
    if not tavily_client:
        return "Tavily nao configurado."

    agora = time.time()
    limpar_cache_se_cheio()

    if query in CACHE_TAVILY:
        if agora - CACHE_TAVILY[query]["t"] < 600:
            return CACHE_TAVILY[query]["r"]

    if not pode_usar_tavily():
        return "Limite de buscas Tavily atingido."

    try:
        print(f"[TAVILY] Buscando: {query}")
        r = tavily_client.search(
            query=query, max_results=2,
            search_depth="basic", include_answer=True
        )
        resposta = r.get("answer", "")
        if not resposta:
            resultados = r.get("results", [])
            resposta = resultados[0].get("content", "Sem resultado")[:300] if resultados else "Sem resultado"
        CACHE_TAVILY[query] = {"r": resposta, "t": agora}
        print(f"[TAVILY] OK ({len(resposta)} chars)")
        return resposta
    except Exception as e:
        print(f"[TAVILY] Erro: {e}")
        return f"Tavily erro: {e}"

# ── APRENDIZADO DE APIs ───────────────────────────────────
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

def registrar_resultado(api_nome: str, tarefa: str, sucesso: bool, tempo: float):
    dados = carregar_aprendizado()
    chave = f"{api_nome}:{tarefa}"
    if chave not in dados:
        dados[chave] = {"sucesso": 0, "falha": 0, "tempo_total": 0.0, "usos": 0}
    dados[chave]["usos"]        += 1
    dados[chave]["tempo_total"] += tempo
    if sucesso:
        dados[chave]["sucesso"] += 1
    else:
        dados[chave]["falha"] += 1
    salvar_aprendizado(dados)

def melhor_api_para(tarefa: str) -> dict:
    dados = carregar_aprendizado()
    melhor = None
    melhor_score = -1
    for api in APIS:
        chave = f"{api['nome']}:{tarefa}"
        if chave in dados:
            d = dados[chave]
            if d["usos"] > 0:
                taxa   = d["sucesso"] / d["usos"]
                tmedio = d["tempo_total"] / d["usos"]
                score  = taxa * 100 - tmedio
                if score > melhor_score:
                    melhor_score = score
                    melhor = api
    return melhor or APIS[0]

# ── CHAMADA IA ───────────────────────────────────────────
SYSTEM_PROMPT = (
    "Voce e um agente autonomo rodando em nuvem. "
    "Responda sempre em portugues brasileiro. "
    "Seja direto e tecnico. Maximo 2 frases. "
    "NUNCA invente dados, precos, cotacoes ou fatos. "
    "Se nao tiver certeza, diga que nao tem a informacao."
)

def chamar_ia(tarefa: str, user_prompt: str, max_tokens: int = 200) -> str:
    api = melhor_api_para(tarefa)
    inicio = time.time()
    try:
        resultado = _chamar_api(api, user_prompt, max_tokens)
        registrar_resultado(api["nome"], tarefa, True, time.time() - inicio)
        print(f"[{api['nome']}] OK ({time.time() - inicio:.1f}s)")
        return resultado
    except Exception as e:
        registrar_resultado(api["nome"], tarefa, False, time.time() - inicio)
        print(f"[{api['nome']}] FALHOU: {e}")
        for alt in APIS:
            if alt["nome"] == api["nome"] or not alt.get("chave"):
                continue
            try:
                resultado = _chamar_api(alt, user_prompt, max_tokens)
                registrar_resultado(alt["nome"], tarefa, True, time.time() - inicio)
                print(f"[FALLBACK] Usando {alt['nome']}")
                return resultado
            except Exception as e2:
                print(f"[FALLBACK] {alt['nome']} falhou: {e2}")
    return "Nenhuma API disponivel no momento."

def _chamar_api(api: dict, user_prompt: str, max_tokens: int) -> str:
    if not api.get("chave"):
        raise Exception(f"{api['nome']} sem chave")

    if api["tipo"] == "groq":
        from groq import Groq
        client = Groq(api_key=api["chave"])
        r = client.chat.completions.create(
            model=api["modelo"],
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=max_tokens
        )
        return r.choices[0].message.content.strip()

    elif api["tipo"] == "gemini":
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{api['modelo']}:generateContent?key={api['chave']}",
            json={"contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}]}]},
            timeout=15
        )
        r.raise_for_status()
        txt = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if not txt:
            raise Exception("Gemini retornou resposta vazia")
        return txt.strip()

    elif api["tipo"] == "hf":
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=api["chave"])
        r = client.chat_completion(
            model=api["modelo"],
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=max_tokens
        )
        return r.choices[0].message.content.strip()

    raise ValueError(f"Tipo desconhecido: {api['tipo']}")

# ── TAREFAS ──────────────────────────────────────────────
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

def estado_sistema():
    cpu = round(psutil.cpu_percent(interval=1), 1)
    mem = round(psutil.virtual_memory().percent, 1)
    return cpu, mem

def planejar_tarefas(objetivo: str) -> list:
    try:
        import ast
        resposta = chamar_ia(
            "planejar",
            f"Objetivo: '{objetivo}'. Escolha 3 tarefas desta lista e responda APENAS "
            f"com uma lista Python valida de strings, sem explicacoes: {tarefas_possiveis}",
            max_tokens=80
        )
        tarefas = ast.literal_eval(resposta)
        if isinstance(tarefas, list):
            return [t.lower().strip() for t in tarefas]
    except:
        pass
    return ["monitorar sistema", "registrar atividade", "verificar sistema"]

def executar_tarefa(tarefa: str, objetivo: str, registros: int, cpu: float, mem: float):
    agora    = datetime.now().strftime("%H:%M:%S")
    contexto = f"Objetivo: {objetivo} | Registros: {registros} | CPU: {cpu}% | Mem: {mem}%"
    resultado = ""

    if tarefa in ("buscar cotacao dolar", "buscar noticias tech"):
        queries = {
            "buscar cotacao dolar": "cotacao dolar hoje brasil real",
            "buscar noticias tech": "noticias tecnologia inteligencia artificial hoje",
        }
        query = queries[tarefa]
        if precisa_tavily(query):
            resultado = buscar_tavily(query)
        else:
            resultado = chamar_ia(tarefa, f"Execute sem dados da internet: '{tarefa}'.")
        print(f"[{tarefa}] {resultado[:120]}")

    elif tarefa == "mostrar hora":
        resultado = agora
        print(f"[HORA] {agora}")

    elif tarefa == "monitorar sistema":
        resultado = f"CPU: {cpu}% | Mem: {mem}%"
        print(f"[SISTEMA] {resultado}")

    elif tarefa == "verificar sistema":
        resultado = chamar_ia(tarefa, f"CPU: {cpu}%, Memoria: {mem}%, Hora: {agora}. O sistema esta saudavel?")
        print(f"[VERIFICAR] {resultado}")

    elif tarefa == "registrar atividade":
        resultado = f"Atividade registrada as {agora}"
        print("[LOG] Atividade registrada")

    elif tarefa == "analisar memoria":
        try:
            with open("memoria.txt", "r", encoding="utf-8") as f:
                linhas = f.readlines()
            resultado = chamar_ia(tarefa, f"Tenho {len(linhas)} registros. Objetivo: {objetivo}. O que devo fazer?")
            print(f"[ANALISE] {resultado}")
        except FileNotFoundError:
            resultado = "memoria.txt ainda nao existe"
            print(f"[MEMORIA] {resultado}")

    elif tarefa == "limpar memoria":
        try:
            with open("memoria.txt", "w", encoding="utf-8") as f:
                f.write("")
            resultado = "Memoria limpa com sucesso"
            print("[MEMORIA] Limpa com sucesso.")
        except Exception as e:
            resultado = f"Erro ao limpar: {e}"
            print(f"[MEMORIA] Erro: {e}")

    elif tarefa == "gerar relatorio":
        try:
            with open("memoria.txt", "r", encoding="utf-8") as f:
                linhas = f.readlines()
            resultado = chamar_ia(tarefa, f"Gere um resumo tecnico de {len(linhas)} registros do agente em nuvem.")
            with open("relatorio.txt", "w", encoding="utf-8") as rel:
                rel.write(f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}]\n{resultado}\n")
            print("[RELATORIO] Criado.")
        except Exception as e:
            resultado = f"Erro ao gerar relatorio: {e}"
            print(f"[RELATORIO] Erro: {e}")

    else:
        resultado = chamar_ia(tarefa, f"Execute: '{tarefa}'. Contexto: {contexto}")
        print(f"[IA] {resultado}")

    # Salva no log interno
    salvar_log(tarefa, resultado)

    # Registra na memória compartilhada GitHub
    if resultado:
        registrar_tarefa_na_memoria(tarefa, resultado)

def salvar_log(tarefa: str, conteudo: str):
    try:
        with open("memoria.txt", "a", encoding="utf-8") as f:
            entrada = json.dumps({
                "time":      datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "tarefa":    tarefa,
                "resultado": conteudo[:200]
            }, ensure_ascii=False)
            f.write(entrada + "\n")
    except Exception as e:
        print(f"[LOG] Erro: {e}")

def limitar_memoria():
    try:
        with open("memoria.txt", "r", encoding="utf-8") as f:
            linhas = f.readlines()
        if len(linhas) > 2000:
            with open("memoria.txt", "w", encoding="utf-8") as f:
                f.writelines(linhas[-1000:])
            print(f"[MEMORIA] Log reduzido para 1000 linhas")
    except:
        pass

def ler_memoria_decisao() -> dict:
    resultado = {"tarefas_frequentes": [], "tarefas_evitar": [], "busca_recente": False}
    try:
        with open("memoria.txt", "r", encoding="utf-8") as f:
            linhas = f.readlines()[-100:]
        contagem = {}
        falhas   = {}
        for linha in linhas:
            try:
                entrada = json.loads(linha)
                tarefa  = entrada.get("tarefa", "")
                texto   = entrada.get("resultado", "").lower()
                contagem[tarefa] = contagem.get(tarefa, 0) + 1
                if any(x in texto for x in ["falhou", "erro", "nenhuma api", "indisponivel"]):
                    falhas[tarefa] = falhas.get(tarefa, 0) + 1
                if tarefa in ("buscar cotacao dolar", "buscar noticias tech"):
                    resultado["busca_recente"] = True
            except:
                continue
        total = len(linhas)
        resultado["tarefas_frequentes"] = [t for t, n in contagem.items() if total > 0 and n / total > 0.3]
        resultado["tarefas_evitar"]     = [t for t, n in falhas.items() if n >= 3]
    except:
        pass
    return resultado

def avaliar_tarefa(tarefa: str) -> int:
    pesos = {
        "monitorar sistema":    4, "limpar memoria":       3,
        "gerar relatorio":      3, "verificar sistema":    3,
        "analisar memoria":     2, "registrar atividade":  2,
        "mostrar hora":         1,
        "buscar cotacao dolar": 5,
        "buscar noticias tech": 4,
    }
    return pesos.get(tarefa, 0)

def avaliar_tarefa_com_memoria(tarefa: str, memoria_decisao: dict) -> int:
    peso = avaliar_tarefa(tarefa)
    if tarefa in memoria_decisao.get("tarefas_frequentes", []):
        peso -= 2
    if tarefa in memoria_decisao.get("tarefas_evitar", []):
        peso -= 3
    if memoria_decisao.get("busca_recente") and tarefa in ("buscar cotacao dolar", "buscar noticias tech"):
        peso -= 2
    return max(peso, 0)

def contar_registros() -> int:
    try:
        with open("memoria.txt", "r", encoding="utf-8") as f:
            return len(f.readlines())
    except:
        return 0

# ── LOOP PRINCIPAL ───────────────────────────────────────
def loop_agente():
    global estado, _memoria_compartilhada

    contador      = 0
    objetivo      = random.choice(objetivos)
    tarefas       = []
    ultima_tarefa = None

    print("=" * 52)
    print("  AGENTE AUTONOMO EM NUVEM")
    print(f"  Tavily : {'OK' if tavily_client else 'INDISPONIVEL'}")
    print(f"  APIs   : {[a['nome'] for a in APIS]}")
    print(f"  GitHub : {'configurado' if GITHUB_TOKEN else 'sem token'}")
    print("=" * 52)

    # Carrega memória compartilhada do GitHub ao iniciar
    dados_github = carregar_memoria_github()
    if dados_github:
        _memoria_compartilhada = dados_github
        # Garante campo total_tarefas existe
        if "total_tarefas" not in _memoria_compartilhada:
            _memoria_compartilhada["total_tarefas"] = 0
    else:
        _memoria_compartilhada = {"resumo": "", "aprendizados": [], "total_conversas": 0, "total_tarefas": 0}

    print(f"[OBJETIVO] Inicial: {objetivo}\n")

    while True:
        try:
            contador += 1
            agora     = datetime.now().strftime("%H:%M:%S")
            registros = contar_registros()

            if contador % 20 == 0:
                objetivo = random.choice(objetivos)
                print(f"\n[OBJETIVO] Novo: {objetivo}")

            cpu, mem = estado_sistema()

            estado.update({
                "ciclo":    contador,
                "objetivo": objetivo,
                "cpu":      cpu,
                "mem":      mem,
            })

            print(f"\n----- Ciclo {contador} | {agora} -----")
            print(f"Objetivo : {objetivo}")
            controle = carregar_controle()
            mem_comp = get_memoria_compartilhada()
            print(f"Registros: {registros} | Tavily: {controle.get('tavily_uso', 0)}/{MAX_TAVILY}")
            print(f"CPU: {cpu}% | Mem: {mem}% | Tarefas acumuladas: {mem_comp.get('total_tarefas', 0)}")

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
                tarefas_sem = [t for t in tarefas if t != melhor]
                melhor = max(tarefas_sem, key=lambda t: avaliar_tarefa_com_memoria(t, memoria_decisao))
                print(f"[SKIP] Evitando repeticao — escolhendo: {melhor}")

            print(f"[TAREFA] Executando: {melhor}")
            executar_tarefa(melhor, objetivo, registros, cpu, mem)
            tarefas.remove(melhor)
            ultima_tarefa = melhor
            estado["ultima_tarefa"] = melhor

            # Sincroniza GitHub a cada 10 ciclos
            sincronizar_github_se_necessario()

            sleep_time = 30 if cpu > 50 else 15
            print(f"[CICLO] Aguardando {sleep_time}s...")
            time.sleep(sleep_time)

        except Exception as e:
            print(f"[ERRO] {e}")
            time.sleep(15)

# ── INICIALIZAÇÃO ─────────────────────────────────────────
if __name__ == "__main__":
    thread = threading.Thread(target=loop_agente, daemon=True)
    thread.start()

    porta = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=porta)
