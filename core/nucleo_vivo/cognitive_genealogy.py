"""
core/nucleo_vivo/cognitive_genealogy.py
Fase 34 — Genealogia Cognitiva.

Rastreia a linhagem completa de cada comportamento atual.
Cada mutação, crença ou princípio tem um ancestral rastreável.

Correção Fase 35: paths corrigidos — arquivo está em core/nucleo_vivo/
portanto precisa de 3x dirname para chegar na raiz do projeto.
Correção processar(): cache não é invalidado a cada chamada — reconstrói
só quando necessário (cache vazio ou a cada 30 nós).
"""

import json
import os
import threading
from datetime import datetime
from core.logger import info, debug, warn

# core/nucleo_vivo/ → core/ → raiz/
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

GENEALOGIA_PATH = os.path.join(_RAIZ, "livro_genealogia.json")

_cache = {"dados": None}
_lock  = threading.Lock()

_TIPOS_NO = {
    "friccao":   "Fricção detectada — padrão de tensão repetida",
    "mutacao":   "Mutação proposta e consolidada",
    "crenca":    "Crença formada ou revisada",
    "principio": "Princípio extraído de padrão consistente",
    "tecido":    "Tecido cognitivo fortalecido",
    "orfao":     "Comportamento sem ancestral rastreável",
}


def _carregar() -> dict:
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(GENEALOGIA_PATH):
        _cache["dados"] = {"nos": {}, "arestas": [], "orfaos": []}
        return _cache["dados"]
    try:
        with open(GENEALOGIA_PATH, "r", encoding="utf-8") as f:
            _cache["dados"] = json.load(f)
            return _cache["dados"]
    except Exception as e:
        warn("GENEALOGIA", f"Erro ao carregar: {e}")
        _cache["dados"] = {"nos": {}, "arestas": [], "orfaos": []}
        return _cache["dados"]


