import time
import random
import psutil
import requests
import json
import os
from datetime import datetime

# ── CHAVES ───────────────────────────────────────────────
APIS = [
    {"nome": "Groq",        "tipo": "groq",   "chave": os.getenv("GROQ_API_KEY"),    "modelo": "llama-3.1-8b-instant"},
    {"nome": "Gemini",      "tipo": "gemini", "chave": os.getenv("GEMINI_API_KEY"),  "modelo": "gemini-1.5-flash"},
    {"nome": "HuggingFace", "tipo": "hf",     "chave": os.getenv("HUGGING_API_KEY"), "modelo": "mistralai/Mistral-7B-Instruct-v0.3"},
]

# ── TAVILY ───────────────────────────────────────────────
try:
    from tavily import TavilyClient
    TAVILY_KEY    = os.getenv("TAVILY_API_KEY")
    tavily_client = TavilyClient(api_key=TAVILY_KEY) if TAVILY_KEY else None
    print(f"[TAVILY] {'Conectado' if tavily_client else 'Chave nao encontrada'}")
except Exception as e:
    tavily_client = None
    print(f"[TAVILY] Erro: {e}")

# ── CONTROLE PERSISTENTE DO TAVILY ──────────────────────
# Salvo em arquivo para sobreviver a reinicializações do Railway
CONTROLE_FILE = "controle.json"
MAX_TAVILY    = 10   # máximo de buscas por dia
RESET_HORAS   = 24  # reset automático após 24h

def carregar_controle() -> dict:
    try:
        with open(CONTROLE_FILE, "r") as f:
            dados = json.load(f)
        # Reset automático se passaram mais de 24h
        ultimo = dados.get("timestamp", 0)
        if time.time() - ultimo > RESET_HORAS * 3600:
            print(f"[CONTROLE] {RESET_HORAS}h passadas — resetando contador Tavily")
            return {"tavily_uso": 0, "timestamp": time.time(), "data": datetime.now().strftime("%Y-%m-%d")}
        return dados
    except:
        return {"tavily_uso": 0, "timestamp": time.time(), "data": datetime.now().strftime("%Y-%m-%d")}

def salvar_controle(dados: dict):
    try:
        with open(CONTROLE_FILE, "w") as f:
            json.dump(dados, f, indent=2)
    except Exception as e:
        print(f"[CONTROLE] Erro ao salvar: {e}")

def pode_usar_tavily() -> bool:
    dados = carregar_controle()
    if dados["tavily_uso"] >= MAX_TAVILY:
        print(f"[TAVILY] Limite de {MAX_TAVILY} buscas/dia atingido. Bloqueado.")
        return False
    dados["tavily_uso"] += 1
    salvar_controle(dados)
    print(f"[TAVILY] Uso {dados['tavily_uso']}/{MAX_TAVILY} hoje")
    return True

# ── CACHE (com limite para não crescer infinito) ─────────
CACHE_DECISAO = {}
CACHE_TAVILY  = {}
MAX_CACHE     = 500

def limpar_cache_se_cheio():
    if len(CACHE_DECISAO) > MAX_CACHE:
        CACHE_DECISAO.clear()
        print("[CACHE] CACHE_DECISAO limpo (limite atingido)")
    if len(CACHE_TAVILY) > MAX_CACHE:
        CACHE_TAVILY.clear()
        print("[CACHE] CACHE_TAVILY limpo (limite atingido)")

# ── PALAVRAS-CHAVE para decisão rápida ──────────────────
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

