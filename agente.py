import time
import random
import psutil
import requests
import json
import os
from datetime import datetime

# ── CHAVES ───────────────────────────────────────────────
APIS = [
    {"nome": "Groq-1", "tipo": "groq", "chave": os.environ.get("GROQ_API_KEY", ""), "modelo": "llama-3.1-8b-instant"},
    {"nome": "Gemini", "tipo": "gemini", "chave": "SUA_CHAVE_GEMINI", "modelo": "gemini-1.5-flash"},
]

# ── APRENDIZADO ───────────────────────────────────────────
MEMORIA_FILE = "aprendizado.json"

def carregar_aprendizado():
    try:
        with open(MEMORIA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def salvar_aprendizado(dados):
    with open(MEMORIA_FILE, "w") as f:
        json.dump(dados, f, indent=2)

def registrar_resultado(api_nome, tarefa, sucesso, tempo):
    dados = carregar_aprendizado()
    chave = f"{api_nome}:{tarefa}"
    if chave not in dados:
        dados[chave] = {"sucesso": 0, "falha": 0, "tempo_total": 0, "usos": 0}
    dados[chave]["usos"] += 1
    dados[chave]["tempo_total"] += tempo
    if sucesso:
        dados[chave]["sucesso"] += 1
    else:
        dados[chave]["falha"] += 1
    salvar_aprendizado(dados)

def melhor_api_para(tarefa):
    dados = carregar_aprendizado()
    melhor = None
    melhor_score = -1
    for api in APIS:
        chave = f"{api['nome']}:{tarefa}"
        if chave in dados:
            d = dados[chave]
            if d["usos"] > 0:
                taxa_sucesso = d["sucesso"] / d["usos"]
                tempo_medio = d["tempo_total"] / d["usos"]
                score = taxa_sucesso * 100 - tempo_medio
                if score > melhor_score:
                    melhor_score = score
                    melhor = api
    return melhor or APIS[0]

# ── CHAMADA IA ────────────────────────────────────────────
def chamar_ia(tarefa, system_prompt, user_prompt, max_tokens=200):
    api = melhor_api_para(tarefa)
    inicio = time.time()
    try:
        if api["tipo"] == "groq":
            resultado = _groq(api, system_prompt, user_prompt, max_tokens)
        elif api["tipo"] == "gemini":
            resultado = _gemini(api, system_prompt, user_prompt)
        tempo = time.time() - inicio
        registrar_resultado(api["nome"], tarefa, True, tempo)
        print(f"[{api['nome']}] ({tempo:.1f}s)")
        return resultado
    except Exception as e:
        tempo = time.time() - inicio
        registrar_resultado(api["nome"], tarefa, False, tempo)
        print(f"[{api['nome']}] FALHOU: {e}")
        # tenta próxima api
        for alt in APIS:
            if alt["nome"] != api["nome"]:
                try:
                    if alt["tipo"] == "groq":
                        return _groq(alt, system_prompt, user_prompt, max_tokens)
                    elif alt["tipo"] == "gemini":
                        return _gemini(alt, system_prompt, user_prompt)
                except:
                    continue
        return "Nenhuma API disponível."

def _groq(api, system_prompt, user_prompt, max_tokens):
    from groq import Groq
    client = Groq(api_key=api["chave"])
    r = client.chat.completions.create(
        model=api["modelo"],
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        max_tokens=max_tokens
    )
    return r.choices[0].message.content.strip()

def _gemini(api, system_prompt, user_prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{api['modelo']}:generateContent?key={api['chave']}"
    r = requests.post(url, json={"contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}]}, timeout=15)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

# ── TAREFAS ───────────────────────────────────────────────
objetivos = [
    "otimizar desempenho do sistema",
    "monitorar recursos e memória",
    "manter o sistema estável",
    "analisar e limpar dados antigos",
    "gerar relatórios de atividade"
]

tarefas_possiveis = [
    "monitorar sistema", "limpar memoria", "gerar relatorio",
    "verificar sistema", "analisar memoria", "registrar atividade", "mostrar hora"
]

def estado_sistema():
    cpu = round(psutil.cpu_percent(interval=1), 1)
    mem = round(psutil.virtual_memory().percent, 1)
    return cpu, mem

def planejar_tarefas(objetivo):
    try:
        resposta = chamar_ia(
            "planejar",
            "Responda APENAS com uma lista Python válida de strings, sem explicações.",
            f"Objetivo: '{objetivo}'. Escolha 3 tarefas: {tarefas_possiveis}",
            max_tokens=100
        )
        tarefas = eval(resposta)
        if isinstance(tarefas, list):
            return [t.lower().strip() for t in tarefas]
    except:
        pass
    return ["monitorar sistema", "registrar atividade", "verificar sistema"]

def executar_tarefa(tarefa, objetivo, registros, cpu, mem):
    contexto = f"Objetivo: {objetivo} | Registros: {registros} | CPU: {cpu}% | Mem: {mem}%"
    resultado = chamar_ia(
        tarefa,
        "Você é um agente autônomo. Responda curto e direto (máximo 2 frases).",
        f"Execute: '{tarefa}'. Contexto: {contexto}"
    )
    print("Analise:", resultado)

def avaliar_tarefa(tarefa):
    pesos = {
        "monitorar sistema": 4, "limpar memoria": 3, "gerar relatorio": 3,
        "verificar sistema": 3, "analisar memoria": 2, "registrar atividade": 2, "mostrar hora": 1
    }
    return pesos.get(tarefa, 0)

def contar_registros():
    try:
        with open("memoria.txt", "r", encoding="utf-8") as f:
            return len(f.readlines())
    except:
        return 0

# ── LOOP PRINCIPAL ────────────────────────────────────────
contador = 0
objetivo = random.choice(objetivos)
tarefas = []
print("Agente autônomo iniciado.")
print("Objetivo:", objetivo)

while True:
    try:
        contador += 1
        agora = datetime.now().strftime("%H:%M:%S")
        registros = contar_registros()

        if contador % 20 == 0:
            objetivo = random.choice(objetivos)

        print(f"\n----- Ciclo {contador} | {agora} -----")
        print("Objetivo:", objetivo)
        print("Registros:", registros)

        cpu, mem = estado_sistema()
        print(f"CPU: {cpu}% | Mem: {mem}%")

        if not tarefas:
            tarefas.extend(planejar_tarefas(objetivo))
        if cpu > 70:
            tarefas.append("analisar memoria")
        if mem > 70:
            tarefas.append("limpar memoria")

        tarefas.append(random.choice(tarefas_possiveis))
        melhor = max(tarefas, key=avaliar_tarefa)
        print("Executando:", melhor)
        executar_tarefa(melhor, objetivo, registros, cpu, mem)
        tarefas.remove(melhor)

        with open("memoria.txt", "a", encoding="utf-8") as f:
            f.write(f"[{agora}] Ciclo {contador} | tarefa: {melhor}\n")

        time.sleep(5)

    except KeyboardInterrupt:
        print("\nAgente encerrado.")
        break
    except Exception as e:
        print("Erro:", e)
        time.sleep(5)