def _salvar(dados: dict):
    try:
        with open(GENEALOGIA_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("GENEALOGIA", f"Erro ao salvar: {e}")


def _adicionar_no(dados: dict, id_no: str, tipo: str, nome: str,
                  descricao: str = "", timestamp: str = "") -> dict:
    if id_no not in dados["nos"]:
        dados["nos"][id_no] = {
            "id":        id_no,
            "tipo":      tipo,
            "nome":      nome,
            "descricao": descricao[:200] if descricao else "",
            "timestamp": timestamp or datetime.now().isoformat(),
        }
    return dados


def _adicionar_aresta(dados: dict, origem: str, destino: str, relacao: str) -> dict:
    aresta = {"origem": origem, "destino": destino, "relacao": relacao}
    if aresta not in dados["arestas"]:
        dados["arestas"].append(aresta)
    return dados


def construir() -> dict:
    """
    Lê livro_mutacoes, livro_crencas, livro_principios e livro_friccao
    e constrói a árvore genealógica completa.
    """
    with _lock:
        dados = {"nos": {}, "arestas": [], "orfaos": []}
        dados = _processar_friccoes(dados)
        dados = _processar_mutacoes(dados)
        dados = _processar_crencas(dados)
        dados = _processar_principios(dados)
        dados = _detectar_orfaos(dados)

        _cache["dados"] = dados
        threading.Thread(target=_salvar, args=(dados,), daemon=True).start()

        info("GENEALOGIA", (
            f"Árvore construída: {len(dados['nos'])} nós | "
            f"{len(dados['arestas'])} relações | "
            f"{len(dados['orfaos'])} órfãos"
        ))
        return dados


def _processar_friccoes(dados: dict) -> dict:
    try:
        path = os.path.join(_RAIZ, "livro_friccao.json")
        if not os.path.exists(path):
            debug("GENEALOGIA", f"livro_friccao.json não encontrado em {path}")
            return dados
        with open(path, "r", encoding="utf-8") as f:
            friccoes = json.load(f)
        for fid, fr in friccoes.items():
            dados = _adicionar_no(
                dados, fid, "friccao",
                nome=fid.replace("_", " ").title(),
                descricao=f"Contagem: {fr.get('contagem', 0)} | Última: {fr.get('ultima_vez', '')}",
                timestamp=fr.get("ultima_vez", "")
            )
        debug("GENEALOGIA", f"{len(friccoes)} fricções carregadas")
    except Exception as e:
        debug("GENEALOGIA", f"Friccoes: {e}")
    return dados


def _processar_mutacoes(dados: dict) -> dict:
    try:
        path = os.path.join(_RAIZ, "livro_mutacoes.json")
        if not os.path.exists(path):
            debug("GENEALOGIA", f"livro_mutacoes.json não encontrado em {path}")
            return dados
        with open(path, "r", encoding="utf-8") as f:
            mutacoes = json.load(f)
        for m in mutacoes:
            mid    = m.get("id", "")
            frid   = m.get("friccao_id", "")
            status = m.get("status", "")
            if not mid:
                continue
            dados = _adicionar_no(
                dados, mid, "mutacao",
                nome=m.get("nome", mid),
                descricao=f"[{status}] {m.get('descricao', '')}",
                timestamp=m.get("criada_em", "")
            )
            if frid and frid in dados["nos"]:
                dados = _adicionar_aresta(dados, frid, mid, "gerou_mutacao")
            elif frid:
                dados = _adicionar_no(dados, frid, "friccao",
                                      nome=frid.replace("_", " ").title(),
                                      descricao="Fricção ancestral (histórico)")
                dados = _adicionar_aresta(dados, frid, mid, "gerou_mutacao")
        debug("GENEALOGIA", f"{len(mutacoes)} mutações carregadas")
    except Exception as e:
        debug("GENEALOGIA", f"Mutacoes: {e}")
    return dados


def _processar_crencas(dados: dict) -> dict:
    try:
        path = os.path.join(_RAIZ, "livro_crencas.json")
        if not os.path.exists(path):
            return dados
        with open(path, "r", encoding="utf-8") as f:
            crencas = json.load(f)
        if not isinstance(crencas, list):
            return dados
        for c in crencas:
            cid    = c.get("id", "")
            status = c.get("status", "ativa")
            if not cid or status == "invalidada":
                continue
            dominio = c.get("dominio", "geral")
            dados = _adicionar_no(
                dados, cid, "crenca",
                nome=c.get("texto", cid)[:80],
                descricao=f"domínio={dominio} | confiança={c.get('confianca', 0):.2f}",
                timestamp=c.get("timestamp", "")
            )
            _conectar_crenca_a_ancestral(dados, cid, dominio)
    except Exception as e:
        debug("GENEALOGIA", f"Crencas: {e}")
    return dados


def _conectar_crenca_a_ancestral(dados: dict, cid: str, dominio: str):
    dominio_lower = dominio.lower()
    for nid, no in dados["nos"].items():
        if no["tipo"] in ("mutacao", "friccao"):
            nome_lower = no["nome"].lower()
            palavras   = [w for w in dominio_lower.split() if len(w) > 3]
            if any(w in nome_lower for w in palavras):
                dados = _adicionar_aresta(dados, nid, cid, "originou_crenca")
                return


def _processar_principios(dados: dict) -> dict:
    try:
        path = os.path.join(_RAIZ, "livro_principios.json")
        if not os.path.exists(path):
            return dados
        with open(path, "r", encoding="utf-8") as f:
            principios = json.load(f)
        if not isinstance(principios, list):
            return dados
        for p in principios:
            pid    = p.get("id", "")
            status = p.get("status", "ativo")
            if not pid or status == "revogado":
                continue
            dominio = p.get("dominio", "")
            dados = _adicionar_no(
                dados, pid, "principio",
                nome=p.get("texto", pid)[:80],
                descricao=f"categoria={p.get('categoria', '')} | confiança={p.get('confianca', 0):.2f}",
                timestamp=p.get("timestamp", "")
            )
            if dominio:
                _conectar_principio_a_crenca(dados, pid, dominio)
    except Exception as e:
        debug("GENEALOGIA", f"Principios: {e}")
    return dados


def _conectar_principio_a_crenca(dados: dict, pid: str, dominio: str):
    dominio_lower = dominio.lower()
    for nid, no in dados["nos"].items():
        if no["tipo"] == "crenca":
            nome_lower = no["nome"].lower()
            palavras   = [w for w in dominio_lower.split() if len(w) > 3]
            if any(w in nome_lower for w in palavras):
                dados = _adicionar_aresta(dados, nid, pid, "consolidou_principio")
                return


def _detectar_orfaos(dados: dict) -> dict:
    destinos = {a["destino"] for a in dados["arestas"]}
    orfaos   = []
    for nid, no in dados["nos"].items():
        if nid not in destinos and no["tipo"] != "friccao":
            orfaos.append({
                "id":   nid,
                "tipo": no["tipo"],
                "nome": no["nome"],
            })
    dados["orfaos"] = orfaos
    if orfaos:
        warn("GENEALOGIA", f"{len(orfaos)} comportamento(s) órfão(s) detectado(s)")
    return dados


def linhagem(id_no: str) -> list:
    dados = _carregar()
    if not dados["nos"]:
        dados = construir()
    visitados = set()
    cadeia    = []

    def _subir(nid):
        if nid in visitados:
            return
        visitados.add(nid)
        ancestrais = [a["origem"] for a in dados["arestas"] if a["destino"] == nid]
        for anc in ancestrais:
            _subir(anc)
        no = dados["nos"].get(nid, {})
        if no:
            cadeia.append({
                "id":        nid,
                "tipo":      no.get("tipo", ""),
                "nome":      no.get("nome", ""),
                "descricao": no.get("descricao", ""),
                "timestamp": no.get("timestamp", ""),
            })

    _subir(id_no)
    return cadeia


def descendentes(id_no: str) -> list:
    dados = _carregar()
    if not dados["nos"]:
        dados = construir()
    visitados = set()
    resultado = []

    def _descer(nid):
        if nid in visitados:
            return
        visitados.add(nid)
        filhos = [a["destino"] for a in dados["arestas"] if a["origem"] == nid]
        for filho in filhos:
            no = dados["nos"].get(filho, {})
            if no:
                resultado.append({
                    "id":   filho,
                    "tipo": no.get("tipo", ""),
                    "nome": no.get("nome", ""),
                })
            _descer(filho)

    _descer(id_no)
    return resultado


def orfaos() -> list:
    dados = _carregar()
    if not dados["nos"]:
        dados = construir()
    return dados.get("orfaos", [])


def resumo() -> dict:
    dados = _carregar()
    if not dados["nos"]:
        dados = construir()
    por_tipo = {}
    for no in dados["nos"].values():
        t = no["tipo"]
        por_tipo[t] = por_tipo.get(t, 0) + 1
    return {
        "total_nos":     len(dados["nos"]),
        "total_arestas": len(dados["arestas"]),
        "por_tipo":      por_tipo,
        "orfaos":        len(dados.get("orfaos", [])),
    }


def narrativa_linhagem(id_no: str) -> str:
    cadeia = linhagem(id_no)
    if not cadeia:
        return f"Nenhuma linhagem encontrada para '{id_no}'."
    partes = []
    for no in cadeia:
        tipo = no["tipo"]
        nome = no["nome"]
        ts   = no.get("timestamp", "")[:10]
        if tipo == "friccao":
            partes.append(f"nasceu da fricção '{nome}'" + (f" em {ts}" if ts else ""))
        elif tipo == "mutacao":
            partes.append(f"gerou a mutação '{nome}'" + (f" em {ts}" if ts else ""))
        elif tipo == "crenca":
            partes.append(f"formou a crença '{nome}'")
        elif tipo == "principio":
            partes.append(f"consolidou o princípio '{nome}'")
        elif tipo == "orfao":
            partes.append(f"comportamento sem ancestral: '{nome}'")
    no_atual  = cadeia[-1]["nome"] if cadeia else id_no
    narrativa = f"'{no_atual}' — " + ", ".join(partes) + "."
    return narrativa


def processar(msg: str = "", resposta: str = "") -> None:
    """
    Chamado pelo pipeline após cada interação.
    Reconstrói a árvore só quando necessário — cache vazio ou a cada 30 nós.
    NÃO invalida cache a cada chamada (evita rebuild constante).
    """
    try:
        dados = _carregar()
        n_nos = len(dados.get("nos", {}))
        # Reconstrói se vazio ou quando o número de nós é múltiplo de 30
        if n_nos == 0 or (n_nos > 0 and n_nos % 30 == 0):
            construir()
    except Exception as e:
        debug("GENEALOGIA", f"processar: {e}")