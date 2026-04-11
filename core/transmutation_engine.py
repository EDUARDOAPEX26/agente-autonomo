"""
core/transmutation_engine.py
Fase 25 — Motor de Transmutação.

Converte fricção persistente em mutação estrutural proposta.
Não ajusta threshold — propõe mudança de fisiologia.

A transmutação só ocorre quando:
  1. Uma fricção atingiu o limiar de repetição (3+ ciclos)
  2. O campo gravitacional está definido (20+ sinais)
  3. A mutação proposta é coerente com o vetor do usuário

Estrutura de uma mutação:
{
    "id":             str,
    "friccao_id":     str,     # qual fricção gerou a mutação
    "tipo":           str,     # "modo" | "orgao" | "necrose" | "cicatriz"
    "nome":           str,     # nome legível
    "descricao":      str,     # o que muda
    "vetor_alvo":     str,     # domínio gravitacional que serve
    "impacto":        str,     # "alto" | "medio" | "baixo"
    "status":         str,     # "proposta" | "em_teste" | "consolidada" | "rejeitada" | "cicatriz"
    "criada_em":      str,
    "atualizada_em":  str,
    "evidencias":     list,    # fricções que justificam
}
"""

import json
import os
import threading
from datetime import datetime
from core.logger import info, warn, debug

MUTACOES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_mutacoes.json"
)

_cache  = {"dados": None}
_lock   = threading.Lock()

