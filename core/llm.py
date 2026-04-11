import time
import os
from integrations.groq_client import chamar_groq, proxima_groq_key, GROQ_KEYS
from integrations.google_client import chamar_google, google_cliente
from integrations.sambanova_cliente import consultar_sambanova_chat
from core.logger import info, warn, erro

SAMBANOVA_KEY = os.getenv("SAMBANOVA_API_KEY")

# ── CONTADORES DE CUSTO ───────────────────────────────────────────────────────
_contadores = {
    "groq_calls": 0,
    "google_calls": 0,
    "sambanova_calls": 0,
    "exa_calls": 0,
    "vazamentos_descartados": 0,
    "total_calls": 0,
    # 18-A — telemetria de tokens (só GROQ retorna usage)
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
}

def get_contadores():
    c = dict(_contadores)
    # cota restante estimada: 3 chaves × 100k = 300k/dia
    usados = c["total_tokens"]
    cota_total = len(GROQ_KEYS) * 100_000
    c["cota_restante_estimada"] = max(0, cota_total - usados)
    c["cota_usada_pct"] = round(usados / cota_total * 100, 1) if cota_total else 0
    return c

def resetar_contadores():
    for k in _contadores:
        _contadores[k] = 0

# ── STATUS DAS APIs ───────────────────────────────────────────────────────────
status_apis = {
    "groq":      {"ativa": bool(GROQ_KEYS),      "falhas": 0},
    "google":    {"ativa": bool(google_cliente),  "falhas": 0},
    "sambanova": {"ativa": bool(SAMBANOVA_KEY),   "falhas": 0},
}

MAX_FALHAS = 3
MAX_RESETS = 2
api_atual  = {"nome": "groq"}

_groq_chaves_esgotadas = {"n": 0}
_groq_bloqueado_ate    = 0.0   # timestamp até quando GROQ está bloqueado

def _limite_groq(erro_str: str) -> bool:
    s = str(erro_str).lower()
    return (
        "tokens per day" in s or "tpd" in s or "per day" in s or
        "rate limit" in s or "rate_limit" in s or "429" in s
    )

def registrar_falha(nome_api, e):
    erro_str = str(e)
    if nome_api == "groq" and _limite_groq(erro_str):
        if _groq_chaves_esgotadas["n"] < len(GROQ_KEYS) - 1:
            _groq_chaves_esgotadas["n"] += 1
            proxima_groq_key()
            status_apis["groq"]["ativa"] = True
            status_apis["groq"]["falhas"] = 0
            warn("LLM", f"GROQ limite — trocando para chave {_groq_chaves_esgotadas['n'] + 1}/{len(GROQ_KEYS)}")
        else:
            status_apis["groq"]["ativa"] = False
            global _groq_bloqueado_ate
            _groq_bloqueado_ate = time.time() + 1800  # 30 min
            warn("LLM", "GROQ todas as chaves esgotadas — bloqueado por 30min, usando fallback")
        return
    status_apis[nome_api]["falhas"] += 1
    if status_apis[nome_api]["falhas"] >= MAX_FALHAS:
        status_apis[nome_api]["ativa"] = False
        warn("LLM", f"{nome_api.upper()} desativada apos {MAX_FALHAS} falhas")
        if nome_api == "groq" and len(GROQ_KEYS) > 1:
            proxima_groq_key()
            status_apis["groq"]["ativa"] = True
            status_apis["groq"]["falhas"] = 0

def resetar_falhas(nome_api):
    status_apis[nome_api]["falhas"] = 0
    status_apis[nome_api]["ativa"] = True

# ── EXA COMO FALLBACK DE BUSCA ────────────────────────────────────────────────

def _injetar_exa_se_disponivel(msgs: list, query: str = "") -> list:
    try:
        from integrations.exa_client import buscar_exa, exa_disponivel
        if not exa_disponivel() or not query:
            return msgs
        resultado = buscar_exa(query)
        if not resultado:
            return msgs
        msgs_com_exa = list(msgs)
        contexto_exa = f"[DADOS EXA — use como fonte para responder]\n{resultado}"
        if msgs_com_exa and msgs_com_exa[0].get("role") == "system":
            msgs_com_exa[0] = {
                "role": "system",
                "content": msgs_com_exa[0]["content"] + f"\n\n{contexto_exa}",
            }
        else:
            msgs_com_exa.insert(0, {"role": "system", "content": contexto_exa})
        info("LLM", "EXA: contexto injetado")
        return msgs_com_exa
    except Exception as e:
        warn("LLM", f"EXA inject falhou: {e}")
        return msgs

