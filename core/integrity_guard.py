# core/integrity_guard.py
"""
Fase 22 — Herança Cognitiva Viva.
Regra estrutural obrigatória: classifica toda afirmação em um nível de verdade.

Níveis (do mais para o menos verificável):
  observado  — aconteceu, foi dito, foi feito. Evidência direta na conversa.
  recorrente — padrão confirmado em múltiplas interações. Contagem >= 3.
  inferido   — deduzido a partir de comportamento ou contexto. Não confirmado explicitamente.
  narrativo  — interpretação, relato autobiográfico, história sobre si mesmo.
               Pode ser verdadeiro mas não verificável pelo sistema.

Regra: nenhuma afirmação entra no livro_legado sem nível atribuído.
"""

from core.logger import info, debug

# ── CRITÉRIOS POR NÍVEL ───────────────────────────────────────────────────────

# Palavras que indicam que o usuário está relatando algo que aconteceu (observado)
_MARCADORES_OBSERVADO = [
    "fiz", "fiz isso", "aconteceu", "aconteceu comigo", "foi assim",
    "eu disse", "eu falei", "eu decidi", "decidi", "escolhi", "comprei",
    "vendi", "perdi", "ganhei", "terminei", "comecei", "entreguei",
    "resolvi", "confirmei", "testei", "rodei", "executei",
]

# Palavras que indicam padrão recorrente
_MARCADORES_RECORRENTE = [
    "sempre faço", "sempre fiz", "toda vez", "todo dia", "constantemente",
    "invariavelmente", "nunca deixo de", "é meu hábito", "costumo sempre",
    "meu padrão é", "historicamente", "ao longo do tempo",
]

# Palavras que indicam inferência/preferência não confirmada
_MARCADORES_INFERIDO = [
    "acho que", "acredito que", "parece que", "provavelmente",
    "deve ser", "imagino que", "suspeito que", "tende a",
    "normalmente", "geralmente", "na maioria das vezes",
    "prefiro", "preferiria", "gostaria",
]

# Palavras que indicam narrativa/relato autobiográfico
_MARCADORES_NARRATIVO = [
    "minha história", "quando eu era", "lembro que", "me lembro de",
    "na época", "antigamente", "quando jovem", "minha trajetória",
    "o que aprendi na vida", "minha experiência de vida",
    "sou uma pessoa que", "sempre fui", "nunca fui",
]


def classificar(texto: str, contagem: int = 1, fonte: str = "") -> str:
    """
    Classifica uma afirmação em um dos 4 níveis de verdade.

    Parâmetros:
        texto    — texto da afirmação
        contagem — quantas vezes foi detectada (para distinguir inferido de recorrente)
        fonte    — origem: "crenca" | "principio" | "metamorfose" | "livre"

    Retorna: "observado" | "recorrente" | "inferido" | "narrativo"
    """
    t = " " + texto.lower() + " "

    # Observado — evidência direta, aconteceu
    if any((" " + m + " ") in t or t.startswith(" " + m) for m in _MARCADORES_OBSERVADO):
        nivel = "observado"
        debug("INTEGRITY", f"observado: '{texto[:50]}'")
        return nivel

    # Recorrente — padrão confirmado OU contagem alta
    if contagem >= 3:
        nivel = "recorrente"
        debug("INTEGRITY", f"recorrente (contagem={contagem}): '{texto[:50]}'")
        return nivel

    if any((" " + m + " ") in t or t.startswith(" " + m) for m in _MARCADORES_RECORRENTE):
        nivel = "recorrente"
        debug("INTEGRITY", f"recorrente (marcador): '{texto[:50]}'")
        return nivel

    # Narrativo — relato autobiográfico
    if any((" " + m + " ") in t or t.startswith(" " + m) for m in _MARCADORES_NARRATIVO):
        nivel = "narrativo"
        debug("INTEGRITY", f"narrativo: '{texto[:50]}'")
        return nivel

    # Inferido — padrão padrão para preferências e deduções
    nivel = "inferido"
    debug("INTEGRITY", f"inferido (default): '{texto[:50]}'")
    return nivel


def classificar_lote(entradas: list[dict]) -> list[dict]:
    """
    Classifica uma lista de entradas (crenças, princípios, metamorfoses).
    Adiciona campo "nivel_verdade" a cada entrada.
    Não modifica os originais — retorna cópias.

    Espera entradas com campos: texto, contagem (opcional), dominio (opcional).
    """
    resultado = []
    for entrada in entradas:
        copia = dict(entrada)
        nivel = classificar(
            texto    = entrada.get("texto", ""),
            contagem = entrada.get("contagem", 1),
            fonte    = entrada.get("fonte", ""),
        )
        copia["nivel_verdade"] = nivel
        resultado.append(copia)

    niveis = {}
    for r in resultado:
        n = r["nivel_verdade"]
        niveis[n] = niveis.get(n, 0) + 1

    info("INTEGRITY", f"Lote classificado: {len(resultado)} entradas | {niveis}")
    return resultado


def resumo_integridade(entradas: list[dict]) -> dict:
    """
    Retorna estatísticas de integridade de um conjunto de afirmações.
    Útil para o legacy_exporter avaliar qualidade antes de exportar.
    """
    if not entradas:
        return {"total": 0, "observado": 0, "recorrente": 0, "inferido": 0, "narrativo": 0, "score": 0.0}

    contagens = {"observado": 0, "recorrente": 0, "inferido": 0, "narrativo": 0}
    for e in entradas:
        nivel = e.get("nivel_verdade") or classificar(
            e.get("texto", ""), e.get("contagem", 1)
        )
        if nivel in contagens:
            contagens[nivel] += 1

    total = len(entradas)
    # Score de integridade: observado=1.0, recorrente=0.8, inferido=0.5, narrativo=0.3
    pesos = {"observado": 1.0, "recorrente": 0.8, "inferido": 0.5, "narrativo": 0.3}
    score = sum(contagens[n] * pesos[n] for n in contagens) / total

    return {
        "total":      total,
        "observado":  contagens["observado"],
        "recorrente": contagens["recorrente"],
        "inferido":   contagens["inferido"],
        "narrativo":  contagens["narrativo"],
        "score":      round(score, 3),
    }