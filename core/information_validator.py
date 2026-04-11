"""
core/information_validator.py
Fase 41-A — Validador Universal de Informação

Atua ANTES do valuator em toda resposta.
Classifica informação por tipo e penaliza score quando falta fonte.

Tipos:
  EFEMERO   — expira em horas (cotação, clima, placar)
  MEDIO     — expira em dias/semanas (versão, cargo, lei)
  FACTUAL   — pode mudar mas não frequentemente (população, estatística)
  ESTAVEL   — raramente muda (conceito, história, identidade)
  OPINIAO   — subjetivo, sem verificação possível
"""

import re
from datetime import datetime
from core.logger import info, warn

# ── CLASSIFICADORES POR PADRÃO DE TEXTO ──────────────────────────────────────

_EFEMERO = {
    "palavras": [
        "preço", "preco", "cotação", "cotacao", "valor atual", "hoje vale",
        "dólar", "dollar", "bitcoin", "ethereum", "cripto", "bolsa", "ibovespa",
        "temperatura", "clima agora", "graus agora",
        "resultado", "placar", "gol", "marcou", "venceu",
        "agora", "neste momento", "tempo real", "ao vivo",
    ],
    "score_max_sem_fonte": 0.35,
    "ttl_horas": 6,
    "label": "EFEMERO",
}

_MEDIO = {
    "palavras": [
        "versão", "versao", "atualização", "atualizacao", "release",
        "presidente", "governador", "ministro", "ceo", "diretor",
        "lei", "decreto", "portaria", "regulamento", "norma",
        "taxa", "juros", "selic", "inflação", "inflacao",
        "eleição", "eleicao", "candidato", "eleito",
        "guerra", "conflito", "acordo", "tratado",
    ],
    "score_max_sem_fonte": 0.55,
    "ttl_horas": 72,
    "label": "MEDIO",
}

_FACTUAL = {
    "palavras": [
        "população", "populacao", "habitantes", "km²", "área",
        "pib", "gdp", "renda per capita",
        "fundado", "criado em", "inaugurado", "descoberto",
        "record", "recorde", "maior", "menor", "mais alto", "mais baixo",
    ],
    "score_max_sem_fonte": 0.70,
    "ttl_horas": 720,  # 30 dias
    "label": "FACTUAL",
}

_OPINIAO = {
    "palavras": [
        "acho que", "acredito que", "na minha opinião", "na minha opiniao",
        "parece que", "talvez", "provavelmente", "pode ser que",
        "melhor é", "melhor e", "recomendo", "sugiro",
    ],
    "score_max_sem_fonte": 0.85,  # opinião não precisa de fonte — é subjetivo
    "ttl_horas": None,
    "label": "OPINIAO",
}

# Ordem de verificação — mais restritivo primeiro
_TIPOS = [_EFEMERO, _MEDIO, _FACTUAL, _OPINIAO]

# Escopos que já exigem busca externa — não penalizar duas vezes
_ESCOPOS_COM_BUSCA = {"world_state", "encyclopedic"}

# Escopos internos — nunca penalizar
_ESCOPOS_INTERNOS = {"conversacional", "internal", "identidade_interna", "mentoria_raciocinio"}


def classificar_informacao(pergunta: str, resposta: str) -> dict:
    """
    Classifica o tipo de informação na resposta.
    Retorna dict com tipo, score_max, ttl e label.
    """
    texto = (pergunta + " " + resposta).lower()

    for tipo in _TIPOS:
        encontradas = [p for p in tipo["palavras"] if p in texto]
        if encontradas:
            return {
                "tipo": tipo["label"],
                "score_max_sem_fonte": tipo["score_max_sem_fonte"],
                "ttl_horas": tipo["ttl_horas"],
                "palavras_detectadas": encontradas[:3],
            }

    return {
        "tipo": "ESTAVEL",
        "score_max_sem_fonte": 1.0,
        "ttl_horas": None,
        "palavras_detectadas": [],
    }


def tem_fonte_externa(dados_online: str, escopo: str) -> bool:
    """
    Verifica se a resposta foi baseada em busca externa real.
    """
    if escopo in _ESCOPOS_COM_BUSCA and dados_online and len(dados_online.strip()) > 50:
        return True
    return False


