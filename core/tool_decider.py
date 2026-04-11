# core/tool_decider.py
"""
Decide qual estratégia usar baseado em memória dos livros existentes.
Usa livros JSON reais: livro_codigo.json, livro_geral.json, etc.
NÃO depende de Chroma, subprocess ou arquivos externos novos.
"""
import json
import os
import re
from datetime import datetime

from core.logger import info, debug

# Livros disponíveis no projeto
LIVROS_DISPONIVEIS = [
    "codigo", "geral", "railway", "memoria",
    "hackathons", "eduardo", "groq", "tavily"
]

BASE_PATH = os.path.join(os.path.dirname(__file__), "..")

def _carregar_livro(assunto: str) -> list:
    caminho = os.path.join(BASE_PATH, f"livro_{assunto}.json")
    if not os.path.exists(caminho):
        return []
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            livro = json.load(f)
            return livro.get("entradas", [])
    except Exception:
        return []

def _score_ajustado(entrada: dict) -> float:
    """Decai o score com o tempo — entradas antigas valem menos."""
    score = entrada.get("confianca", 0.5)
    try:
        data_str = entrada.get("data", "")
        if data_str:
            data = datetime.strptime(data_str, "%d/%m/%Y %H:%M")
            idade_dias = (datetime.now() - data).days
            score = score - (idade_dias * 0.005)  # decaimento suave
    except Exception:
        pass
    return max(0.0, round(score, 3))

def _buscar_experiencia(pergunta: str) -> dict | None:
    """Busca nos livros uma entrada relevante por substring."""
    p = pergunta.lower()
    melhor = None
    melhor_score = 0.0

    for assunto in LIVROS_DISPONIVEIS:
        entradas = _carregar_livro(assunto)
        for entrada in entradas:
            texto = entrada.get("pergunta", "").lower()
            if not texto:
                continue
            # Match simples por palavras em comum
            palavras_pergunta = set(p.split())
            palavras_entrada  = set(texto.split())
            comuns = palavras_pergunta & palavras_entrada
            if len(comuns) >= 2:
                score = _score_ajustado(entrada)
                if score > melhor_score:
                    melhor_score = score
                    melhor = {**entrada, "assunto": assunto, "score_ajustado": score}

    return melhor if melhor_score >= 0.4 else None

def decidir_estrategia(pergunta: str) -> tuple[str, dict]:
    """
    Retorna (estrategia, log_dict).
    Estratégias possíveis:
      - "local_codigo"  → pergunta de código, usa EXA para exemplos
      - "local_memoria" → responde com livros, sem busca externa
      - "local_web"     → precisa de dado atual, usa EXA/Tavily
      - "local"         → fallback geral
    """
    p = pergunta.lower()

    # 1. Verifica memória dos livros
    exp = _buscar_experiencia(pergunta)

    if exp:
        score = exp["score_ajustado"]
        debug("TOOL", f"Experiencia encontrada (score={score}) em livro '{exp['assunto']}'")

        if score >= 0.8:
            info("TOOL", f"Estrategia: local_memoria (score={score})")
            return "local_memoria", {"tipo": "memoria", "score": score, "assunto": exp["assunto"]}

    # 2. Detecta pergunta de código
    if re.search(r"(código|code|função|script|programa|implementa|cria|faz um|desenvolve)", p):
        info("TOOL", "Estrategia: local_codigo")
        return "local_codigo", {"tipo": "regra_codigo"}

    # 3. Detecta pergunta que precisa de dado atual
    palavras_web = ["hoje", "agora", "atual", "recente", "noticia", "cotacao",
                    "preco", "dolar", "bitcoin", "clima", "resultado", "placar"]
    if any(w in p for w in palavras_web):
        info("TOOL", "Estrategia: local_web")
        return "local_web", {"tipo": "regra_web"}

    # 4. Fallback
    debug("TOOL", "Estrategia: local (fallback)")
    return "local", {"tipo": "fallback"}