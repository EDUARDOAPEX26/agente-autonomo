"""
core/consensus_checker.py
Tri-source — busca em ate 3 fontes e devolve consenso para o valuator.
Nao substitui o valuator — alimenta ele com contexto.

Fase 16-B: _extrair_fato agora e local (zero LLM).
Extrai numeros, moedas, temperaturas e datas direto do snippet via regex.

Retorna:
{
    "resposta": str,
    "fontes":   list[str],
    "consenso": int   # 0, 1, 2 ou 3
}
"""

import re
import unicodedata
from difflib import SequenceMatcher
from core.logger import info, warn, erro


# ── SIMILARIDADE ──────────────────────────────────────────────────────────────
THRESHOLD_SIMILARIDADE = 0.85

# ── PADROES FACTUAIS — extraidos sem LLM ─────────────────────────────────────
_PADROES_FATO = [
    r"(?:US\$|R\$|\$|€|£)\s*[\d.,]+",
    r"\d+[\.,]?\d*\s*°[CcFf]",
    r"\d+[\.,]?\d*\s*graus?\s*(?:celsius|fahrenheit)?",
    r"\d+[\.,]?\d*\s*%",
    r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}",
    r"(?:fechou|vale|esta|custa|subiu|caiu|atingiu)\s+(?:em\s+)?[\d.,]+",
    # Número com separador de milhar: 68,155.64 | 358.040,16 | 68.155
    r"\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?\b",
    # Número grande sem separador: 68155 | 360000
    r"\b\d{5,}\b",
]


def _normalizar(texto: str) -> str:
    t = texto.lower().strip()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s%$.,°]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _extrair_fato_local(texto: str) -> str:
    """
    Extrai fato factual do snippet sem chamar LLM.
    Prioriza: moeda > temperatura > percentual > numero > primeiras palavras.
    """
    for padrao in _PADROES_FATO:
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            inicio = max(0, match.start() - 20)
            fim    = min(len(texto), match.end() + 20)
            trecho = texto[inicio:fim].strip()
            return _normalizar(trecho)

    return _normalizar(texto[:150])


def _extrair_fato(resultado: dict, llm=None) -> str:
    snippet = resultado.get("snippet", "") or resultado.get("text", "") or ""
    title   = resultado.get("title", "") or ""
    texto   = (title + " " + snippet).strip()
    if not texto:
        return ""
    return _extrair_fato_local(texto)


def _extrair_numero(texto: str):
    """
    Extrai o maior numero do texto para comparação de preços.
    Trata: 358.040,16 (BR), 68.199,91 (BR), 68199.91 (EN), 360.000 (BR milhar).
    Retorna float ou None.
    """
    # Captura padrões numéricos: dígitos com pontos/vírgulas
    candidatos = re.findall(r"\d+(?:[.,]\d+)*", texto)
    numeros = []
    for c in candidatos:
        v = c
        if "," in v and "." in v:
            # Determina qual é decimal pelo último separador
            if v.rfind(",") > v.rfind("."):
                v = v.replace(".", "").replace(",", ".")  # BR: 358.040,16
            else:
                v = v.replace(",", "")  # EN: 68,199.91
        elif "." in v:
            partes = v.split(".")
            # Milhar BR: todas as partes após a primeira têm 3 dígitos
            if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
                v = v.replace(".", "")  # 360.000 → 360000
            # Senão é decimal EN: 360.5 → mantém
        elif "," in v:
            partes = v.split(",")
            if len(partes[-1]) <= 2:
                v = v.replace(",", ".")  # decimal BR: 357,98
            else:
                v = v.replace(",", "")  # milhar: 357,982
        v = re.sub(r"[^\d.]", "", v)
        try:
            n = float(v)
            if n > 100:  # filtra números pequenos (dia, mês, %)
                numeros.append(n)
        except Exception:
            pass
    return max(numeros) if numeros else None


def _similar(a: str, b: str) -> bool:
    """
    Retorna True se os textos concordam factualmente.
    Para numeros grandes (precos, cotacoes): tolerancia de 3%.
    Para texto sem numero grande: similaridade por palavras.
    """
    v1 = _extrair_numero(a)
    v2 = _extrair_numero(b)

    if v1 is not None and v2 is not None:
        diff = abs(v1 - v2) / max(v1, v2)
        similar = diff <= 0.03
        info("CONSENSUS", f"Numeros: {v1:.0f} vs {v2:.0f} | diff={diff:.2%} | similar={similar}")
        return similar

    # Sem numero grande — similaridade textual
    ratio = SequenceMatcher(None, a, b).ratio()
    if ratio >= THRESHOLD_SIMILARIDADE:
        return True

    palavras_a = set(w for w in a.split() if len(w) >= 5)
    palavras_b = set(w for w in b.split() if len(w) >= 5)
    return len(palavras_a & palavras_b) >= 2


