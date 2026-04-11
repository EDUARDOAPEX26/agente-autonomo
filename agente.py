import time
import random
from datetime import datetime
from config import objetivos, tarefas_possiveis
from tarefas import executar_tarefa, planejar_tarefas, api_atual, status_apis
from sistema import estado_sistema

contador = 0
objetivo = random.choice(objetivos) if objetivos else "Nenhum objetivo"
tarefas = []

print("=" * 50)
print("🤖 Agente iniciado...")
print("🎯 Objetivo inicial:", objetivo)
print("🔌 APIs disponíveis: GROQ | GOOGLE | HUGGINGFACE")
print("=" * 50)

def loop_principal():
    global contador, objetivo, tarefas

    while True:
        try:
            contador += 1
            agora = datetime.now().strftime("%H:%M:%S")
            cpu, memoria = estado_sistema()

            # ─── TROCA DE OBJETIVO A CADA 10 CICLOS ──────────────────
            if contador % 10 == 0:
                novo_objetivo = random.choice(objetivos)
                if novo_objetivo != objetivo:
                    objetivo = novo_objetivo
                    tarefas = []  # reseta tarefas para o novo objetivo
                    print(f"\n🔄 Novo objetivo: {objetivo}\n")

            # ─── PLANEJAMENTO DE TAREFAS ──────────────────────────────
            if not tarefas:
                tarefas = planejar_tarefas(objetivo)
                if not tarefas:
                    tarefas = tarefas_possiveis

            melhor_tarefa = random.choice(tarefas)
            executar_tarefa(melhor_tarefa, objetivo, 0, cpu, memoria)

            # ─── STATUS DAS APIs ──────────────────────────────────────
            apis_status = " | ".join(
                f"{nome.upper()}: {'✅' if s['ativa'] else '❌'}"
                for nome, s in status_apis.items()
            )

            mensagem = (
                f"[{agora}] Ciclo {contador} | "
                f"Obj: {objetivo} | "
                f"CPU: {cpu}% | Mem: {memoria}% | "
                f"Tarefa: {melhor_tarefa} | "
                f"API: {api_atual['nome'].upper()} | "
                f"{apis_status}"
            )

            with open("memoria.txt", "a", encoding="utf-8") as f:
                f.write(mensagem + "\n")

            print(mensagem)
            time.sleep(2)

        except Exception as e:
            print("Erro:", e)
            time.sleep(2)

if __name__ == "__main__":
    loop_principal()