# ── MAPA DE TRANSMUTAÇÃO ──────────────────────────────────────────────────────
# friccao_id → mutação proposta por vetor gravitacional
# O mesmo padrão de fricção gera mutações diferentes dependendo do vetor ativo
_MAPA_TRANSMUTACAO = {
    "velocidade_vs_complexidade": {
        "crescimento": {
            "tipo":      "orgao",
            "nome":      "Órgão de Poda de Complexidade",
            "descricao": "A cada 10 interações, identifica módulos ou abstrações que cresceram sem gerar resultado e propõe remoção. Cresce eliminando o que não serve.",
            "impacto":   "alto",
        },
        "clareza": {
            "tipo":      "modo",
            "nome":      "Modo Compressão Forçada",
            "descricao": "Quando complexidade acumular 3x seguidas, resposta é comprimida para 1 ação concreta. Clareza antes de velocidade.",
            "impacto":   "medio",
        },
        "construcao": {
            "tipo":      "orgao",
            "nome":      "Órgão de Dívida Técnica Visível",
            "descricao": "Rastreia débito técnico como objeto de primeira classe. Nenhuma feature nova sem custo de dívida calculado.",
            "impacto":   "alto",
        },
        "default": {
            "tipo":      "cicatriz",
            "nome":      "Cicatriz: Velocidade sem Direção",
            "descricao": "Padrão gravado: velocidade sem clareza gera débito que trava depois. Avisa antes de repetir.",
            "impacto":   "medio",
        },
    },
    "autonomia_vs_dependencia": {
        "controle": {
            "tipo":      "orgao",
            "nome":      "Órgão de Pressão de Autonomia",
            "descricao": "Detecta quando o usuário pede a mesma coisa 2x e redireciona para construção da capacidade, não para a resposta direta.",
            "impacto":   "alto",
        },
        "crescimento": {
            "tipo":      "modo",
            "nome":      "Modo Espelho de Dependência",
            "descricao": "Quando o mesmo ponto de travamento aparecer 2x, o agente nomeia o padrão antes de responder. O usuário precisa ver o ciclo.",
            "impacto":   "alto",
        },
        "potencia": {
            "tipo":      "orgao",
            "nome":      "Órgão de Transferência de Capacidade",
            "descricao": "Em vez de resolver, ensina o mecanismo. O objetivo é que o usuário resolva sozinho na próxima vez.",
            "impacto":   "medio",
        },
        "default": {
            "tipo":      "cicatriz",
            "nome":      "Cicatriz: Loop de Dependência",
            "descricao": "Padrão documentado: retornar ao mesmo ponto sem construir a capacidade de sair dele.",
            "impacto":   "medio",
        },
    },
    "evolucao_vs_preservacao": {
        "transformacao": {
            "tipo":      "modo",
            "nome":      "Modo Ruptura Controlada",
            "descricao": "Quando estrutura antiga travar evolução 3x, propõe remoção cirúrgica do que está preservando. Muda forma, não só conteúdo.",
            "impacto":   "alto",
        },
        "crescimento": {
            "tipo":      "orgao",
            "nome":      "Órgão de Arqueologia de Projeto",
            "descricao": "Recupera a intenção original do projeto quando o desenvolvimento deriva. Pergunta: 'isso serve o que você queria construir?'",
            "impacto":   "alto",
        },
        "clareza": {
            "tipo":      "necrose",
            "nome":      "Necrose: Estrutura que Ficou Bonita e Inútil",
            "descricao": "Identifica módulos que existem por elegância e não por necessidade. Propõe morte cirúrgica.",
            "impacto":   "medio",
        },
        "default": {
            "tipo":      "cicatriz",
            "nome":      "Cicatriz: Apego à Forma Antiga",
            "descricao": "Padrão documentado: preservar estrutura à custa da evolução que ela deveria servir.",
            "impacto":   "baixo",
        },
    },
    "ousadia_vs_cautela": {
        "transformacao": {
            "tipo":      "modo",
            "nome":      "Modo Experimento Irrevogável",
            "descricao": "Quando risco for punido antes de desenvolver, propõe experimento mínimo irreversível. Obriga a sentir o resultado antes de julgar.",
            "impacto":   "alto",
        },
        "crescimento": {
            "tipo":      "orgao",
            "nome":      "Órgão de Incubação de Risco",
            "descricao": "Protege hipóteses jovens de julgamento prematuro. Nenhuma ideia nova é descartada nas primeiras 3 interações.",
            "impacto":   "medio",
        },
        "default": {
            "tipo":      "cicatriz",
            "nome":      "Cicatriz: Risco Punido Cedo",
            "descricao": "Padrão documentado: abandonar antes do experimento completar o ciclo mínimo.",
            "impacto":   "baixo",
        },
    },
    "decisao_vs_analise": {
        "clareza": {
            "tipo":      "orgao",
            "nome":      "Órgão de Compressão Decisória",
            "descricao": "Quando análise chegar em 3 iterações sem decisão, comprime para escolha binária obrigatória. Sem terceira opção.",
            "impacto":   "alto",
        },
        "potencia": {
            "tipo":      "modo",
            "nome":      "Modo Custo de Não Decidir",
            "descricao": "Calcula e mostra o custo energético de cada ciclo de análise adicional. Tornar o preço da indecisão visível.",
            "impacto":   "medio",
        },
        "default": {
            "tipo":      "cicatriz",
            "nome":      "Cicatriz: Análise sem Conclusão",
            "descricao": "Padrão documentado: análise que nunca chega à decisão — o processo virou o destino.",
            "impacto":   "baixo",
        },
    },
}


# ── PERSISTÊNCIA ─────────────────────────────────────────────────────────────

def _carregar() -> list:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(MUTACOES_PATH):
        _cache["dados"] = []
        return []
    try:
        with open(MUTACOES_PATH, "r", encoding="utf-8") as f:
            _cache["dados"] = json.load(f)
            return _cache["dados"]
    except Exception:
        _cache["dados"] = []
        return []


