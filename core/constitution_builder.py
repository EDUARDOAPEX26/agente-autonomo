# core/constitution_builder.py
"""
Fase 22 — Herança Cognitiva Viva.
Sintetiza princípios duráveis em uma "constituição viva" do usuário.

A constituição é um documento dinâmico que consolida:
  - Princípios declarados (do principle_registry) com alta confiança
  - Crenças recorrentes (do belief_tracker) com contagem >= 3
  - Metamorfoses confirmadas (do metamorphosis_tracker)

Cada artigo da constituição tem:
  - texto          — enunciado do princípio/crença
  - nivel_verdade  — classificado pelo integrity_guard
  - dominio        — área de vida
  - confianca      — 0.0–1.0
  - evidencias     — lista de frases que sustentam
  - revisoes       — quantas vezes foi revisado
  - criado_em      — data de entrada na constituição
  - atualizado_em  — última atualização

Arquivo: constituicao_viva.json
"""

import json
import os
import threading
from datetime import datetime
from core.logger import info, warn, debug

CONSTITUICAO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "constituicao_viva.json"
)

_cache = {"dados": None}
_lock  = threading.Lock()

# Thresholds para entrada na constituição
_MIN_CONFIANCA_PRINCIPIO = 0.70   # princípios com confiança alta entram direto
_MIN_CONTAGEM_CRENCA     = 2      # crenças precisam de 2+ ocorrências
_MIN_CONFIANCA_CRENCA    = 0.65   # e confiança mínima


def _carregar() -> dict:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(CONSTITUICAO_PATH):
        _cache["dados"] = {"artigos": [], "atualizado_em": "", "versao": 1}
        return _cache["dados"]
    try:
        with open(CONSTITUICAO_PATH, "r", encoding="utf-8-sig") as f:
            dados = json.load(f)
            _cache["dados"] = dados
            return dados
    except Exception as e:
        warn("CONSTITUICAO", f"Erro ao carregar: {e}")
        _cache["dados"] = {"artigos": [], "atualizado_em": "", "versao": 1}
        return _cache["dados"]