# ── FUNCAO PRINCIPAL ──────────────────────────────────────────────────────────

def pensar(msgs, max_tokens=400, exa_query: str = "", pergunta: str = ""):
    """
    exa_query: injeta resultado EXA no contexto antes de chamar o LLM.
    pergunta: usada pelo valuator para avaliar a resposta (sem custo de API).
    """
    if exa_query:
        msgs = _injetar_exa_se_disponivel(msgs, exa_query)

    resets = 0
    while resets <= MAX_RESETS:
        disponiveis = [a for a in ["groq", "google", "sambanova"] if status_apis[a]["ativa"]]
        # Pula GROQ se ainda está no período de bloqueio
        if time.time() < _groq_bloqueado_ate and "groq" in disponiveis:
            disponiveis.remove("groq")
        if not disponiveis:
            if resets >= MAX_RESETS:
                erro("LLM", f"Limite de {MAX_RESETS} resets atingido — desistindo")
                break
            resets += 1
            warn("LLM", f"Todas as APIs falharam — reset {resets}/{MAX_RESETS}")
            for nome in status_apis:
                resetar_falhas(nome)
            _groq_chaves_esgotadas["n"] = 0
            time.sleep(2)
            continue

        for nome_api in disponiveis:
            if not status_apis[nome_api]["ativa"]:
                continue
            try:
                info("API", f"Chamando {nome_api.upper()}...")
                if nome_api == "groq":
                    # chamar_groq agora retorna (texto, uso)
                    resposta, uso = chamar_groq(msgs, max_tokens)
                    _contadores["groq_calls"] += 1
                    # 18-A — acumula tokens da sessão
                    _contadores["prompt_tokens"]     += uso.prompt_tokens
                    _contadores["completion_tokens"] += uso.completion_tokens
                    _contadores["total_tokens"]      += uso.total_tokens
                    info("LLM", (
                        f"Sessão: {_contadores['groq_calls']} chamadas GROQ | "
                        f"{_contadores['total_tokens']:,} tokens usados | "
                        f"~{max(0, len(GROQ_KEYS)*100_000 - _contadores['total_tokens']):,} restantes"
                    ))
                elif nome_api == "google":
                    resposta = chamar_google(msgs)
                    _contadores["google_calls"] += 1
                else:
                    resposta, _ = consultar_sambanova_chat(msgs, max_tokens)
                    _contadores["sambanova_calls"] += 1
                    warn("LLM", "Usando SambaNova (Meta-Llama-3.3-70B) como fallback")
                _contadores["total_calls"] += 1

                resetar_falhas(nome_api)
                api_atual["nome"] = nome_api

                if not resposta or not resposta.strip():
                    raise Exception("Resposta vazia")

                info("API", f"{nome_api.upper()} respondeu: {resposta[:80]}...")

                # ── LEAK CHECK — só vazamento, valuator completo fica no pipeline ──
                try:
                    from core.valuator import _detectar_vazamento
                    if _detectar_vazamento(resposta, pergunta or "", "internal"):
                        warn("VALUATOR", "Vazamento detectado — descartando resposta")
                        raise Exception("vazamento_detectado")
                except ImportError:
                    pass
                # ── FIM LEAK CHECK ────────────────────────────────────────────

                return resposta, nome_api

            except Exception as e:
                if "vazamento_detectado" in str(e):
                    erro("API", "Resposta descartada por vazamento")
                    _contadores["vazamentos_descartados"] += 1
                    break
                registrar_falha(nome_api, e)
                erro("API", f"{nome_api.upper()} falhou: {e}")
                if nome_api == "groq" and status_apis["groq"]["ativa"]:
                    break
        else:
            break

    return "Estou com instabilidade nas APIs agora. Tente novamente em alguns segundos.", "nenhuma"