# ── ROUTER: decide se usa Tavily ─────────────────────────
def precisa_tavily(pergunta: str) -> bool:
    """
    Ordem de decisão (mais rápida → mais lenta):
    1. Cache — responde na hora se já foi decidido antes
    2. Palavras de bloqueio — bloqueia sem chamar nenhuma API
    3. Palavras-chave web — libera sem chamar nenhuma API
    4. GROQ decide (3 tokens, temperature=0)
    5. GEMINI decide se GROQ cair
    6. Bloqueia se ambos caírem
    """
    p = pergunta.lower().strip()
    limpar_cache_se_cheio()

    # 1. Cache
    if p in CACHE_DECISAO:
        print(f"[ROUTER] Cache: {'SIM' if CACHE_DECISAO[p] else 'NAO'}")
        return CACHE_DECISAO[p]

    # 2. Bloqueio por palavras-chave
    if any(x in p for x in PALAVRAS_BLOQUEIO):
        print("[ROUTER] Palavra de bloqueio — Tavily NAO")
        CACHE_DECISAO[p] = False
        return False

    # 3. Liberação por palavras-chave
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

    # 4. GROQ decide
    try:
        from groq import Groq
        api = next((a for a in APIS if a["tipo"] == "groq" and a["chave"]), None)
        if not api:
            raise Exception("Groq indisponivel")
        client = Groq(api_key=api["chave"])
        r = client.chat.completions.create(
            model=api["modelo"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3,
            temperature=0
        )
        decisao = r.choices[0].message.content.strip().upper() == "SIM"
        print(f"[ROUTER] GROQ decidiu: {'SIM' if decisao else 'NAO'}")
        CACHE_DECISAO[p] = decisao
        return decisao
    except Exception as e:
        print(f"[ROUTER] GROQ falhou: {e}")

    # 5. GEMINI decide
    try:
        api = next((a for a in APIS if a["tipo"] == "gemini" and a["chave"]), None)
        if not api:
            raise Exception("Gemini indisponivel")
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{api['modelo']}:generateContent?key={api['chave']}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=8
        )
        data = r.json()
        txt = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        decisao = txt.strip().upper() == "SIM"
        print(f"[ROUTER] GEMINI decidiu: {'SIM' if decisao else 'NAO'}")
        CACHE_DECISAO[p] = decisao
        return decisao
    except Exception as e:
        print(f"[ROUTER] GEMINI falhou: {e}")

    # 6. Ambos caíram — bloqueia
    print("[ROUTER] GROQ e GEMINI indisponiveis — Tavily BLOQUEADO")
    CACHE_DECISAO[p] = False
    return False