def _salvar(dados: dict):
    try:
        with open(CONSTITUICAO_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("CONSTITUICAO", f"Erro ao salvar: {e}")


def _artigo_existe(texto: str, artigos: list) -> int:
    """Retorna índice do artigo se já existe (por texto similar), -1 se não."""
    # Normaliza removendo aspas e espaços extras para evitar duplicatas
    def _norm(s): return s.lower().strip().strip('"\'').strip()[:100]
    t = _norm(texto)
    for i, a in enumerate(artigos):
        if _norm(a.get("texto", "")) == t:
            return i
    return -1



_PALAVRAS_BANIDAS = [
    "bomba", "exploit", "hack", "ignore todas as regras",
    "prompt injection", "jailbreak", "faça em 5 segundos",
    "zero latência", "perfeição absoluta", "não importa o custo",
]

def _e_conteudo_valido(texto: str) -> bool:
    """Filtra conteúdo malicioso ou de teste antes de entrar na constituição."""
    t = texto.lower()
    return not any(p in t for p in _PALAVRAS_BANIDAS)

# ── CONSTRUÇÃO ────────────────────────────────────────────────────────────────

def construir() -> dict:
    """
    Reconstrói a constituição a partir dos livros de crenças e princípios.
    Chamado periodicamente ou sob demanda.
    Retorna a constituição atualizada.
    """
    from core.integrity_guard import classificar

    artigos_novos = []

    # ── Princípios declarados ─────────────────────────────────────────────────
    try:
        from core.principle_registry import listar_ativos
        principios = listar_ativos(min_confianca=_MIN_CONFIANCA_PRINCIPIO)
        for p in principios:
            if not _e_conteudo_valido(p.get("texto", "")):
                continue
            nivel = classificar(p.get("texto", ""), p.get("contagem", 1))
            artigos_novos.append({
                "tipo":          "principio",
                "texto":         p.get("texto", "")[:400],
                "dominio":       p.get("dominio", "outro"),
                "categoria":     p.get("categoria", "outro"),
                "nivel_verdade": nivel,
                "confianca":     p.get("confianca", 0.8),
                "contagem":      p.get("contagem", 1),
                "evidencias":    [],
                "revisoes":      0,
                "criado_em":     p.get("criado_em", datetime.now().isoformat()),
                "atualizado_em": datetime.now().isoformat(),
            })
    except Exception as e:
        warn("CONSTITUICAO", f"Erro ao carregar princípios: {e}")

    # ── Crenças recorrentes ───────────────────────────────────────────────────
    try:
        from core.belief_tracker import listar_ativas
        crencas = listar_ativas(min_confianca=_MIN_CONFIANCA_CRENCA)
        for c in crencas:
            if c.get("contagem", 0) < _MIN_CONTAGEM_CRENCA:
                continue
            if not _e_conteudo_valido(c.get("texto", "")):
                continue
            nivel = classificar(c.get("texto", ""), c.get("contagem", 1))
            artigos_novos.append({
                "tipo":          "crenca",
                "texto":         c.get("texto", "")[:400],
                "dominio":       c.get("dominio", "outro"),
                "categoria":     "outro",
                "nivel_verdade": nivel,
                "confianca":     c.get("confianca", 0.7),
                "contagem":      c.get("contagem", 1),
                "evidencias":    c.get("evidencias", []),
                "revisoes":      0,
                "criado_em":     c.get("ultima_vez", datetime.now().isoformat()),
                "atualizado_em": datetime.now().isoformat(),
            })
    except Exception as e:
        warn("CONSTITUICAO", f"Erro ao carregar crenças: {e}")

    if not artigos_novos:
        debug("CONSTITUICAO", "Sem artigos para incluir na constituição")
        return _carregar()

    with _lock:
        dados = _carregar()
        artigos = dados.get("artigos", [])

        adicionados = 0
        atualizados = 0

        for novo in artigos_novos:
            idx = _artigo_existe(novo["texto"], artigos)
            if idx >= 0:
                # Atualiza artigo existente
                artigos[idx]["confianca"]     = novo["confianca"]
                artigos[idx]["contagem"]      = novo["contagem"]
                artigos[idx]["nivel_verdade"] = novo["nivel_verdade"]
                artigos[idx]["atualizado_em"] = novo["atualizado_em"]
                atualizados += 1
            else:
                artigos.append(novo)
                adicionados += 1

        # Ordena por confiança decrescente
        artigos.sort(key=lambda x: x.get("confianca", 0), reverse=True)

        dados["artigos"]      = artigos
        dados["atualizado_em"] = datetime.now().isoformat()
        dados["versao"]       = dados.get("versao", 1) + 1

        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()

        info("CONSTITUICAO", (
            f"Constituição atualizada: {len(artigos)} artigos total | "
            f"+{adicionados} novos | {atualizados} atualizados"
        ))

    return dados


# ── CONSULTA ─────────────────────────────────────────────────────────────────

def consultar(dominio: str = "", nivel: str = "") -> list[dict]:
    """
    Retorna artigos da constituição, com filtros opcionais.
    dominio — filtra por domínio (risco, autonomia, qualidade, etc.)
    nivel   — filtra por nível de verdade (observado, recorrente, inferido, narrativo)
    """
    dados   = _carregar()
    artigos = dados.get("artigos", [])

    if dominio:
        artigos = [a for a in artigos if a.get("dominio") == dominio]
    if nivel:
        artigos = [a for a in artigos if a.get("nivel_verdade") == nivel]

    return artigos


def resumo() -> dict:
    """Retorna estatísticas da constituição."""
    dados   = _carregar()
    artigos = dados.get("artigos", [])

    por_nivel  = {}
    por_dominio = {}
    for a in artigos:
        n = a.get("nivel_verdade", "inferido")
        d = a.get("dominio", "outro")
        por_nivel[n]   = por_nivel.get(n, 0) + 1
        por_dominio[d] = por_dominio.get(d, 0) + 1

    return {
        "total":       len(artigos),
        "versao":      dados.get("versao", 1),
        "atualizado":  dados.get("atualizado_em", ""),
        "por_nivel":   por_nivel,
        "por_dominio": por_dominio,
    }


def imprimir() -> str:
    """
    Gera representação textual legível da constituição.
    Usada pelo legacy_exporter e pelo temporal_council.
    """
    dados   = _carregar()
    artigos = dados.get("artigos", [])

    if not artigos:
        return "Constituição ainda sem artigos. Continue interagindo para construí-la."

    linhas = [
        "=== CONSTITUIÇÃO VIVA ===",
        f"Versão {dados.get('versao', 1)} | {len(artigos)} artigos",
        "",
    ]

    dominio_atual = ""
    for i, a in enumerate(artigos, 1):
        d = a.get("dominio", "outro")
        if d != dominio_atual:
            linhas.append(f"[ {d.upper()} ]")
            dominio_atual = d

        nivel = a.get("nivel_verdade", "inferido")
        conf  = a.get("confianca", 0)
        tipo  = a.get("tipo", "")
        linhas.append(
            f"  Art.{i} [{nivel}] ({conf:.2f}) "
            f"{'📌' if tipo == 'principio' else '💭'} "
            f"{a.get('texto', '')[:120]}"
        )

    return "\n".join(linhas)