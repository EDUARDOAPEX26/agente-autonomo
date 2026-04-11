"""
core/internal_parliament.py
Fase 26 — Parlamento Interno com pesos dinâmicos reais.

CORREÇÃO v5:
- Threading removido do _salvar — escrita síncrona dentro do lock (fix corrupção)
- Jitter reduzido de 0.03 → 0.005 (fix instabilidade de identidade)
- _normalizar_pesos e _corrigir_ratio_sessao unificadas — sem luta interna
- Sinais expandidos com escopo + query real
"""
import json, os, threading, random
from datetime import datetime
from core.logger import info, warn

PARLAMENTO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "livro_parlamento.json"
)
_cache = {"dados": None}
_lock  = threading.Lock()

_PESO_BASE_PADRAO = 0.143

_FACCOES = {
    "impulso":       {"peso_base": _PESO_BASE_PADRAO, "regime": "acao"},
    "prudencia":     {"peso_base": _PESO_BASE_PADRAO, "regime": "cautela"},
    "ruptura":       {"peso_base": _PESO_BASE_PADRAO, "regime": "ruptura"},
    "continuidade":  {"peso_base": _PESO_BASE_PADRAO, "regime": "preservacao"},
    "elegancia":     {"peso_base": _PESO_BASE_PADRAO, "regime": "compressao"},
    "sobrevivencia": {"peso_base": _PESO_BASE_PADRAO, "regime": "protecao"},
    "ambicao":       {"peso_base": _PESO_BASE_PADRAO, "regime": "expansao"},
}

_SINAIS = {
    "impulso":       ["rápido","urgente","agora","logo","já","prazo","imediato","rápida","quanto tempo"],
    "prudencia":     ["cuidado","risco","erro","falhou","quebrou","cautela","perigoso","problema","bug","corrigir"],
    "ruptura":       ["mudar","abandonar","novo","diferente","refatorar","reescrever","revolucionar","substituir","trocar"],
    "continuidade":  ["consistente","manter","preservar","histórico","padrão","estável","continuar","manutenção"],
    "elegancia":     ["limpo","simples","elegante","menos","reduzir","complexo","sentido","vida","filosofia","otimizar"],
    "sobrevivencia": ["colapso","perda","crítico","emergência","travou","quebrou tudo","falha total","estouro"],
    "ambicao":       ["crescer","evoluir","próximo nível","expandir","escalar","melhorar","fase","avançar","implementar"],
}

# Sinais por escopo — reforço direto sem depender de palavras-chave
_SINAIS_ESCOPO = {
    "conversacional": "continuidade",
    "internal":       "elegancia",
    "encyclopedic":   "ambicao",
    "world_state":    "impulso",
    "subjective_decision": "prudencia",
    "mentoria_raciocinio": "continuidade",
    "ruptura":        "ruptura",
}

_MAPA_POLYPHONIC = {
    "Guardião":   {"continuidade": 0.09, "prudencia":    0.03},
    "Visionário": {"ambicao":      0.09, "ruptura":      0.04},
    "Herético":   {"ruptura":      0.10, "ambicao":      0.03},
    "Predador":   {"impulso":      0.09, "sobrevivencia":0.03},
    "Coruja":     {"elegancia":    0.10, "continuidade": 0.03},
}

_PESO_MAX       = 0.35
_PESO_MIN       = 0.05
_INC_VITORIA    = 0.008
_DEC_DERROTA    = 0.006
_LIMIAR_MINORIA = 0.08
_BOOST_MINORIA  = 0.05
_JITTER         = 0.005  # FIX v5: reduzido de 0.03 — identidade consistente
_RATIO_MAX      = 4.5    # FIX v5: único limiar unificado


def _estado_inicial():
    return {f: {
        "peso":           _FACCOES[f]["peso_base"],
        "vitorias":       0,
        "ultima_vitoria": None,
    } for f in _FACCOES}


def _ratio_atual(dados: dict) -> float:
    pesos = [dados[f].get("peso", _FACCOES[f]["peso_base"]) for f in _FACCOES if f in dados]
    if not pesos or min(pesos) <= 0:
        return 0.0
    return round(max(pesos) / min(pesos), 1)