# ── BUSCA TAVILY (cache 10 min + limite de uso) ──────────
def buscar_tavily(query: str) -> str:
    if not tavily_client:
        return "Tavily nao configurado."

    agora = time.time()
    limpar_cache_se_cheio()

    # Cache de 10 minutos
    if query in CACHE_TAVILY:
        if agora - CACHE_TAVILY[query]["t"] < 600:
            print(f"[TAVILY] Cache hit: {query}")
            return CACHE_TAVILY[query]["r"]

    # Verifica limite de uso antes de gastar crédito
    if not pode_usar_tavily():
        return "Limite de buscas Tavily atingido nesta sessao."

    try:
        print(f"[TAVILY] Buscando: {query}")
        r = tavily_client.search(
            query=query,
            max_results=1,
            search_depth="basic",
            include_answer=True
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

# ── APRENDIZADO ──────────────────────────────────────────
MEMORIA_FILE = "aprendizado.json"

def carregar_aprendizado() -> dict:
    try:
        with open(MEMORIA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def salvar_aprendizado(dados: dict):
    try:
        with open(MEMORIA_FILE, "w") as f:
            json.dump(dados, f, indent=2)
    except Exception as e:
        print(f"[APREND] Erro ao salvar: {e}")

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
        raise Exception(f"{api['nome']} sem chave configurada")

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
        data = r.json()
        txt = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
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

    # ── Tarefas com Tavily ──
    if tarefa in ("buscar cotacao dolar", "buscar noticias tech"):
        queries = {
            "buscar cotacao dolar": "cotacao dolar hoje brasil real",
            "buscar noticias tech": "noticias tecnologia inteligencia artificial hoje",
        }
        query = queries[tarefa]

        if precisa_tavily(query):
            resultado = buscar_tavily(query)
        else:
            resultado = chamar_ia(
                tarefa,
                f"Execute sem dados da internet: '{tarefa}'. "
                "Se nao souber com certeza, diga que nao tem a informacao atual."
            )
        print(f"[{tarefa}] {resultado[:120]}")
        salvar_log(tarefa, resultado)
        return

    # ── Tarefas normais ──
    if tarefa == "mostrar hora":
        print(f"[HORA] {agora}")
        salvar_log(tarefa, agora)

    elif tarefa == "monitorar sistema":
        print(f"[SISTEMA] CPU: {cpu}% | Memoria: {mem}%")
        salvar_log(tarefa, f"CPU: {cpu}% | Mem: {mem}%")

    elif tarefa == "verificar sistema":
        resultado = chamar_ia(tarefa, f"CPU: {cpu}%, Memoria: {mem}%, Hora: {agora}. O sistema esta saudavel?")
        print(f"[VERIFICAR] {resultado}")
        salvar_log(tarefa, resultado)

    elif tarefa == "registrar atividade":
        salvar_log(tarefa, f"Atividade registrada as {agora}")
        print("[LOG] Atividade registrada")

    elif tarefa == "analisar memoria":
        try:
            with open("memoria.txt", "r", encoding="utf-8") as f:
                linhas = f.readlines()
            resultado = chamar_ia(tarefa, f"Tenho {len(linhas)} registros. Objetivo: {objetivo}. O que o agente deve fazer?")
            print(f"[ANALISE] {resultado}")
            salvar_log(tarefa, resultado)
        except FileNotFoundError:
            print("[MEMORIA] memoria.txt ainda nao existe.")

    elif tarefa == "limpar memoria":
        try:
            with open("memoria.txt", "w", encoding="utf-8") as f:
                f.write("")
            print("[MEMORIA] Limpa com sucesso.")
            salvar_log(tarefa, "Memoria limpa")
        except Exception as e:
            print(f"[MEMORIA] Erro: {e}")

    elif tarefa == "gerar relatorio":
        try:
            with open("memoria.txt", "r", encoding="utf-8") as f:
                linhas = f.readlines()
            resultado = chamar_ia(tarefa, f"Gere um resumo tecnico de {len(linhas)} registros de atividade do agente em nuvem.")
            with open("relatorio.txt", "w", encoding="utf-8") as rel:
                rel.write(f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}]\n{resultado}\n")
            print("[RELATORIO] Criado.")
            salvar_log(tarefa, resultado)
        except Exception as e:
            print(f"[RELATORIO] Erro: {e}")

    else:
        resultado = chamar_ia(tarefa, f"Execute: '{tarefa}'. Contexto: {contexto}")
        print(f"[IA] {resultado}")
        salvar_log(tarefa, resultado)

def salvar_log(tarefa: str, conteudo: str):
    """Salva em JSON — permite usar como memória inteligente no futuro."""
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
    """Mantém memoria.txt com no máximo 2000 linhas — guarda as últimas 1000."""
    try:
        with open("memoria.txt", "r", encoding="utf-8") as f:
            linhas = f.readlines()
        if len(linhas) > 2000:
            with open("memoria.txt", "w", encoding="utf-8") as f:
                f.writelines(linhas[-1000:])
            print(f"[MEMORIA] Log reduzido de {len(linhas)} para 1000 linhas")
    except:
        pass

def ler_memoria_decisao() -> dict:
    """
    Lê as últimas 100 entradas do memoria.txt e extrai padrões
    para influenciar decisões do agente — sem custo de API.

    Retorna:
      - tarefas_frequentes: tarefas que aparecem muito (possível loop)
      - tarefas_evitar:     tarefas que falharam recentemente
      - busca_recente:      se já buscou Tavily nas últimas entradas
    """
    resultado = {
        "tarefas_frequentes": [],
        "tarefas_evitar":     [],
        "busca_recente":      False,
    }
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

                # Conta frequência por tarefa
                contagem[tarefa] = contagem.get(tarefa, 0) + 1

                # Detecta falhas no resultado
                if any(x in texto for x in ["falhou", "erro", "nenhuma api", "indisponivel"]):
                    falhas[tarefa] = falhas.get(tarefa, 0) + 1

                # Detecta busca Tavily recente
                if tarefa in ("buscar cotacao dolar", "buscar noticias tech"):
                    resultado["busca_recente"] = True

            except:
                continue

        # Tarefas com mais de 30% das entradas = possível loop
        total = len(linhas)
        resultado["tarefas_frequentes"] = [
            t for t, n in contagem.items() if total > 0 and n / total > 0.3
        ]

        # Tarefas com 3+ falhas recentes = evitar por enquanto
        resultado["tarefas_evitar"] = [
            t for t, n in falhas.items() if n >= 3
        ]

        if resultado["tarefas_frequentes"] or resultado["tarefas_evitar"]:
            print(f"[MEMORIA] Frequentes: {resultado['tarefas_frequentes']} | Evitar: {resultado['tarefas_evitar']}")

    except:
        pass

    return resultado

def avaliar_tarefa_com_memoria(tarefa: str, memoria_decisao: dict) -> int:
    """Ajusta o peso da tarefa com base no que foi aprendido do log."""
    peso = avaliar_tarefa(tarefa)

    # Penaliza tarefa em loop
    if tarefa in memoria_decisao.get("tarefas_frequentes", []):
        peso -= 2

    # Penaliza tarefa que falhou muito
    if tarefa in memoria_decisao.get("tarefas_evitar", []):
        peso -= 3

    # Se já buscou Tavily recentemente, reduz prioridade de nova busca
    if memoria_decisao.get("busca_recente") and tarefa in ("buscar cotacao dolar", "buscar noticias tech"):
        peso -= 2

    return max(peso, 0)  # nunca negativo

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

def contar_registros() -> int:
    try:
        with open("memoria.txt", "r", encoding="utf-8") as f:
            return len(f.readlines())
    except:
        return 0

# ── LOOP PRINCIPAL ───────────────────────────────────────
print("=" * 52)
print("  AGENTE AUTONOMO EM NUVEM — VERSAO FINAL")
print(f"  Tavily : {'OK' if tavily_client else 'INDISPONIVEL'}")
print(f"  APIs   : {[a['nome'] for a in APIS]}")
print(f"  Limite Tavily: {MAX_TAVILY} buscas/dia (persiste entre reinicializacoes)")
print("=" * 52)

contador     = 0
objetivo     = random.choice(objetivos)
tarefas      = []
ultima_tarefa = None

print(f"[OBJETIVO] Inicial: {objetivo}\n")

while True:
    try:
        contador  += 1
        agora      = datetime.now().strftime("%H:%M:%S")
        registros  = contar_registros()

        # Troca de objetivo a cada 20 ciclos
        if contador % 20 == 0:
            objetivo = random.choice(objetivos)
            print(f"\n[OBJETIVO] Novo: {objetivo}")

        print(f"\n----- Ciclo {contador} | {agora} -----")
        print(f"Objetivo : {objetivo}")
        controle = carregar_controle()
        uso_hoje = controle.get("tavily_uso", 0)
        print(f"Registros: {registros} | Tavily usado: {uso_hoje}/{MAX_TAVILY}")

        cpu, mem = estado_sistema()
        print(f"CPU: {cpu}% | Mem: {mem}%")

        limitar_memoria()

        # Lê padrões do log para influenciar decisões (sem custo de API)
        memoria_decisao = ler_memoria_decisao()

        # Planeja tarefas se a fila estiver vazia
        if not tarefas:
            tarefas.extend(planejar_tarefas(objetivo))

        # Emergência por recursos
        if cpu > 70:
            tarefas.append("analisar memoria")
        if mem > 70:
            tarefas.append("limpar memoria")

        # Busca cotação a cada 30 ciclos
        if contador % 30 == 0:
            tarefas.append("buscar cotacao dolar")

        # Variedade
        tarefas.append(random.choice(tarefas_possiveis))

        # Executa tarefa de maior prioridade — pesos ajustados pelo log
        melhor = max(tarefas, key=lambda t: avaliar_tarefa_com_memoria(t, memoria_decisao))

        # Evita repetir a mesma tarefa duas vezes seguidas
        if melhor == ultima_tarefa and len(tarefas) > 1:
            tarefas_sem_repetir = [t for t in tarefas if t != melhor]
            melhor = max(tarefas_sem_repetir, key=lambda t: avaliar_tarefa_com_memoria(t, memoria_decisao))
            print(f"[SKIP] Evitando repeticao — escolhendo: {melhor}")

        print(f"[TAREFA] Executando: {melhor}")
        executar_tarefa(melhor, objetivo, registros, cpu, mem)
        tarefas.remove(melhor)
        ultima_tarefa = melhor

        # Log do ciclo
        with open("memoria.txt", "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "time": agora, "ciclo": contador, "tarefa": melhor
            }, ensure_ascii=False) + "\n")

        # Sleep adaptativo: 15s normal, 30s se CPU alta
        sleep_time = 30 if cpu > 50 else 15
        print(f"[CICLO] Aguardando {sleep_time}s...")
        time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[AGENTE] Encerrado pelo usuario.")
        break
    except Exception as e:
        print(f"[ERRO] {e}")
        time.sleep(15)
