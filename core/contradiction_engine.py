# core/contradiction_engine.py
"""
Fase 20 — Motor de Coerência Cognitiva.
Detecta conflito entre a mensagem/decisão atual e crenças ou princípios
registrados do usuário.

Design:
  - Não usa SequenceMatcher (similaridade léxica ≠ contradição cognitiva)
  - Não usa lista estática de "opostos" — contexto muda o que é oposto
  - Detecta incompatibilidade por domínio + sinal de valor contrário
  - Retorna conflito estruturado para o dissonance_trigger decidir se intervém

Estrutura de conflito retornado:
{
    "tipo":       "crenca" | "principio",
    "id":         str,               # id da crença/princípio em conflito
    "texto_ref":  str,               # texto da crença/princípio
    "dominio":    str,               # domínio do conflito
    "confianca":  float,             # confiança da referência
    "intensidade": float,            # 0.0–1.0 — quão forte é o conflito
    "descricao":  str,               # descrição legível
}
"""

from core.logger import info, debug, warn

# ── SINAIS DE VALOR POR POLO ──────────────────────────────────────────────────
# Para cada domínio, palavras que indicam polo ALTO vs BAIXO.
# Conflito = usuário demonstra polo contrário ao que acredita/declara.

_POLOS = {
    "risco": {
        "alto":  ["arriscar", "risco alto", "apostar", "agressivo", "alavancagem",
                  "sem proteção", "tudo ou nada", "dobrar", "all in"],
        "baixo": ["seguro", "conservador", "protegido", "cautela", "diversificar",
                  "garantido", "sem risco", "reserva", "hedge"],
    },
    "crescimento": {
        "alto":  ["crescer", "expandir", "escalar", "acelerar", "maximizar",
                  "oportunidade", "agressivo", "ambicioso"],
        "baixo": ["manter", "preservar", "estável", "sem crescimento", "suficiente",
                  "já chega", "não precisa crescer"],
    },
    "velocidade": {
        "alto":  ["rápido", "urgente", "já", "agora", "imediato", "sem esperar",
                  "hoje", "esta semana", "prazo curto"],
        "baixo": ["devagar", "calma", "sem pressa", "tranquilo", "com tempo",
                  "não urgente", "depois", "mais tarde"],
    },
    "qualidade": {
        "alto":  ["qualidade", "perfeito", "correto", "testado", "validado",
                  "sem bug", "robusto", "documentado", "revisado",
                  "testar", "testar antes", "revisar antes", "verificar antes"],
        "baixo": ["rápido o suficiente", "funciona e pronto", "não precisa ser perfeito",
                  "sem teste", "sem testar", "gambiarra", "provisório", "só funcionar",
                  "sem revisar", "sem validar", "sem verificar"],
    },
    "autonomia": {
        "alto":  ["autonomia", "autônomo", "independente", "independência", "livre",
                  "sozinho", "sem ajuda", "por conta própria", "minha decisão",
                  "sem supervisão", "sem depender", "independente de",
                  "independência de"],
        "baixo": ["ajuda", "supervisão", "aprovação", "dependente", "dependência",
                  "depender", "dependo", "vou depender", "precisar de ajuda",
                  "permissão", "validação", "consenso", "externo", "externos"],
    },
    "custo": {
        "alto":  ["caro", "investimento alto", "pagar mais", "premium", "sem limite",
                  "custo não importa"],
        "baixo": ["barato", "gratuito", "economizar", "custo baixo", "sem gastar",
                  "grátis", "reduzir custo"],
    },
}

# Peso de conflito por tipo de referência
_PESO_PRINCIPIO = 1.0   # princípio declarado → conflito mais sério
_PESO_CRENCA    = 0.7   # crença inferida → conflito menos sério


def _detectar_polo(texto: str, dominio: str) -> str | None:
    """
    Detecta qual polo o texto indica para um domínio.
    Retorna "alto", "baixo" ou None.
    Frases mais longas têm prioridade sobre substrings.
    """
    if dominio not in _POLOS:
        return None
    t = texto.lower()
    polos = _POLOS[dominio]

    alto_sorted  = sorted(polos["alto"],  key=len, reverse=True)
    baixo_sorted = sorted(polos["baixo"], key=len, reverse=True)

    votos_alto  = sum(1 for p in alto_sorted  if p in t)
    votos_baixo = sum(1 for p in baixo_sorted if p in t)

    # Cancela votos de alto que sejam substring de padrão baixo detectado
    for p_baixo in baixo_sorted:
        if p_baixo in t:
            for p_alto in alto_sorted:
                if p_alto in p_baixo:
                    votos_alto = max(0, votos_alto - 1)

    if votos_alto > votos_baixo:
        return "alto"
    if votos_baixo > votos_alto:
        return "baixo"
    return None


_NEGACOES = ["nunca", "jamais", "não", "nem", "proíbo", "evito"]