def _normalizar_e_corrigir(raw: dict, contexto: str = "boot") -> dict:
    """FIX v5: função unificada — elimina luta interna entre normalizar e corrigir."""
    agora = datetime.now()
    for f in _FACCOES:
        if f not in raw:
            raw[f] = {"peso": _FACCOES[f]["peso_base"], "vitorias": 0, "ultima_vitoria": None}
            continue
        peso_atual = raw[f].get("peso", _FACCOES[f]["peso_base"])
        peso_base  = _FACCOES[f]["peso_base"]
        ultima     = raw[f].get("ultima_vitoria")

        if peso_atual > _PESO_MAX * 0.9:
            peso_atual = peso_base

        peso_atual = min(_PESO_MAX, max(_PESO_MIN, peso_atual))

        if peso_atual > peso_base and ultima:
            try:
                dt    = datetime.fromisoformat(ultima)
                horas = (agora - dt).total_seconds() / 3600
                if horas > 24:
                    excesso    = peso_atual - peso_base
                    decaimento = min(excesso, excesso * (horas - 24) * 0.05)
                    peso_atual = max(peso_base, peso_atual - decaimento)
            except Exception:
                peso_atual = peso_base
        raw[f]["peso"] = round(peso_atual, 4)

    # Proteção de ratio unificada
    ratio = _ratio_atual(raw)
    if ratio > _RATIO_MAX:
        warn("PARLAMENTO", f"Ratio {ratio}x > {_RATIO_MAX}x ({contexto}) — resetando para baseline")
        for f in _FACCOES:
            raw[f]["peso"] = _FACCOES[f]["peso_base"]

    return raw


