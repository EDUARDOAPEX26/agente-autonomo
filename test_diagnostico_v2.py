import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 60)
print("DIAGNÓSTICO v2 — verificando 5 problemas")
print("=" * 60)

# 1. Sovereign Will instanciado 2x?
print("\n[1] SOVEREIGN WILL — instâncias")
try:
    from core.nucleo_vivo import sovereign_will as sw_mod
    from core.nucleo_vivo.nucleo_vivo_bridge import nucleo_vivo_bridge
    id1 = id(sw_mod.SovereignWill) if hasattr(sw_mod, '_instancia') else "sem singleton"
    print(f"  sovereign_will module: {id(sw_mod)}")
    print(f"  bridge.sovereign_will: {id(nucleo_vivo_bridge.sovereign_will)}")
    print("  ⚠️ Verificar log — se aparecer 2x 'inicializado' = duplicata")
except Exception as e:
    print(f"  ERRO: {e}")

# 2. Tamanho do prompt
print("\n[2] PROMPT — tamanho em tokens (aprox)")
try:
    from core.prompt import get_prompt_sem_dados, get_prompt_com_dados
    p = get_prompt_sem_dados()
    tokens_aprox = len(p) // 4
    print(f"  get_prompt_sem_dados(): {len(p)} chars ≈ {tokens_aprox} tokens")
    if tokens_aprox > 3000:
        print(f"  ❌ ALTO — ideal < 3000 tokens")
    else:
        print(f"  ✅ OK")
except Exception as e:
    print(f"  ERRO: {e}")

# 3. Bridge — injeção condicional ou sempre?
print("\n[3] BRIDGE — injeção de mentores")
try:
    from core.nucleo_vivo.nucleo_vivo_bridge import nucleo_vivo_bridge
    r1 = nucleo_vivo_bridge.process_query("ola como vai")
    r2 = nucleo_vivo_bridge.process_query("quem são seus mentores")
    inj1 = len(r1.get("instrucao_memoria", ""))
    inj2 = len(r2.get("instrucao_memoria", ""))
    print(f"  query normal 'ola':      {inj1} chars injetados")
    print(f"  query 'mentores':        {inj2} chars injetados")
    if inj1 > 500 and inj2 > 500:
        print("  ❌ SEMPRE injeta — oportunidade de economizar tokens")
    elif inj1 < 100 and inj2 > 500:
        print("  ✅ Injeção condicional já funciona")
    else:
        print(f"  ⚠️ Parcial — verificar lógica")
except Exception as e:
    print(f"  ERRO: {e}")

# 4. Crenças — query crua sendo registrada?
print("\n[4] CRENÇAS — verificar entradas recentes")
try:
    with open("livro_crencas.json", "r", encoding="utf-8") as f:
        dados = json.load(f)
    entradas = dados.get("crencas", dados.get("entradas", []))
    print(f"  Total de crenças: {len(entradas)}")
    if entradas:
        ultimas = entradas[-3:] if len(entradas) >= 3 else entradas
        for e in ultimas:
            texto = e.get("crenca", e.get("texto", e.get("pergunta", str(e))))[:80]
            print(f"  → {texto}")
except Exception as ex:
    print(f"  ERRO: {ex}")

# 5. Constituição — rewrite total a cada chamada?
print("\n[5] CONSTITUIÇÃO — artigos e última atualização")
try:
    with open("constituicao_viva.json", "r", encoding="utf-8") as f:
        dados = json.load(f)
    artigos = dados.get("artigos", [])
    print(f"  Total artigos: {len(artigos)}")
    datas = [a.get("atualizado_em", "") for a in artigos if a.get("atualizado_em")]
    if datas:
        from collections import Counter
        mais_comuns = Counter(datas).most_common(2)
        for data, qtd in mais_comuns:
            print(f"  {qtd} artigos com data: {data}")
        if mais_comuns and mais_comuns[0][1] == len(artigos):
            print("  ❌ TODOS com mesma data — rewrite total confirmado")
        else:
            print("  ✅ Datas variadas — atualização incremental OK")
except Exception as ex:
    print(f"  ERRO: {ex}")

print("\n" + "=" * 60)