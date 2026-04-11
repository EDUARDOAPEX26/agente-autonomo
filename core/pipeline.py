"""
core/pipeline.py
Motor central — Fase 16 até Fase 34 integradas.
Correção: injeção forte de memórias + proteção contra sobrescrita do prompt.
CORREÇÃO world_state: Tavily direto — elimina 3 chamadas EXA paralelas desnecessárias.
"""

import re
import time
import concurrent.futures
import json
from core.logger import info, warn, erro
from core import book_raciocinio
from core.classifier import classificar
from core.llm import pensar
from core.prompt import get_prompt_com_dados, get_prompt_sem_dados
from core.consensus_checker import tri_source_consensus, _extrair_fato_local

try:
    from core.self_optimizer import verificar_e_otimizar as _otimizar
    _OPTIMIZER_ATIVO = True
except ImportError:
    _OPTIMIZER_ATIVO = False

from core.valuator import avaliar, frase_incerteza
from integrations.exa_client import buscar_exa
from integrations.tavily_client import buscar_online, tavily_disponivel

_historico = []
MAX_HISTORICO = 12
_ESCOPOS_SEM_BUSCA = {"identidade_interna", "internal", "conversacional", "subjective_decision", "mentoria_raciocinio"}

_STOP_WORDS = {
    "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "e", "ou", "que", "se", "por",
    "para", "com", "como", "qual", "quais", "este", "esta", "isso",
    "é", "são", "foi", "ser", "ter", "me", "te", "se", "nos",
}

def _adicionar_historico(role: str, content: str):
    _historico.append({"role": role, "content": content})
    if len(_historico) > MAX_HISTORICO:
        _historico.pop(0)

def _fato_relevante(query: str, fato: str, limiar: int = 1) -> bool:
    if not fato or not query:
        return False
    palavras_query = {
        w.strip("?!.,;:")
        for w in query.lower().split()
        if len(w) >= 3 and w not in _STOP_WORDS
    }
    if not palavras_query:
        return False
    fato_lower = fato.lower()
    matches = sum(1 for w in palavras_query if w in fato_lower)
    relevante = matches >= limiar
    if not relevante:
        warn("PIPELINE", f"Early exit BLOQUEADO — fato irrelevante")
    return relevante

def _processar_cognitivo(msg: str, resposta: str, score: float = 1.0, erro_tipo: str = "ok"):
    avisos = []
    try:
        from core.dissonance_trigger import verificar_dissonancia
        aviso_dis = verificar_dissonancia(msg, modo="deep") or ""
        if aviso_dis:
            avisos.append(aviso_dis)
    except Exception:
        pass

    try:
        from core.belief_tracker import processar as bt_processar
        from core.principle_registry import processar as pr_processar
        bt_processar(msg)
        pr_processar(msg)
    except Exception:
        pass

    try:
        from core.metamorphosis_tracker import processar as mt_processar
        mt_processar(msg, resposta)
    except Exception:
        pass

    try:
        from core.constitution_builder import construir as _construir_const
        _construir_const()
    except Exception:
        pass

    try:
        from core.friction_chamber import registrar as fc_registrar
        fc_registrar(msg, resposta)
        from core.ppd_tracker import registrar as ppd_registrar
        ppd_registrar(msg, resposta)
    except Exception:
        pass

    try:
        from core.gravity_detector import registrar as gd_registrar
        gd_registrar(msg, resposta)
    except Exception:
        pass

    try:
        from core.transmutation_engine import processar as te_processar
        novas_mutacoes = te_processar()
        if novas_mutacoes:
            info("PIPELINE", f"Fase 25: {len(novas_mutacoes)} mutacao(oes) proposta(s)")
    except Exception:
        pass

    try:
        from core.internal_parliament import votar as _votar
        _votar(msg)
    except Exception:
        pass

    try:
        from core.tissue_memory import processar as tm_processar
        tm_processar(msg, resposta)
    except Exception:
        pass

    try:
        from core.experiment_forge import processar as ef_processar
        ef_processar(score=score, erro_tipo=erro_tipo)
    except Exception:
        pass

    try:
        from core.metabolism_controller import estado_atual as mc_estado
        est = mc_estado()
        info("PIPELINE", f"Fase 29: metabolismo={est.get('metabolismo', 'desconhecido')}")
    except Exception:
        pass

    try:
        from core.organ_factory import processar as of_processar
        of_processar(msg, resposta)
    except Exception:
        pass

    try:
        from core.nucleo_vivo.cognitive_genealogy import processar as cg_processar
        cg_processar(msg, resposta)
    except Exception:
        pass

    # FASE 39 — Constituição Adaptativa
    try:
        from core.constitutional_engine import promover_clausulas, verificar_conflito
        promover_clausulas()
        conflitos = verificar_conflito(msg)
        if conflitos:
            warn("PIPELINE", f"Fase 39: conflito com {len(conflitos)} clausula(s) ativa(s)")
    except Exception:
        pass

    # FASE 37 — Câmara de Contra-Futuros
    try:
        from core.counterfutures import detectar as cf_detectar
        intervencoes = cf_detectar(msg, resposta)
        if intervencoes:
            warn("PIPELINE", f"Fase 37: {len(intervencoes)} intervencao(oes) recomendada(s)")
    except Exception:
        pass

    # FASE 38 — Economia Sacrificial
    try:
        from core.sacrificial_economy import analisar as se_analisar
        candidatos = se_analisar()
        if candidatos:
            warn("PIPELINE", f"Fase 38: {len(candidatos)} candidato(s) a sacrificio")
    except Exception:
        pass

    # FASE 40 — Diretor de Trajetória
    try:
        from core.trajectory_director import calcular_vetor
        vetor = calcular_vetor()
        direcao = vetor.get("direcao", "aguardar")
        if direcao != "aguardar":
            info("PIPELINE", f"Fase 40: direcao={direcao} | {vetor.get('justificativa','')[:60]}")
    except Exception:
        pass

    return "\n\n".join(avisos) if avisos else ""

