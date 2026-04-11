"""
core/organ_factory.py
Fase 30 — Órgãos Cognitivos que Nascem e Morrem.

O sistema não começa completo. Desenvolve novos órgãos quando a realidade
o obriga — e mata órgãos que ficaram bonitos e inúteis.

Cada órgão tem:
  - nome         — identificador legível
  - funcao       — o que faz
  - status       — embrionario | ativo | inflamado | morto
  - condicao_nascer  — o que precisa acontecer para nascer
  - condicao_morrer  — o que faz o órgão morrer (necrose)
  - ativacoes    — quantas vezes foi chamado com sucesso
  - falhas       — quantas vezes falhou ou foi irrelevante
  - criado_em    — timestamp
  - ultima_vez   — última ativação
"""

import json
import os
import threading
from datetime import datetime
from core.logger import info, warn, debug

ORGAOS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_orgaos.json"
)

_cache = {"dados": None}
_lock  = threading.Lock()

# ── CATÁLOGO DE ÓRGÃOS POSSÍVEIS ─────────────────────────────────────────────
_CATALOGO = {
    "compressao_brutal": {
        "nome":    "Órgão de Compressão Brutal",
        "funcao":  "Quando análise falha 3x, reduz resposta a 1 frase obrigatória",
        "nasce_quando": lambda ctx: ctx.get("falhas_analise", 0) >= 3,
        "morre_quando": lambda ctx: ctx.get("ativacoes", 0) > 0 and ctx.get("taxa_aceitacao", 1.0) < 0.2,
        "instrucao": "\n[COMPRESSÃO BRUTAL ATIVA] Responda em 1 frase. Sem análise. Sem contexto.",
    },
    "pressao_continuidade": {
        "nome":    "Órgão de Pressão de Continuidade",
        "funcao":  "Detecta abandono de projetos a 70% e empurra para conclusão",
        "nasce_quando": lambda ctx: ctx.get("projetos_abandonados", 0) >= 2,
        "morre_quando": lambda ctx: ctx.get("projetos_concluidos", 0) >= ctx.get("projetos_abandonados", 0),
        "instrucao": "\n[PRESSÃO DE CONTINUIDADE] Se o usuário está mudando de assunto sem concluir, pergunte sobre o projeto anterior antes de seguir.",
    },
    "arqueologia_projeto": {
        "nome":    "Órgão de Arqueologia de Projeto",
        "funcao":  "Recupera intenção original quando projeto deriva",
        "nasce_quando": lambda ctx: ctx.get("desvios_detectados", 0) >= 3,
        "morre_quando": lambda ctx: ctx.get("ativacoes", 0) > 5 and ctx.get("taxa_aceitacao", 1.0) < 0.3,
        "instrucao": "\n[ARQUEOLOGIA ATIVA] Antes de responder, verifique se a pergunta atual serve a intenção original do projeto.",
    },
    "poda_complexidade": {
        "nome":    "Órgão de Poda de Complexidade",
        "funcao":  "Mata módulos que cresceram bonitos e inúteis",
        "nasce_quando": lambda ctx: ctx.get("modulos_sem_uso", 0) >= 3,
        "morre_quando": lambda ctx: ctx.get("complexidade_atual", 10) < 5,
        "instrucao": "\n[PODA ATIVA] Se a resposta pode ser mais simples, simplifique. Elimine o que não serve o objetivo real.",
    },
    "divida_cognitiva": {
        "nome":    "Órgão de Dívida Cognitiva",
        "funcao":  "Rastreia promessas não cumpridas e traz de volta",
        "nasce_quando": lambda ctx: ctx.get("promessas_nao_cumpridas", 0) >= 2,
        "morre_quando": lambda ctx: ctx.get("promessas_nao_cumpridas", 0) == 0,
        "instrucao": "\n[DÍVIDA COGNITIVA] Há itens prometidos não entregues. Mencione-os se relevante.",
    },
    "deteccao_autoengano": {
        "nome":    "Órgão de Detecção de Autoengano",
        "funcao":  "Identifica quando usuário se contradiz sem perceber",
        "nasce_quando": lambda ctx: ctx.get("contradicoes_nao_percebidas", 0) >= 3,
        "morre_quando": lambda ctx: ctx.get("contradicoes_nao_percebidas", 0) == 0,
        "instrucao": "\n[ANTIENGANO ATIVO] Se detectar contradição com crença anterior, nomeie gentilmente antes de responder.",
    },
    "reconciliacao": {
        "nome":    "Órgão de Reconciliação",
        "funcao":  "Calibra ambição vs energia real disponível",
        "nasce_quando": lambda ctx: ctx.get("ppd", 0) >= 0.7 and ctx.get("metas_irreais", 0) >= 2,
        "morre_quando": lambda ctx: ctx.get("ppd", 0) < 0.5,
        "instrucao": "\n[RECONCILIAÇÃO] Calibre a resposta para o nível de energia real do usuário. Não alimente metas além da capacidade atual.",
    },
}


# ── PERSISTÊNCIA ─────────────────────────────────────────────────────────────

def _carregar() -> dict:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(ORGAOS_PATH):
        _cache["dados"] = {}
        return {}
    try:
        with open(ORGAOS_PATH, "r", encoding="utf-8") as f:
            _cache["dados"] = json.load(f)
            return _cache["dados"]
    except Exception:
        _cache["dados"] = {}
        return {}