def _polo_da_referencia(texto_ref: str, dominio: str) -> str | None:
    """
    Detecta polo de uma crença/princípio armazenado.
    Trata negação: 'nunca sem testar' → inverte polo de 'sem testar' (baixo→alto).
    """
    t = texto_ref.lower()

    # Detecta polo direto primeiro
    polo = _detectar_polo(texto_ref, dominio)

    if dominio not in _POLOS:
        return polo

    # Verifica se há negação antes de padrão de polo baixo
    # Ex: "nunca sem testar" → "sem testar" é baixo, mas "nunca" inverte → alto
    tem_negacao = any(neg in t for neg in _NEGACOES)
    if tem_negacao:
        polos = _POLOS[dominio]
        for p_baixo in sorted(polos["baixo"], key=len, reverse=True):
            if p_baixo in t:
                # Verifica se a negação precede o padrão no texto
                idx_neg = min((t.find(neg) for neg in _NEGACOES if neg in t), default=-1)
                idx_pad = t.find(p_baixo)
                if idx_neg >= 0 and idx_neg < idx_pad:
                    # Negação antes do padrão → inverte
                    return "alto"

    return polo


def _conflito_de_polo(polo_atual: str, polo_ref: str) -> bool:
    """Retorna True se os polos são opostos."""
    return (
        polo_atual is not None and
        polo_ref   is not None and
        polo_atual != polo_ref
    )


def _calcular_intensidade(confianca_ref: float, polo_atual: str, polo_ref: str) -> float:
    """
    Intensidade do conflito: produto da confiança da referência
    pelo grau de oposição (0.5 se polos existem mas são iguais, 1.0 se opostos).
    """
    if not _conflito_de_polo(polo_atual, polo_ref):
        return 0.0
    return round(confianca_ref * 0.9, 3)


# ── DETECÇÃO PRINCIPAL ────────────────────────────────────────────────────────

def detectar_conflitos(
    msg: str,
    crencas: list[dict],
    principios: list[dict],
    min_intensidade: float = 0.4,
) -> list[dict]:
    """
    Detecta conflitos entre a mensagem atual e o histórico de
    crenças e princípios do usuário.

    Retorna lista de conflitos ordenados por intensidade (maior primeiro).
    Lista vazia = sem conflito relevante.

    Parâmetros:
        msg            — mensagem atual do usuário
        crencas        — lista de crenças ativas (do belief_tracker)
        principios     — lista de princípios ativos (do principle_registry)
        min_intensidade — threshold mínimo para considerar conflito
    """
    conflitos = []

    # ── Conflito com princípios (peso maior) ──────────────────────────────────
    for p in principios:
        dominio = p.get("dominio", "outro")
        if dominio == "outro":
            continue

        polo_atual = _detectar_polo(msg, dominio)
        polo_ref   = _polo_da_referencia(p.get("texto", ""), dominio)

        if not _conflito_de_polo(polo_atual, polo_ref):
            continue

        intensidade = _calcular_intensidade(
            p.get("confianca", 0.8) * _PESO_PRINCIPIO,
            polo_atual, polo_ref
        )

        if intensidade >= min_intensidade:
            conflito = {
                "tipo":       "principio",
                "id":         p.get("id", ""),
                "texto_ref":  p.get("texto", "")[:200],
                "dominio":    dominio,
                "confianca":  p.get("confianca", 0.8),
                "intensidade": intensidade,
                "descricao":  (
                    f"Decisão atual (polo={polo_atual}) conflita com princípio "
                    f"declarado (polo={polo_ref}): '{p.get('texto','')[:80]}'"
                ),
            }
            conflitos.append(conflito)
            warn("CONTRADIÇÃO", f"Princípio: domínio={dominio} | intensidade={intensidade:.2f}")

    # ── Conflito com crenças (peso menor) ────────────────────────────────────
    for c in crencas:
        dominio = c.get("dominio", "outro")
        if dominio == "outro":
            continue

        polo_atual = _detectar_polo(msg, dominio)
        polo_ref   = _polo_da_referencia(c.get("texto", ""), dominio)

        if not _conflito_de_polo(polo_atual, polo_ref):
            continue

        intensidade = _calcular_intensidade(
            c.get("confianca", 0.65) * _PESO_CRENCA,
            polo_atual, polo_ref
        )

        if intensidade >= min_intensidade:
            conflito = {
                "tipo":       "crenca",
                "id":         c.get("id", ""),
                "texto_ref":  c.get("texto", "")[:200],
                "dominio":    dominio,
                "confianca":  c.get("confianca", 0.65),
                "intensidade": intensidade,
                "descricao":  (
                    f"Decisão atual (polo={polo_atual}) contradiz crença "
                    f"(polo={polo_ref}, confiança={c.get('confianca',0):.2f}): "
                    f"'{c.get('texto','')[:80]}'"
                ),
            }
            conflitos.append(conflito)
            info("CONTRADIÇÃO", f"Crença: domínio={dominio} | intensidade={intensidade:.2f}")

    # Ordena por intensidade decrescente
    conflitos.sort(key=lambda x: x["intensidade"], reverse=True)

    if conflitos:
        debug("CONTRADIÇÃO", f"{len(conflitos)} conflito(s) detectado(s)")

    return conflitos


def conflito_mais_grave(conflitos: list[dict]) -> dict | None:
    """Retorna o conflito de maior intensidade, ou None."""
    return conflitos[0] if conflitos else None