def _tri_source_paralelo(pergunta: str) -> dict:
    from core.consensus_checker import _buscar, _extrair_fato, _similar, _extrair_dominio
    queries = [
        f"{pergunta} site oficial",
        f"{pergunta} noticia recente",
        f"{pergunta} wikipedia",
    ]
    def buscar_query(q):
        try:
            resultados = _buscar(q)
            if resultados:
                fato = _extrair_fato(resultados[0])
                url = resultados[0].get("url", q)
                if fato:
                    return fato, url
        except Exception:
            pass
        return None, None

    fatos = []
    fontes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futuros = {executor.submit(buscar_query, q): q for q in queries}
        for futuro in concurrent.futures.as_completed(futuros, timeout=15):
            try:
                fato, url = futuro.result()
                if fato:
                    fatos.append(fato)
                    fontes.append(url or "exa")
            except Exception:
                pass

    if not fatos:
        return {"resposta": "Sem dados disponiveis no momento.", "fontes": [], "consenso": 0}
    if len(fatos) == 1:
        return {"resposta": fatos[0], "fontes": fontes, "consenso": 1}

    pares_concordam = 0
    fato_consenso = fatos[0]
    for i in range(len(fatos)):
        for j in range(i + 1, len(fatos)):
            if _similar(fatos[i], fatos[j]):
                pares_concordam += 1
                fato_consenso = fatos[i]

    dominios = {_extrair_dominio(f) for f in fontes}
    if pares_concordam >= 1 and len(dominios) >= 2:
        consenso = min(3, pares_concordam + 1)
        info("PIPELINE", f"Consenso paralelo {consenso}/3")
        return {"resposta": fato_consenso, "fontes": fontes, "consenso": consenso}

    return {"resposta": fatos[0], "fontes": fontes, "consenso": 1}