def _salvar(dados: dict):
    try:
        with open(ORGAOS_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("ORGAOS", f"Erro ao salvar: {e}")


# ── CICLO DE VIDA ─────────────────────────────────────────────────────────────

def avaliar_nascimento(ctx: dict) -> list:
    """
    Verifica quais órgãos devem nascer dado o contexto atual.
    Retorna lista de IDs dos órgãos recém-nascidos.
    """
    dados   = _carregar()
    nascidos = []
    agora   = datetime.now().isoformat()

    for oid, catalogo in _CATALOGO.items():
        existente = dados.get(oid, {})
        status    = existente.get("status", "inexistente")

        # Já ativo ou morto permanente — não renasce
        if status in ("ativo", "morto_permanente"):
            continue

        # Verifica condição de nascimento
        try:
            if catalogo["nasce_quando"](ctx):
                if status == "inexistente":
                    dados[oid] = {
                        "id":         oid,
                        "nome":       catalogo["nome"],
                        "funcao":     catalogo["funcao"],
                        "status":     "embrionario",
                        "ativacoes":  0,
                        "falhas":     0,
                        "taxa_aceitacao": 1.0,
                        "criado_em":  agora,
                        "ultima_vez": agora,
                    }
                    nascidos.append(oid)
                    info("ORGAOS", f"Nascimento: {catalogo['nome']}")
                elif status == "embrionario":
                    # Embrião que continua com condição → ativa
                    dados[oid]["status"] = "ativo"
                    dados[oid]["ultima_vez"] = agora
                    nascidos.append(oid)
                    info("ORGAOS", f"Ativado: {catalogo['nome']}")
        except Exception:
            pass

    if nascidos:
        with _lock:
            _cache["dados"] = dados
            threading.Thread(target=_salvar, args=(dados,), daemon=True).start()

    return nascidos


def avaliar_morte(ctx: dict) -> list:
    """
    Verifica quais órgãos ativos devem morrer (necrose).
    Retorna lista de IDs dos órgãos que morreram.
    """
    dados  = _carregar()
    mortos = []
    agora  = datetime.now().isoformat()

    for oid, orgao in dados.items():
        if orgao.get("status") not in ("ativo", "embrionario"):
            continue

        catalogo = _CATALOGO.get(oid)
        if not catalogo:
            continue

        ctx_orgao = {**ctx, **orgao}
        try:
            if catalogo["morre_quando"](ctx_orgao):
                orgao["status"]     = "morto"
                orgao["ultima_vez"] = agora
                mortos.append(oid)
                warn("ORGAOS", f"Necrose: {orgao['nome']}")
        except Exception:
            pass

    if mortos:
        with _lock:
            _cache["dados"] = dados
            threading.Thread(target=_salvar, args=(dados,), daemon=True).start()

    return mortos


def registrar_ativacao(oid: str, sucesso: bool = True):
    """Registra uso de um órgão e atualiza taxa de aceitação."""
    with _lock:
        dados = _carregar()
        if oid not in dados:
            return
        o = dados[oid]
        if sucesso:
            o["ativacoes"] = o.get("ativacoes", 0) + 1
        else:
            o["falhas"] = o.get("falhas", 0) + 1
        total = o["ativacoes"] + o["falhas"]
        o["taxa_aceitacao"] = round(o["ativacoes"] / total, 2) if total > 0 else 1.0
        o["ultima_vez"] = datetime.now().isoformat()
        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()


# ── INSTRUÇÃO ATIVA ───────────────────────────────────────────────────────────

def instrucoes_ativas() -> str:
    """
    Retorna instruções combinadas de todos os órgãos ativos.
    Injetadas no contexto do LLM.
    """
    dados = _carregar()
    partes = []
    for oid, orgao in dados.items():
        if orgao.get("status") != "ativo":
            continue
        catalogo = _CATALOGO.get(oid)
        if catalogo:
            partes.append(catalogo["instrucao"])
    return "".join(partes)


# ── CONTEXTO AUTOMÁTICO ───────────────────────────────────────────────────────

def _montar_contexto() -> dict:
    """
    Monta contexto para avaliação de nascimento/morte a partir dos livros existentes.
    Zero API — lê arquivos locais.
    """
    base = os.path.dirname(os.path.dirname(__file__))
    ctx  = {}

    # PPD
    try:
        from core.ppd_tracker import calcular_ppd
        ctx["ppd"] = calcular_ppd()
    except Exception:
        ctx["ppd"] = 0.0

    # Fricções
    try:
        from core.friction_chamber import padroes_criticos
        ctx["falhas_analise"] = sum(
            1 for p in padroes_criticos()
            if p.get("id") == "decisao_vs_analise"
        )
        ctx["projetos_abandonados"] = sum(
            1 for p in padroes_criticos()
            if p.get("id") == "evolucao_vs_preservacao"
        )
    except Exception:
        pass

    # Contradições recentes
    try:
        p = os.path.join(base, "livro_dissonancia.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                dis = json.load(f)
            ctx["contradicoes_nao_percebidas"] = len(dis)
    except Exception:
        pass

    return ctx


def processar(msg: str = "", resposta: str = "") -> str:
    """
    Ponto de entrada do pipeline.
    Avalia nascimentos, mortes e retorna instruções dos órgãos ativos.
    """
    ctx = _montar_contexto()

    avaliar_morte(ctx)
    avaliar_nascimento(ctx)

    instrucoes = instrucoes_ativas()
    if instrucoes:
        debug("ORGAOS", f"Instruções ativas: {len(instrucoes)} chars")

    return instrucoes


def resumo() -> dict:
    dados = _carregar()
    por_status = {}
    for o in dados.values():
        s = o.get("status", "?")
        por_status[s] = por_status.get(s, 0) + 1
    return {
        "total":      len(dados),
        "por_status": por_status,
        "ativos":     [o["nome"] for o in dados.values() if o.get("status") == "ativo"],
    }