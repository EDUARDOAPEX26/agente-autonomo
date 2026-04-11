# core/temporal_council.py
"""
Fase 22 — Herança Cognitiva Viva.
Permite consultar "versões anteriores" do usuário — o que acreditava antes,
o que mudou, o que permaneceu, e o que o Eduardo de hoje diria ao de antes.

O "conselho temporal" compara cápsulas cognitivas de datas diferentes
e sintetiza a evolução verificável.

Salva consultas significativas em livro_conselhos_temporais.json.
"""

import json
import os
import threading
from datetime import datetime
from core.logger import info, warn, debug

CONSELHOS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_conselhos_temporais.json"
)

_cache = {"dados": None}
_lock  = threading.Lock()


def _carregar() -> dict:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(CONSELHOS_PATH):
        _cache["dados"] = {"descricao": "Conselhos entre versões temporais",
                           "versao": 1, "criado_em": "", "atualizado_em": "",
                           "conselhos": []}
        return _cache["dados"]
    try:
        with open(CONSELHOS_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
            _cache["dados"] = dados
            return dados
    except Exception as e:
        warn("CONSELHOS", f"Erro ao carregar: {e}")
        _cache["dados"] = {"conselhos": []}
        return _cache["dados"]


def _salvar(dados: dict):
    try:
        with open(CONSELHOS_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("CONSELHOS", f"Erro ao salvar: {e}")


# ── COMPARAÇÃO DE CÁPSULAS ────────────────────────────────────────────────────

def _textos_de(capsula: dict, tipo: str) -> set:
    """Extrai textos normalizados de uma cápsula por tipo (principios/crencas)."""
    return {item["texto"][:80].lower() for item in capsula.get(tipo, [])}


def _comparar_capsulas(antiga: dict, nova: dict) -> dict:
    """
    Compara duas cápsulas e retorna o que mudou, o que permaneceu e o que surgiu.
    """
    result = {
        "permaneceu":  [],  # estava antes e continua
        "surgiu":      [],  # novo, não estava antes
        "desapareceu": [],  # estava antes, não está mais
    }

    for tipo in ("principios", "crencas"):
        textos_antigos = _textos_de(antiga, tipo)
        textos_novos   = _textos_de(nova,   tipo)

        for item in nova.get(tipo, []):
            t = item["texto"][:80].lower()
            if t in textos_antigos:
                result["permaneceu"].append({"texto": item["texto"][:120], "tipo": tipo})
            else:
                result["surgiu"].append({"texto": item["texto"][:120], "tipo": tipo})

        for item in antiga.get(tipo, []):
            t = item["texto"][:80].lower()
            if t not in textos_novos:
                result["desapareceu"].append({"texto": item["texto"][:120], "tipo": tipo})

    return result


# ── CONSULTAS TEMPORAIS ───────────────────────────────────────────────────────

def consultar_evolucao() -> dict:
    """
    Compara a cápsula mais antiga com a mais recente.
    Retorna o que mudou, surgiu e permaneceu na identidade do usuário.
    """
    try:
        from core.legacy_exporter import listar_capsulas
        capsulas = listar_capsulas()
    except Exception as e:
        warn("CONSELHOS", f"Sem cápsulas disponíveis: {e}")
        return {"erro": "Nenhuma cápsula encontrada"}

    if len(capsulas) < 2:
        return {
            "mensagem": "Apenas uma cápsula disponível — continue interagindo para construir histórico",
            "capsulas": len(capsulas),
        }

    antiga = capsulas[0]
    nova   = capsulas[-1]

    diff = _comparar_capsulas(antiga, nova)

    resultado = {
        "periodo":      f"{antiga['gerado_em'][:10]} → {nova['gerado_em'][:10]}",
        "capsulas":     len(capsulas),
        "permaneceu":   diff["permaneceu"],
        "surgiu":       diff["surgiu"],
        "desapareceu":  diff["desapareceu"],
        "estabilidade": len(diff["permaneceu"]) / max(1, len(diff["permaneceu"]) + len(diff["desapareceu"])),
    }

    info("CONSELHOS", (
        f"Evolução {resultado['periodo']} | "
        f"permaneceu={len(diff['permaneceu'])} | "
        f"surgiu={len(diff['surgiu'])} | "
        f"desapareceu={len(diff['desapareceu'])}"
    ))

    return resultado


def conselho_para_passado() -> str:
    """
    O que o Eduardo de hoje diria ao Eduardo de antes?
    Sintetiza as maiores mudanças em forma de conselho.
    """
    evolucao = consultar_evolucao()

    if "erro" in evolucao or "mensagem" in evolucao:
        return evolucao.get("mensagem", evolucao.get("erro", "Sem dados suficientes."))

    linhas = [
        f"=== CONSELHO DO PRESENTE PARA O PASSADO ===",
        f"Período analisado: {evolucao['periodo']}",
        "",
    ]

    if evolucao["surgiu"]:
        linhas.append("O que você desenvolveu que antes não tinha:")
        for item in evolucao["surgiu"][:5]:
            linhas.append(f"  + {item['texto'][:100]}")
        linhas.append("")

    if evolucao["desapareceu"]:
        linhas.append("O que você superou ou revisou:")
        for item in evolucao["desapareceu"][:5]:
            linhas.append(f"  - {item['texto'][:100]}")
        linhas.append("")

    if evolucao["permaneceu"]:
        linhas.append("O que ficou constante — sua base estável:")
        for item in evolucao["permaneceu"][:5]:
            linhas.append(f"  = {item['texto'][:100]}")
        linhas.append("")

    estab = evolucao.get("estabilidade", 0)
    linhas.append(f"Índice de estabilidade: {estab:.0%}")

    return "\n".join(linhas)


def registrar_conselho(texto: str, contexto: str = ""):
    """
    Salva um conselho significativo no livro_conselhos_temporais.json.
    Chamado quando o usuário pede explicitamente uma reflexão temporal.
    """
    agora = datetime.now().isoformat()
    conselho = {
        "texto":      texto[:500],
        "contexto":   contexto[:200],
        "gerado_em":  agora,
    }

    with _lock:
        dados = _carregar()
        dados["conselhos"].append(conselho)
        if len(dados["conselhos"]) > 100:
            dados["conselhos"] = dados["conselhos"][-100:]
        dados["atualizado_em"] = agora
        if not dados.get("criado_em"):
            dados["criado_em"] = agora
        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()

    info("CONSELHOS", f"Conselho registrado: '{texto[:50]}'")


def versoes_do_usuario() -> str:
    """
    Resumo textual das versões temporais do usuário baseado nas cápsulas.
    """
    try:
        from core.legacy_exporter import listar_capsulas
        capsulas = listar_capsulas()
    except Exception:
        return "Sem cápsulas disponíveis."

    if not capsulas:
        return "Nenhuma cápsula gerada ainda."

    linhas = [f"=== VERSÕES TEMPORAIS — {len(capsulas)} snapshots ===", ""]

    for i, c in enumerate(capsulas, 1):
        n_p = len(c.get("principios", []))
        n_c = len(c.get("crencas", []))
        integ = c.get("integridade", {}).get("score", 0)
        linhas.append(
            f"[{c['gerado_em'][:10]}] {c['titulo']} | "
            f"{n_p} princípios | {n_c} crenças | integridade={integ:.0%}"
        )

    return "\n".join(linhas)