def executar_pipeline(msg: str) -> tuple:
    info("PIPELINE", f"Iniciando: '{msg[:60]}'")
    t0 = time.time()

    # 1. CLASSIFICACAO
    classificacao = classificar(msg, "", get_groq_fn=None)
    escopo = classificacao.get("escopo", "encyclopedic")
    volatilidade = classificacao.get("volatilidade", "baixa")
    n_fontes = classificacao.get("n_fontes", 1)
    info("PIPELINE", f"escopo={escopo} | volatilidade={volatilidade} | n_fontes={n_fontes}")

    _adicionar_historico("user", msg)

    dados_online = None
    api_busca = "nenhuma"

    # 2. BUSCA POR ESCOPO
    if escopo == "world_state":
        # Tavily direto — dados em tempo real, EXA consensus sempre falha para preços
        if tavily_disponivel():
            dados_tavily = buscar_online(msg)
            if dados_tavily and len(dados_tavily.strip()) >= 50:
                dados_online = dados_tavily
                api_busca = "tavily"
                info("PIPELINE", f"world_state → Tavily direto ({len(dados_tavily)} chars)")
            else:
                warn("PIPELINE", "Tavily sem resultado para world_state — tentando EXA")
        if not dados_online:
            # Fallback: EXA se Tavily falhou ou indisponível
            try:
                tri = _tri_source_paralelo(msg)
                dados_online = tri["resposta"]
                api_busca = "exa_consensus"
            except Exception as e:
                warn("PIPELINE", f"EXA fallback falhou: {e}")
                dados_online = buscar_exa(msg)
                api_busca = "exa"

    elif escopo in ("merchant_specific", "encyclopedic"):
        dados_online = buscar_exa(msg)
        api_busca = "exa"
        info("PIPELINE", f"EXA direto (escopo={escopo}): {msg[:50]}")

        _early_exit_bloqueado = book_raciocinio.escopo_deve_usar_llm(escopo)
        if not _early_exit_bloqueado and dados_online and len(dados_online.strip()) >= 50:
            fato = _extrair_fato_local(dados_online)
            if fato and any(c.isdigit() for c in fato) and _fato_relevante(msg, fato):
                info("PIPELINE", f"EARLY EXIT {escopo} — fato numérico — 0 LLM")
                _adicionar_historico("assistant", fato)
                book_raciocinio.registrar(
                    pergunta=msg, estrategia="exa_early_exit", erro_tipo="ok", score=1.0,
                    escopo=escopo, latencia_ms=int((time.time()-t0)*1000), api_usada="exa",
                )
                aviso = _processar_cognitivo(msg, fato, score=1.0, erro_tipo="ok")
                if aviso:
                    fato = aviso + "\n\n" + fato
                return fato, "exa"

    elif escopo in _ESCOPOS_SEM_BUSCA:
        dados_online = None
        api_busca = "nenhuma"
        info("PIPELINE", f"Escopo {escopo} — 0 busca externa")

    # 3. FALLBACK TAVILY (para encyclopedic/merchant que não tiveram dado suficiente)
    if (not dados_online or len(dados_online.strip()) < 50) and escopo not in _ESCOPOS_SEM_BUSCA:
        if tavily_disponivel():
            warn("PIPELINE", "EXA sem resultado — tentando Tavily")
            dados_tavily = buscar_online(msg)
            if dados_tavily and len(dados_tavily.strip()) >= 50:
                dados_online = dados_tavily
                api_busca = "tavily"

    # === INSTRUÇÕES EXTRAS ===
    instrucao_ppd = ""
    try:
        from core.ppd_tracker import papel_agente, instrucao_papel
        instrucao_ppd = instrucao_papel(papel_agente())
    except Exception:
        pass

    instrucao_gravidade = ""
    if escopo in ("encyclopedic", "world_state", "merchant_specific"):
        try:
            from core.gravity_detector import descricao_vetor
            vetor = descricao_vetor()
            if vetor:
                instrucao_gravidade = f"\n[CONTEXTO DE GRAVIDADE: {vetor}]"
        except Exception:
            pass

    instrucao_parlamento = ""
    try:
        from core.internal_parliament import votar as _votar_ctx, instrucao_regime
        _regime = _votar_ctx(msg)
        instrucao_parlamento = instrucao_regime(_regime)
    except Exception:
        pass

    instrucao_metabolismo = ""
    try:
        from core.metabolism_controller import instrucao_metabolismo as _instr_met
        instrucao_metabolismo = _instr_met()
    except Exception:
        pass

    instrucao_orgaos = ""
    try:
        from core.organ_factory import instrucoes_ativas
        instrucao_orgaos = instrucoes_ativas()
    except Exception:
        pass

    # FASE 40 — instrução de trajetória para o LLM
    instrucao_trajetoria = ""
    try:
        from core.trajectory_director import instrucao_trajetoria as _instr_traj
        instrucao_trajetoria = _instr_traj()
    except Exception:
        pass

    # === FASE 33/34 — INJEÇÃO FORÇADA DIRETA DOS LIVROS ===
    instrucao_nucleo_vivo = ""
    try:
        from core.nucleo_vivo.nucleo_vivo_bridge import nucleo_vivo_bridge
        resultado_nucleo = nucleo_vivo_bridge.process_query(msg)

        if isinstance(resultado_nucleo, dict):
            instrucao_nucleo_vivo = resultado_nucleo.get("instrucao_memoria_forte", "") or ""
        else:
            instrucao_nucleo_vivo = str(resultado_nucleo) if resultado_nucleo else ""

        if instrucao_nucleo_vivo and len(instrucao_nucleo_vivo.strip()) > 100:
            info("PIPELINE", "Fase 33/34: Injeção FORÇADA de conteúdo dos livros ativada")
        else:
            warn("PIPELINE", "Fase 33/34: Injeção retornou conteúdo insuficiente")
    except Exception as e:
        warn("PIPELINE", f"Fase 33/34 falhou: {e}")
        instrucao_nucleo_vivo = ""

    instrucao_extra = (
        instrucao_ppd +
        instrucao_gravidade +
        instrucao_parlamento +
        instrucao_metabolismo +
        instrucao_orgaos +
        instrucao_trajetoria +
        ("\n\n" + instrucao_nucleo_vivo if instrucao_nucleo_vivo else "")
    )

    if dados_online and len(dados_online.strip()) >= 50:
        contexto_sistema = (
            f"{get_prompt_com_dados()}{instrucao_extra}\n\n"
            f"DADOS DA INTERNET — USE PARA RESPONDER:\n{dados_online.strip()[:1500]}"
        )
        max_tokens = 800
    else:
        warn("PIPELINE", "Sem dados externos — modo sem dados")
        contexto_sistema = get_prompt_sem_dados() + instrucao_extra
        max_tokens = 800

    # Fix reincidência
    if escopo == "subjective_decision":
        try:
            from core.book_raciocinio import buscar
            entrada_ant = buscar(msg)
            if entrada_ant and entrada_ant.get("erro_tipo") == "reincidencia":
                resposta_final = (
                    "Voce fez essa pergunta antes e eu dei uma resposta padrao.\n\n"
                    "Isso sugere que a duvida nao e sobre a decisao em si "
                    "— e sobre o que voce teme perder se errar.\n\n"
                    "O que especificamente esta te impedindo de decidir?"
                )
                _adicionar_historico("assistant", resposta_final)
                book_raciocinio.registrar(
                    pergunta=msg, estrategia="anti_loop", erro_tipo="ok", score=1.0,
                    escopo=escopo, latencia_ms=int((time.time()-t0)*1000), api_usada="anti_loop",
                )
                aviso = _processar_cognitivo(msg, resposta_final, score=1.0, erro_tipo="ok")
                if aviso:
                    resposta_final = aviso + "\n\n" + resposta_final
                return resposta_final, "anti_loop"
        except Exception:
            pass

    # 5. LLM - FORÇANDO A INSTRUÇÃO NO INÍCIO DO PROMPT
    system_prompt = contexto_sistema
    if "instrucao_memoria_forte" in locals() and instrucao_nucleo_vivo:
        system_prompt = instrucao_nucleo_vivo + "\n\n" + system_prompt

    msgs = [{"role": "system", "content": system_prompt}] + _historico
    resposta_llm, api_llm = pensar(msgs, max_tokens)
    resposta_llm = resposta_llm.strip() if resposta_llm else ""
    info("PIPELINE", f"LLM ({api_llm}): {resposta_llm[:80]}")

    # 6. VALUATOR
    av = avaliar(msg, resposta_llm, {
        "consenso": None,
        "fontes": [],
        "usou_tool": False,
        "volatilidade": volatilidade,
        "escopo": escopo,
    })

    if av["acao"] == "descartar":
        warn("PIPELINE", f"Valuator DESCARTAR — {av['erro_tipo']}")
        resposta_final = "Nao consegui gerar uma resposta adequada. Tente reformular."
        api_final = "valuator"
    elif av["acao"] == "responder_com_incerteza":
        warn("PIPELINE", f"Valuator INCERTEZA — score={av['score']}")
        resposta_final = resposta_llm if resposta_llm else frase_incerteza()
        api_final = api_llm
    else:
        resposta_final = resposta_llm
        api_final = api_llm

    _adicionar_historico("assistant", resposta_final)

    book_raciocinio.registrar(
        pergunta=msg, estrategia=api_final, erro_tipo=av.get("erro_tipo","ok"),
        score=av.get("score",1.0), escopo=escopo,
        latencia_ms=int((time.time()-t0)*1000), api_usada=api_final,
    )

    if _OPTIMIZER_ATIVO:
        try:
            _otimizar()
        except Exception:
            pass

    aviso = _processar_cognitivo(msg, resposta_final, score=av.get("score",1.0), erro_tipo=av.get("erro_tipo","ok"))
    if aviso:
        resposta_final = aviso + "\n\n" + resposta_final

    return resposta_final, api_final