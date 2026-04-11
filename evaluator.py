"""
FASE 14 — Suite de Avaliação com rate limit robusto
Uso:
  python evaluator.py                          # completo (50 perguntas)
  python evaluator.py rapido                  # 1 por categoria (7 perguntas)
  python evaluator.py safe                    # modo conservador (sleep=20s, retry=2)
  python evaluator.py categoria:memoria_apis
"""

import json
import os
import sys
import time
import re
import hashlib
import requests
import itertools
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# CONFIG
FROZEN_FILE         = "avaliacao_frozen.json"
RESULTADOS_FILE     = "resultados_avaliacao.json"
EVAL_CACHE_FILE     = "eval_cache.json"
GROQ_KEYS           = [k for k in [os.getenv("GROQ_API_KEY"), os.getenv("GROQ_API_KEY_2"), os.getenv("GROQ_API_KEY_3")] if k]
GOOGLE_KEY          = os.getenv("GOOGLE_API_KEY") or os.getenv("CHAVE_API_DO_GOOGLE")
MODELO_JUDGE        = "llama-3.3-70b-versatile"
MODELO_FALLBACK     = "gemini-2.0-flash"
THRESHOLD_REGRESSAO = 0.10

# Teto de chamadas LLM por sessão — evita cascata de rate limit
MAX_LLM_CALLS_SESSAO = 120
_llm_calls_sessao    = {"n": 0}

# Modo safe
MODO_SAFE  = False
SLEEP_BASE = 15
SLEEP_SAFE = 20
MAX_RETRY  = 3

# Estado global de rate limit
_bloqueio_global = {"ativo": False, "desde": 0, "contagem": 0}
_key_cycle       = itertools.cycle(GROQ_KEYS) if GROQ_KEYS else iter([])

def log(msg, nivel="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}][{nivel}][EVAL] {msg}", flush=True)

# DETECÇÃO DE BLOQUEIO GLOBAL
def _registrar_falha_429():
    _bloqueio_global["contagem"] += 1
    if _bloqueio_global["contagem"] >= 3 and not _bloqueio_global["ativo"]:
        _bloqueio_global["ativo"]  = True
        _bloqueio_global["desde"]  = time.time()
        log("Bloqueio global detectado — cooldown de 30s", "WARN")
        try:
            time.sleep(30)
        except KeyboardInterrupt:
            log("Cooldown interrompido pelo usuario", "WARN")
        _bloqueio_global["ativo"]    = False
        _bloqueio_global["contagem"] = 0
        log("Cooldown encerrado — retomando", "INFO")

def _proxima_chave():
    try:
        return next(_key_cycle)
    except StopIteration:
        return GROQ_KEYS[0] if GROQ_KEYS else None

def _teto_atingido() -> bool:
    """Retorna True se o teto de chamadas da sessão foi atingido."""
    if _llm_calls_sessao["n"] >= MAX_LLM_CALLS_SESSAO:
        log(f"Teto de {MAX_LLM_CALLS_SESSAO} chamadas LLM atingido — usando cache/string para o restante", "WARN")
        return True
    return False

# LLM COM RODIZIO E BACKOFF
def _chamar_groq_com_backoff(prompt, max_tokens=40):
    if not GROQ_KEYS or _teto_atingido():
        return ""
    from groq import Groq
    backoffs = [5, 10, 15]
    _llm_calls_sessao["n"] += 1
    for tentativa in range(MAX_RETRY):
        chave = _proxima_chave()
        if not chave:
            break
        try:
            client = Groq(api_key=chave)
            r = client.chat.completions.create(
                model=MODELO_JUDGE,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=0
            )
            _bloqueio_global["contagem"] = 0
            return r.choices[0].message.content.strip()
        except Exception as e:
            msg = str(e).lower()
            if "rate_limit" in msg or "429" in msg or "per day" in msg or "per minute" in msg:
                espera = backoffs[min(tentativa, len(backoffs)-1)]
                log(f"GROQ limite (tentativa {tentativa+1}/{MAX_RETRY}) — aguardando {espera}s", "WARN")
                _registrar_falha_429()
                time.sleep(espera)
            else:
                log(f"GROQ erro: {str(e)[:80]}", "WARN")
                break
    # Fallback Google
    if GOOGLE_KEY:
        time.sleep(10)
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO_FALLBACK}:generateContent?key={GOOGLE_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=20
            )
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            log(f"Google fallback falhou: {str(e)[:80]}", "WARN")
    return ""