def validar(pergunta: str, resposta: str, dados_online: str = "",
            escopo: str = "", score_atual: float = 1.0) -> dict:
    """
    Valida a informação e retorna score ajustado + metadados.

    Integração no valuator.py:
        from core.information_validator import validar as validar_info
        resultado_info = validar_info(pergunta, resposta, dados_online, escopo, score)
        score = resultado_info["score_final"]
        if resultado_info["flag"]:
            erro_tipo = resultado_info["flag"]
    """
    # Escopos internos nunca são penalizados
    if escopo in _ESCOPOS_INTERNOS:
        return {
            "score_final": score_atual,
            "tipo": "ESTAVEL",
            "flag": None,
            "ttl_horas": None,
            "requer_fonte": False,
            "mensagem": "escopo interno — sem penalidade",
        }

    classificacao = classificar_informacao(pergunta, resposta)
    tipo = classificacao["tipo"]
    score_max = classificacao["score_max_sem_fonte"]
    ttl = classificacao["ttl_horas"]
    palavras = classificacao["palavras_detectadas"]

    tem_fonte = tem_fonte_externa(dados_online, escopo)
    flag = None
    score_final = score_atual

    if tipo == "ESTAVEL" or tipo == "OPINIAO":
        # Estável e opinião não precisam de fonte
        score_final = score_atual

    elif tem_fonte:
        # Tem fonte — score normal, só marca o TTL
        score_final = score_atual
        info("INFO_VALIDATOR", f"Tipo={tipo} | fonte=OK | ttl={ttl}h | {palavras}")

    else:
        # Informação factual/volátil SEM fonte — penaliza
        score_penalizado = min(score_atual, score_max)
        score_final = round(score_penalizado, 3)
        flag = f"sem_fonte_{tipo.lower()}"

        warn("INFO_VALIDATOR", (
            f"Tipo={tipo} | SEM FONTE | "
            f"score {score_atual:.2f} → {score_final:.2f} | "
            f"palavras={palavras}"
        ))

    return {
        "score_final": score_final,
        "tipo": tipo,
        "flag": flag,
        "ttl_horas": ttl,
        "requer_fonte": not tem_fonte and tipo not in ("ESTAVEL", "OPINIAO"),
        "palavras_detectadas": palavras,
        "mensagem": (
            f"tipo={tipo} | fonte={'sim' if tem_fonte else 'nao'} | "
            f"score={score_final}"
        ),
    }


def enriquecer_entrada_livro(entrada: dict, resultado_validacao: dict) -> dict:
    """
    Adiciona metadados de validade a uma entrada antes de salvar no livro.
    Uso em books.py antes de append no livro.

    entrada = {
        "data": "...",
        "pergunta": "...",
        "resposta": "...",
    }
    """
    ttl = resultado_validacao.get("ttl_horas")
    tipo = resultado_validacao.get("tipo", "ESTAVEL")

    entrada["tipo_informacao"] = tipo

    if ttl:
        agora = datetime.now()
        # Marca quando essa entrada expira
        from datetime import timedelta
        expira = agora + timedelta(hours=ttl)
        entrada["expira_em"] = expira.strftime("%d/%m/%Y %H:%M")
        entrada["ttl_horas"] = ttl

    if resultado_validacao.get("flag"):
        entrada["confianca"] = resultado_validacao["score_final"]
        entrada["sem_fonte"] = True

    return entrada


def filtrar_entradas_expiradas(entradas: list) -> list:
    """
    Remove entradas com expira_em no passado.
    Uso em books.py ao carregar livro para injeção no contexto.
    """
    agora = datetime.now()
    validas = []
    expiradas = 0

    for e in entradas:
        expira_str = e.get("expira_em")
        if not expira_str:
            validas.append(e)
            continue
        try:
            expira = datetime.strptime(expira_str, "%d/%m/%Y %H:%M")
            if expira > agora:
                validas.append(e)
            else:
                expiradas += 1
        except Exception:
            validas.append(e)

    if expiradas:
        warn("INFO_VALIDATOR", f"{expiradas} entrada(s) expirada(s) filtrada(s) na injeção")

    return validas