def _salvar(dados: list):
    try:
        with open(MUTACOES_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("MUTACAO", f"Erro ao salvar: {e}")


def _gerar_id(friccao_id: str, vetor: str) -> str:
    import hashlib
    return hashlib.md5(f"{friccao_id}:{vetor}".encode()).hexdigest()[:8]


# ── TRANSMUTAÇÃO ─────────────────────────────────────────────────────────────

def transmutар(friccao_id: str, vetor: str, evidencias: list) -> dict | None:
    """
    Propõe uma mutação para uma fricção persistente dado o vetor gravitacional.
    Retorna a mutação proposta ou None se já existe ou vetor inválido.
    """
    mapa_friccao = _MAPA_TRANSMUTACAO.get(friccao_id)
    if not mapa_friccao:
        debug("MUTACAO", f"Fricção '{friccao_id}' não mapeada")
        return None

    # Usa o vetor específico ou o default
    template = mapa_friccao.get(vetor) or mapa_friccao.get("default")
    if not template:
        return None

    mid = _gerar_id(friccao_id, vetor)

    # Verifica se mutação já existe
    with _lock:
        dados = _carregar()
        existente = next((m for m in dados if m.get("id") == mid), None)

        if existente:
            if existente.get("status") not in ("rejeitada", "cicatriz"):
                debug("MUTACAO", f"Mutação {mid} já existe com status={existente['status']}")
                return existente

        agora = datetime.now().isoformat()
        mutacao = {
            "id":            mid,
            "friccao_id":    friccao_id,
            "tipo":          template["tipo"],
            "nome":          template["nome"],
            "descricao":     template["descricao"],
            "vetor_alvo":    vetor,
            "impacto":       template["impacto"],
            "status":        "proposta",
            "criada_em":     agora,
            "atualizada_em": agora,
            "evidencias":    [e[:100] for e in evidencias[:5]],
        }

        dados.append(mutacao)
        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()

        info("MUTACAO", (
            f"Mutação proposta: [{template['tipo']}] {template['nome']} "
            f"| vetor={vetor} | impacto={template['impacto']}"
        ))
        return mutacao


def processar() -> list:
    """
    Ponto de entrada principal. Verifica fricções críticas e propõe mutações.
    Chamado pelo pipeline a cada N execuções.
    Retorna lista de mutações novas propostas.
    """
    try:
        from core.friction_chamber import padroes_criticos
        from core.gravity_detector import vetor_principal, calcular_campo
    except ImportError as e:
        warn("MUTACAO", f"Dependência não disponível: {e}")
        return []

    campo  = calcular_campo()
    vetor  = vetor_principal() or "default"
    criticos = padroes_criticos(limiar=3)

    if not criticos or not campo:
        return []

    novas = []
    for friccao in criticos:
        evidencias = [h.get("trecho", "") for h in friccao.get("historico", [])[-5:]]
        mutacao = transmutар(friccao["id"], vetor, evidencias)
        if mutacao and mutacao.get("status") == "proposta":
            novas.append(mutacao)

    if novas:
        info("MUTACAO", f"{len(novas)} mutação(ões) nova(s) proposta(s)")

    return novas


# ── CONSULTA ─────────────────────────────────────────────────────────────────

def listar(status: str = "") -> list:
    """Lista mutações, opcionalmente filtradas por status."""
    dados = _carregar()
    if status:
        return [m for m in dados if m.get("status") == status]
    return dados


def atualizar_status(mid: str, novo_status: str):
    """Atualiza o status de uma mutação (proposta → em_teste → consolidada | rejeitada)."""
    _STATUS_VALIDOS = {"proposta", "em_teste", "consolidada", "rejeitada", "cicatriz"}
    if novo_status not in _STATUS_VALIDOS:
        warn("MUTACAO", f"Status inválido: {novo_status}")
        return

    with _lock:
        dados = _carregar()
        for m in dados:
            if m.get("id") == mid:
                m["status"] = novo_status
                m["atualizada_em"] = datetime.now().isoformat()
                info("MUTACAO", f"Mutação {mid} → {novo_status}")
                break
        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()


def resumo() -> dict:
    """Resumo do estado atual das mutações."""
    dados = _carregar()
    por_status = {}
    por_tipo   = {}
    for m in dados:
        s = m.get("status", "?")
        t = m.get("tipo", "?")
        por_status[s] = por_status.get(s, 0) + 1
        por_tipo[t]   = por_tipo.get(t, 0) + 1

    return {
        "total":      len(dados),
        "por_status": por_status,
        "por_tipo":   por_tipo,
        "propostas":  [m["nome"] for m in dados if m.get("status") == "proposta"],
    }