def _carregar():
    if _cache["dados"] is not None:
        return _cache["dados"]
    if not os.path.exists(PARLAMENTO_PATH):
        _cache["dados"] = _estado_inicial()
        return _cache["dados"]
    try:
        with open(PARLAMENTO_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if "debates" in raw and isinstance(raw.get("debates"), list):
            warn("PARLAMENTO", "Formato de memória detectado — iniciando estado limpo")
            _cache["dados"] = _estado_inicial()
            return _cache["dados"]
        raw = _normalizar_e_corrigir(raw, contexto="boot")
        _cache["dados"] = raw
        return _cache["dados"]
    except Exception:
        _cache["dados"] = _estado_inicial()
        return _cache["dados"]


def _salvar(dados):
    """FIX v5: síncrono — sem thread separada, elimina risco de corrupção."""
    for f in _FACCOES:
        if f in dados:
            dados[f]["peso"] = round(
                min(_PESO_MAX, max(_PESO_MIN, dados[f].get("peso", _FACCOES[f]["peso_base"]))), 4
            )
    try:
        with open(PARLAMENTO_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        warn("PARLAMENTO", f"Erro ao salvar: {e}")


def _boost_polyphonic(votos: dict) -> dict:
    try:
        from core.nucleo_vivo.parliament_integration import parliament_integration
        if not parliament_integration.foi_ativado_ultima_vez():
            return votos
        vencedor_poly = parliament_integration.ultimo_vencedor
        if vencedor_poly and vencedor_poly in _MAPA_POLYPHONIC:
            boosts = _MAPA_POLYPHONIC[vencedor_poly]
            for faccao_interna, bonus in boosts.items():
                if faccao_interna in votos:
                    votos[faccao_interna] = min(_PESO_MAX, votos[faccao_interna] + bonus)
            info("PARLAMENTO", f"Fase 33 sync: {vencedor_poly} → boost em {list(boosts.keys())}")
    except Exception:
        pass
    return votos


def _aplicar_boost_minoria(votos: dict, dados: dict) -> dict:
    for faccao in _FACCOES:
        peso_salvo = dados.get(faccao, {}).get("peso", _FACCOES[faccao]["peso_base"])
        if peso_salvo < _LIMIAR_MINORIA:
            votos[faccao] = min(_PESO_MAX, votos.get(faccao, 0) + _BOOST_MINORIA)
    return votos


def votar(msg, contexto=None):
    contexto = contexto or {}
    dados    = _carregar()
    t        = msg.lower()
    votos    = {}
    tem_sinais = False

    for faccao, info_f in _FACCOES.items():
        peso_atual = dados.get(faccao, {}).get("peso", info_f["peso_base"])
        sinais     = sum(1 for s in _SINAIS[faccao] if s in t)
        if sinais > 0:
            tem_sinais = True
        votos[faccao] = round(min(_PESO_MAX, peso_atual + sinais * 0.10), 3)

    # FIX v5: boost por escopo antes do jitter — query com escopo conhecido não é aleatória
    escopo = contexto.get("escopo", "")
    if escopo and escopo in _SINAIS_ESCOPO:
        faccao_escopo = _SINAIS_ESCOPO[escopo]
        votos[faccao_escopo] = min(_PESO_MAX, votos[faccao_escopo] + 0.06)
        tem_sinais = True

    # Jitter mínimo quando sem sinais — FIX v5: 0.005 em vez de 0.03
    if not tem_sinais:
        for faccao in _FACCOES:
            votos[faccao] = round(
                min(_PESO_MAX, votos[faccao] + random.uniform(-_JITTER, _JITTER)), 3
            )

    votos = _aplicar_boost_minoria(votos, dados)
    votos = _boost_polyphonic(votos)

    ppd = contexto.get("ppd", -1)
    if ppd >= 0.7:
        votos["sobrevivencia"] = min(_PESO_MAX, votos.get("sobrevivencia", 0) + 0.3)
        votos["ruptura"]       = min(_PESO_MAX, votos.get("ruptura", 0) + 0.2)

    erros = contexto.get("erros_rec", 0)
    if erros >= 3:
        votos["prudencia"] = min(_PESO_MAX, votos.get("prudencia", 0) + 0.25)

    ciclos = contexto.get("ciclos_sem_evolucao", 0)
    if ciclos >= 20:
        votos["ruptura"] = min(_PESO_MAX, votos.get("ruptura", 0) + 0.3)
        votos["ambicao"] = min(_PESO_MAX, votos.get("ambicao", 0) + 0.2)

    vencedor = max(votos, key=lambda f: votos[f])
    regime   = _FACCOES[vencedor]["regime"]

    # FIX v5: _salvar síncrono dentro do lock — sem thread separada
    with _lock:
        d = _carregar()
        for f in _FACCOES:
            if f not in d:
                d[f] = {"peso": _FACCOES[f]["peso_base"], "vitorias": 0, "ultima_vitoria": None}
        d[vencedor]["vitorias"]       = d[vencedor].get("vitorias", 0) + 1
        d[vencedor]["ultima_vitoria"] = datetime.now().isoformat()
        d[vencedor]["peso"] = min(
            _PESO_MAX,
            d[vencedor].get("peso", _FACCOES[vencedor]["peso_base"]) + _INC_VITORIA
        )
        for f in _FACCOES:
            if f != vencedor:
                d[f]["peso"] = max(
                    _PESO_MIN,
                    d[f].get("peso", _FACCOES[f]["peso_base"]) - _DEC_DERROTA
                )
        # FIX v5: usa função unificada em vez de _corrigir_ratio_sessao separada
        d = _normalizar_e_corrigir(d, contexto="sessao")
        _cache["dados"] = d
        _salvar(d)  # FIX v5: síncrono aqui dentro do lock

    pesos = {f: d[f]["peso"] for f in _FACCOES}
    maior = max(pesos.values())
    menor = min(pesos.values())
    ratio = round(maior / menor, 1) if menor > 0 else 99
    info("PARLAMENTO", f"Vencedor: {vencedor} ({votos[vencedor]:.2f}) → regime={regime} | ratio={ratio}x")

    return regime


def instrucao_regime(regime):
    _INSTRUCOES = {
        "acao":        "\n[PARLAMENTO: IMPULSO] Responda direto e curto. Priorize acao sobre analise.",
        "cautela":     "\n[PARLAMENTO: PRUDENCIA] Mencione riscos antes de sugerir acao.",
        "ruptura":     "\n[PARLAMENTO: RUPTURA] Questione a estrutura atual se ela esta impedindo avanco.",
        "preservacao": "\n[PARLAMENTO: CONTINUIDADE] Mantenha consistencia com o historico estabelecido.",
        "compressao":  "\n[PARLAMENTO: ELEGANCIA] Simplifique. Elimine o que e bonito mas inutil.",
        "protecao":    "\n[PARLAMENTO: SOBREVIVENCIA] Proteja o que esta funcionando. Nao arrisque o nucleo.",
        "expansao":    "\n[PARLAMENTO: AMBICAO] Empurre para o proximo nivel. Nao se contente com manutencao.",
    }
    return _INSTRUCOES.get(regime, "")


def resumo():
    dados = _carregar()
    return {f: {
        "peso":     dados.get(f, {}).get("peso", _FACCOES[f]["peso_base"]),
        "vitorias": dados.get(f, {}).get("vitorias", 0),
    } for f in _FACCOES}