def _extrair_dominio(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except Exception:
        return url


def _buscar(query: str) -> list:
    try:
        from integrations.exa_client import buscar_exa_multi, exa_disponivel
        if exa_disponivel():
            resultados = buscar_exa_multi(query, num_results=3)
            if resultados:
                info("CONSENSUS", f"EXA OK: {query[:50]}")
                return resultados
    except Exception as e:
        warn("CONSENSUS", f"EXA falhou: {e}")

    try:
        from integrations.tavily_client import buscar_online, tavily_disponivel
        if tavily_disponivel():
            resultado = buscar_online(query)
            if resultado:
                info("CONSENSUS", f"Tavily OK: {query[:50]}")
                return [{"title": "", "url": query, "snippet": resultado, "fonte": "tavily"}]
    except Exception as e:
        warn("CONSENSUS", f"Tavily falhou: {e}")

    return []


def tri_source_consensus(pergunta: str, llm=None, erros_api: list = None) -> dict:
    """
    Busca em ate 3 queries, extrai fatos LOCAL (zero LLM) e verifica consenso.
    Retorna: { "resposta": str, "fontes": list[str], "consenso": int }
    """
    if erros_api is None:
        erros_api = [0]

    queries = [
        f"{pergunta} site oficial",
        f"{pergunta} noticia recente",
    ]

    fatos  = []
    fontes = []

    for q in queries:
        try:
            resultados = _buscar(q)
        except Exception as e:
            erros_api[0] += 1
            erro("CONSENSUS", f"Busca falhou: {e}")
            if erros_api[0] >= 2:
                warn("CONSENSUS", "Circuit breaker — modo offline")
                return {"resposta": "Nao foi possivel buscar dados agora.", "fontes": fontes, "consenso": 0}
            continue

        if resultados:
            fato = _extrair_fato(resultados[0], llm)
            url  = resultados[0].get("url", q)
            # Debug: loga o que foi extraído
            info("CONSENSUS", f"fato extraido ({len(fato)} chars): '{fato[:60]}'")
            # Fallback: se extração falhou, usa primeiros 100 chars do snippet
            if not fato:
                snippet = resultados[0].get("snippet", "")
                fato = _normalizar(snippet[:100]) if snippet else ""
                if fato:
                    warn("CONSENSUS", f"Extração falhou — usando fallback: '{fato[:50]}'")
            if fato:
                fatos.append(fato)
                fontes.append(url)

    # 2 fatos concordam — economiza 3a busca
    if len(fatos) == 2 and _similar(fatos[0], fatos[1]):
        info("CONSENSUS", f"Consenso 2/2: {fatos[0][:60]}")
        return {"resposta": fatos[0], "fontes": fontes, "consenso": 2}

    # 3a busca — Wikipedia como desempate
    try:
        res3 = _buscar(f"{pergunta} wikipedia")
        if res3:
            fato3 = _extrair_fato(res3[0], llm)
            url3  = res3[0].get("url", "wikipedia")
            if not fato3:
                snippet3 = res3[0].get("snippet", "")
                fato3 = _normalizar(snippet3[:100]) if snippet3 else ""
            if fato3:
                fatos.append(fato3)
                fontes.append(url3)
    except Exception as e:
        erros_api[0] += 1
        warn("CONSENSUS", f"3a busca falhou: {e}")

    # Verifica consenso entre todos os pares
    if len(fatos) >= 2:
        pares_concordam = 0
        fato_consenso   = fatos[0]
        for i in range(len(fatos)):
            for j in range(i + 1, len(fatos)):
                if _similar(fatos[i], fatos[j]):
                    pares_concordam += 1
                    fato_consenso   = fatos[i]

        dominios = {_extrair_dominio(f) for f in fontes}
        if pares_concordam >= 1 and len(dominios) >= 2:
            consenso = min(3, pares_concordam + 1)
            info("CONSENSUS", f"Consenso {consenso}/3: {fato_consenso[:60]}")
            return {"resposta": fato_consenso, "fontes": fontes, "consenso": consenso}

    warn("CONSENSUS", "Sem consenso entre as fontes")
    resposta_fallback = fatos[0] if fatos else "Nao ha consenso confiavel entre as fontes."
    return {"resposta": resposta_fallback, "fontes": fontes, "consenso": len(fatos)}