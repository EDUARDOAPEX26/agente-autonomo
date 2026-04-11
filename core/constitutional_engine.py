"""
core/constitutional_engine.py
Fase 39 — Constituição Adaptativa
Transforma padrões recorrentes em regras vivas.
Regras podem ser quebradas com justificativa.
Quebras são registradas como jurisprudência.
"""
import json
import os
import threading
from datetime import datetime
from core.logger import info, warn, debug

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONSTITUICAO_PATH = os.path.join(_RAIZ, "constituicao_viva.json")
_JURISPRUDENCIA_PATH = os.path.join(_RAIZ, "livro_jurisprudencia.json")
_lock = threading.Lock()

# Mínimo de repetições para promover artigo a cláusula ativa
_MINIMO_PROMOCAO = 3
# Confiança mínima para considerar cláusula estável
_CONFIANCA_ESTAVEL = 0.85


def _carregar_constituicao() -> dict:
    try:
        with open(_CONSTITUICAO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        warn("CONSTITUTIONAL", f"Erro ao carregar constituição: {e}")
        return {"artigos": []}


def _salvar_constituicao(data: dict):
    try:
        with open(_CONSTITUICAO_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("CONSTITUTIONAL", f"Erro ao salvar constituição: {e}")


def _carregar_jurisprudencia() -> dict:
    try:
        with open(_JURISPRUDENCIA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"meta": {}, "precedentes": []}


def _salvar_jurisprudencia(data: dict):
    try:
        with open(_JURISPRUDENCIA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("CONSTITUTIONAL", f"Erro ao salvar jurisprudência: {e}")


def promover_clausulas() -> int:
    """
    Varre os artigos da constituição.
    Artigos com contagem >= _MINIMO_PROMOCAO viram cláusulas ativas.
    Retorna quantas foram promovidas.
    """
    with _lock:
        data = _carregar_constituicao()
        artigos = data.get("artigos", [])
        promovidos = 0

        for artigo in artigos:
            contagem = artigo.get("contagem", 0)
            ja_clausula = artigo.get("clausula_ativa", False)

            if contagem >= _MINIMO_PROMOCAO and not ja_clausula:
                artigo["clausula_ativa"] = True
                artigo["promovido_em"] = datetime.now().isoformat()
                artigo["quebravel"] = True
                artigo["quebras"] = 0
                promovidos += 1
                info("CONSTITUTIONAL", f"Cláusula promovida: {artigo.get('texto','')[:60]}")

        if promovidos > 0:
            data["artigos"] = artigos
            _salvar_constituicao(data)

        return promovidos


def registrar_quebra(clausula_texto: str, justificativa: str, contexto: str = "") -> bool:
    """
    Registra quebra de uma cláusula com justificativa.
    Toda quebra vira precedente na jurisprudência.
    Retorna True se a quebra foi registrada.
    """
    with _lock:
        # Atualiza contador de quebras na constituição
        data = _carregar_constituicao()
        for artigo in data.get("artigos", []):
            if artigo.get("texto", "") == clausula_texto:
                artigo["quebras"] = artigo.get("quebras", 0) + 1
                artigo["ultima_quebra"] = datetime.now().isoformat()
                break
        _salvar_constituicao(data)

        # Registra na jurisprudência
        juris = _carregar_jurisprudencia()
        precedente = {
            "id": f"prec_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "clausula": clausula_texto[:200],
            "justificativa": justificativa[:300],
            "contexto": contexto[:200],
            "timestamp": datetime.now().isoformat(),
        }
        juris["precedentes"].append(precedente)
        _salvar_jurisprudencia(juris)

        info("CONSTITUTIONAL", f"Quebra registrada: {clausula_texto[:50]} | {justificativa[:50]}")
        return True


def verificar_conflito(texto: str) -> list:
    """
    Verifica se um texto conflita com cláusulas ativas.
    Retorna lista de cláusulas conflitantes.
    """
    data = _carregar_constituicao()
    conflitos = []
    texto_lower = texto.lower()

    clausulas_ativas = [
        a for a in data.get("artigos", [])
        if a.get("clausula_ativa") and a.get("confianca", 0) >= _CONFIANCA_ESTAVEL
    ]

    for clausula in clausulas_ativas:
        palavras_clausula = set(
            w for w in clausula.get("texto", "").lower().split()
            if len(w) > 3
        )
        palavras_texto = set(
            w for w in texto_lower.split()
            if len(w) > 3
        )
        # Se há sobreposição significativa mas sentido oposto
        overlap = len(palavras_clausula & palavras_texto)
        if overlap >= 2:
            conflitos.append(clausula.get("texto", "")[:100])

    if conflitos:
        debug("CONSTITUTIONAL", f"Conflitos detectados: {len(conflitos)}")

    return conflitos


def relatorio() -> dict:
    """Retorna resumo do estado da constituição."""
    data = _carregar_constituicao()
    artigos = data.get("artigos", [])
    clausulas_ativas = [a for a in artigos if a.get("clausula_ativa")]
    juris = _carregar_jurisprudencia()

    return {
        "total_artigos": len(artigos),
        "clausulas_ativas": len(clausulas_ativas),
        "total_precedentes": len(juris.get("precedentes", [])),
        "artigos_proximos_promocao": sum(
            1 for a in artigos
            if not a.get("clausula_ativa") and a.get("contagem", 0) >= _MINIMO_PROMOCAO - 1
        ),
    }


# Executa promoção automática ao importar
def inicializar():
    promovidos = promover_clausulas()
    rel = relatorio()
    info("CONSTITUTIONAL", (
        f"Fase 39 inicializada | artigos={rel['total_artigos']} | "
        f"clausulas_ativas={rel['clausulas_ativas']} | "
        f"promovidos={promovidos} | precedentes={rel['total_precedentes']}"
    ))
    return rel