# CACHE DE AVALIAÇÃO
def _carregar_eval_cache():
    try:
        with open(EVAL_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _salvar_eval_cache(cache):
    try:
        with open(EVAL_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _versao_prompt():
    """Hash MD5 do prompt atual — invalida cache quando conteúdo muda, não só tamanho."""
    try:
        sys.path.insert(0, os.path.abspath("."))
        from core.prompt import PROMPT_BASE
        return hashlib.md5(PROMPT_BASE.encode("utf-8")).hexdigest()[:8]
    except Exception:
        return "0"

# OBTER RESPOSTA DO AGENTE
def _obter_via_import(pergunta):
    if _teto_atingido():
        return ""
    sys.path.insert(0, os.path.abspath("."))
    # Prompt minimo — so identidade, sem blocos de regras
    # PROMPT_BASE completo custa 3000+ tokens por chamada e esgota cota
    try:
        import json as _json, os as _os
        caminho = _os.path.join(_os.path.abspath("."), "identidade_agente.json")
        with open(caminho, "r", encoding="utf-8") as f:
            id_ = _json.load(f)
        linhas = [
            f"Voce e um agente autonomo criado por {id_.get("criador","Eduardo Conceicao")} de {id_.get("local_criador","Atibaia-SP")}.",
            "Responda sempre em portugues brasileiro. Seja direto e especifico.",
        ]
        for e in id_.get("essencia", []):
            linhas.append(f"- {e}")
        pub = id_.get("autodescricao_publica", {})
        if pub.get("tecnica"):
            linhas.append(pub["tecnica"])
        system_prompt = "\n".join(linhas)
    except Exception:
        system_prompt = "Voce e um agente de IA pessoal criado por Eduardo Conceicao de Atibaia-SP. Responda em portugues."
    prompt_completo = f"{system_prompt}\n\nPergunta: {pergunta}"
    return _chamar_groq_com_backoff(prompt_completo, max_tokens=150)

def _obter_via_http(pergunta, url):
    url = url.rstrip("/")
    for endpoint, payload in [
        (f"{url}/responder", {"pergunta": pergunta}),
        (f"{url}/tarefa",    {"tarefa": "responder", "dados": {"pergunta": pergunta}}),
    ]:
        try:
            r = requests.post(endpoint, json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                return data.get("resposta", data.get("resultado", str(data)))
        except Exception:
            continue
    return ""

def obter_resposta_agente(pergunta, url_agente=None):
    if url_agente:
        return _obter_via_http(pergunta, url_agente)
    return _obter_via_import(pergunta)

# AVALIADORES
def avaliar_contem_palavra(resposta, palavras):
    r = resposta.lower()
    for palavra in palavras:
        if palavra.lower() in r:
            return True, f"Encontrou '{palavra}'"
    return False, f"Nenhuma de {palavras} encontrada"

def avaliar_contem_numero(resposta, numero):
    padrao = r'\b' + re.escape(str(numero)) + r'\b'
    if re.search(padrao, resposta):
        return True, f"Numero '{numero}' encontrado"
    return False, f"Numero '{numero}' nao encontrado"

def avaliar_llm_judge(resposta, criterio):
    if not resposta.strip():
        return False, "Resposta vazia"
    prompt = (
        f"Criterio: {criterio}\n\n"
        f"Resposta do agente: {resposta[:400]}\n\n"
        f"O criterio foi atendido? Responda SIM ou NAO + justificativa em 10 palavras."
    )
    # max_tokens=40 — só precisa SIM/NAO + 10 palavras
    julgamento = _chamar_groq_com_backoff(prompt, max_tokens=40)
    if not julgamento:
        return False, "Judge sem resposta"
    passou = julgamento.upper().startswith("SIM")
    return passou, julgamento

def avaliar_pergunta(pergunta_obj, resposta):
    tipo = pergunta_obj.get("tipo_avaliacao", "contem_palavra")
    if tipo == "contem_palavra":
        passou, detalhe = avaliar_contem_palavra(resposta, pergunta_obj.get("palavras_chave", []))
    elif tipo == "contem_numero":
        passou, detalhe = avaliar_contem_numero(resposta, pergunta_obj.get("numero_esperado", ""))
    elif tipo == "llm_judge":
        passou, detalhe = avaliar_llm_judge(resposta, pergunta_obj.get("criterio_llm", ""))
    else:
        passou, detalhe = False, f"Tipo desconhecido: {tipo}"
    return {"id": pergunta_obj["id"], "passou": passou, "detalhe": detalhe,
            "peso": pergunta_obj.get("peso", 1.0), "resposta": resposta[:200]}

# CARREGAR FROZEN
def carregar_frozen(caminho=None):
    caminho = caminho or FROZEN_FILE
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log(f"Arquivo nao encontrado: {caminho}", "ERRO"); sys.exit(1)
    except json.JSONDecodeError as e:
        log(f"JSON invalido: {e}", "ERRO"); sys.exit(1)

# SELECIONAR PERGUNTAS
def selecionar_perguntas(frozen, modo):
    todas = frozen["perguntas"]
    if modo in ("completo", "safe"):
        return todas
    if modo == "rapido":
        por_cat = {}
        for p in todas:
            cat = p["categoria"]
            if cat not in por_cat or p["peso"] > por_cat[cat]["peso"]:
                por_cat[cat] = p
        return list(por_cat.values())
    if modo.startswith("categoria:"):
        cat = modo.split(":", 1)[1]
        selecionadas = [p for p in todas if p["categoria"] == cat]
        if not selecionadas:
            log(f"Categoria '{cat}' nao encontrada", "ERRO"); sys.exit(1)
        return selecionadas
    log(f"Modo desconhecido: {modo}", "ERRO"); sys.exit(1)

# EXECUTAR SUITE
def executar_suite(url_agente=None, modo="completo", caminho_frozen=None):
    global MODO_SAFE
    if modo == "safe":
        MODO_SAFE = True
    sleep = SLEEP_SAFE if MODO_SAFE else SLEEP_BASE

    frozen    = carregar_frozen(caminho_frozen)
    perguntas = selecionar_perguntas(frozen, modo)
    total     = len(perguntas)

    eval_cache    = _carregar_eval_cache()
    versao_prompt = _versao_prompt()
    puladas       = 0

    log(f"Iniciando — modo={modo} | {total} perguntas | {len(GROQ_KEYS)} chaves | sleep={sleep}s | cache_v={versao_prompt}")
    log(f"Tempo estimado: ~{total * (sleep + 5) // 60 + 1} min")
    log(f"Teto LLM sessao: {MAX_LLM_CALLS_SESSAO} chamadas")
    print("-" * 60)

    resultados_por_categoria = {}
    resultados_detalhados    = []
    inicio_total             = time.time()

    for i, pergunta_obj in enumerate(perguntas, 1):
        cat       = pergunta_obj["categoria"]
        cache_key = f"{versao_prompt}:{pergunta_obj['id']}"

        # Cache hit — só aprova se o hash do prompt é o mesmo
        if cache_key in eval_cache and eval_cache[cache_key].get("passou"):
            resultado = eval_cache[cache_key]
            print(f"[{i:02d}/{total}] {pergunta_obj['id']} [CACHE] — {resultado['detalhe'][:50]}")
            puladas += 1
        else:
            print(f"[{i:02d}/{total}] {pergunta_obj['id']} ({cat})", end=" ", flush=True)
            inicio   = time.time()
            resposta = obter_resposta_agente(pergunta_obj["pergunta"], url_agente)
            tempo_r  = round(time.time() - inicio, 2)
            resultado = avaliar_pergunta(pergunta_obj, resposta)
            resultado["tempo_resposta"] = tempo_r
            simbolo = "OK" if resultado["passou"] else "XX"
            print(f"[{simbolo}] ({tempo_r}s) — {resultado['detalhe'][:60]}")

            if resultado["passou"]:
                eval_cache[cache_key] = resultado
                _salvar_eval_cache(eval_cache)

        resultados_detalhados.append(resultado)
        if cat not in resultados_por_categoria:
            resultados_por_categoria[cat] = {"passou": 0, "total": 0, "peso_total": 0.0, "peso_passou": 0.0}
        resultados_por_categoria[cat]["total"]      += 1
        resultados_por_categoria[cat]["peso_total"] += resultado["peso"]
        if resultado["passou"]:
            resultados_por_categoria[cat]["passou"]      += 1
            resultados_por_categoria[cat]["peso_passou"] += resultado["peso"]

        if i < total and cache_key not in eval_cache:
            time.sleep(sleep)

    tempo_total = round(time.time() - inicio_total, 1)
    if puladas:
        log(f"{puladas} perguntas puladas por cache")
    log(f"Total chamadas LLM nesta sessao: {_llm_calls_sessao['n']}")

    peso_total_geral  = sum(r["peso_total"]  for r in resultados_por_categoria.values())
    peso_passou_geral = sum(r["peso_passou"] for r in resultados_por_categoria.values())
    score_global = round(peso_passou_geral / peso_total_geral, 4) if peso_total_geral > 0 else 0.0

    scores_por_categoria = {
        cat: round(v["peso_passou"] / v["peso_total"], 4) if v["peso_total"] > 0 else 0.0
        for cat, v in resultados_por_categoria.items()
    }

    execucao = {
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"), "modo": modo,
        "total_perguntas": total, "score_global": score_global,
        "scores_por_categoria": scores_por_categoria,
        "passou_global": score_global >= 0.70,
        "tempo_total_segundos": tempo_total, "detalhes": resultados_detalhados,
    }
    _imprimir_relatorio(execucao, resultados_por_categoria)
    return execucao

def _imprimir_relatorio(execucao, por_categoria):
    print("\n" + "=" * 60)
    print(f"  RESULTADO DA AVALIACAO — {execucao['data']}")
    print("=" * 60)
    status = "OK" if execucao["passou_global"] else "ABAIXO DE 70%"
    print(f"  Score global : {execucao['score_global']:.1%}  [{status}]")
    print(f"  Tempo total  : {execucao['tempo_total_segundos']}s")
    print(f"  Modo         : {execucao['modo']}")
    print()
    print("  Por categoria:")
    for cat, score in execucao["scores_por_categoria"].items():
        v = por_categoria.get(cat, {})
        barra = "#" * int(score * 20) + "." * (20 - int(score * 20))
        print(f"    {cat:<22} [{barra}] {score:.0%} ({v.get('passou',0)}/{v.get('total',0)})")
    print("=" * 60)

def salvar_resultado(execucao, caminho=None):
    caminho = caminho or RESULTADOS_FILE
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            historico = json.load(f)
    except Exception:
        historico = {"meta": {"baseline_score": None, "melhor_score": 0.0, "ultimo_score": 0.0, "total_execucoes": 0}, "execucoes": []}

    meta = historico["meta"]
    if meta["baseline_score"] is None and execucao["modo"] == "completo":
        meta["baseline_score"] = execucao["score_global"]
        log(f"Baseline definido: {execucao['score_global']:.1%}")

    regressao = None
    if meta["ultimo_score"] > 0 and execucao["modo"] == "completo":
        queda = meta["ultimo_score"] - execucao["score_global"]
        if queda >= THRESHOLD_REGRESSAO:
            regressao = {"alerta": f"Queda de {queda:.1%}", "score_anterior": meta["ultimo_score"], "score_atual": execucao["score_global"]}
            log(f"REGRESSAO DETECTADA: {regressao['alerta']}", "WARN")

    meta["total_execucoes"] += 1
    meta["ultimo_score"]     = execucao["score_global"]
    if execucao["score_global"] > meta["melhor_score"]:
        meta["melhor_score"] = execucao["score_global"]
        log(f"Novo recorde: {execucao['score_global']:.1%}")

    execucao_resumida = {k: v for k, v in execucao.items() if k != "detalhes"}
    if regressao:
        execucao_resumida["regressao"] = regressao
    historico["execucoes"].append(execucao_resumida)
    if len(historico["execucoes"]) > 30:
        historico["execucoes"] = historico["execucoes"][-30:]

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)
    log(f"Resultado salvo em {caminho}")
    return execucao_resumida

if __name__ == "__main__":
    args       = sys.argv[1:]
    url_agente = None
    modo       = "completo"

    for arg in args:
        if arg.startswith("http"):
            url_agente = arg
        elif arg in ("completo", "rapido", "safe") or arg.startswith("categoria:"):
            modo = arg

    if not args:
        print("Uso:")
        print("  python evaluator.py                         # completo (50 perguntas)")
        print("  python evaluator.py rapido                  # 1 por categoria")
        print("  python evaluator.py safe                    # conservador (sleep=20s)")
        print("  python evaluator.py categoria:memoria_apis")
        print()

    execucao  = executar_suite(url_agente=url_agente, modo=modo)
    resultado = salvar_resultado(execucao)
    if resultado.get("regressao"):
        sys.exit(2)