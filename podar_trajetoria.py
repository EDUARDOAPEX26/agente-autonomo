"""
podar_trajetoria.py
Remove entradas duplicadas do livro_trajetoria.json.
Mantém: última entrada de cada direção única por dia + máximo 20 entradas totais.
Roda na raiz do projeto: python podar_trajetoria.py
"""
import json
import os
from datetime import datetime

ARQUIVO = "livro_trajetoria.json"
MAX_ENTRADAS = 20

def podar():
    if not os.path.exists(ARQUIVO):
        print(f"Arquivo {ARQUIVO} não encontrado.")
        return

    with open(ARQUIVO, "r", encoding="utf-8") as f:
        dados = json.load(f)

    total_antes = len(dados)

    if not isinstance(dados, list):
        print("Formato inesperado — esperado lista.")
        return

    # Deduplica: mantém só entradas com combinação única de (direcao + dia)
    vistas = set()
    unicas = []
    for entrada in dados:
        direcao = entrada.get("direcao", "")
        ts = entrada.get("timestamp", "")
        dia = ts[:10] if ts else "sem_data"
        chave = f"{direcao}|{dia}"
        if chave not in vistas:
            vistas.add(chave)
            unicas.append(entrada)

    # Ordena por timestamp desc e mantém as MAX_ENTRADAS mais recentes
    unicas.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    podadas = unicas[:MAX_ENTRADAS]

    # Salva backup antes de sobrescrever
    backup = ARQUIVO.replace(".json", "_backup_pre_poda.json")
    with open(backup, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    with open(ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(podadas, f, ensure_ascii=False, indent=2)

    total_depois = len(podadas)
    tamanho_antes = os.path.getsize(backup)
    tamanho_depois = os.path.getsize(ARQUIVO)
    reducao = round((1 - tamanho_depois / tamanho_antes) * 100, 1)

    print(f"Poda concluída:")
    print(f"  Entradas: {total_antes} → {total_depois}")
    print(f"  Tamanho:  {tamanho_antes:,} → {tamanho_depois:,} chars ({reducao}% menor)")
    print(f"  Backup:   {backup}")

if __name__ == "__main__":
    podar()