# core/nucleo_vivo/pain_register.py
# Pain Register - Registro de Dor Estrutural (corrigido)
# Fase 31 - Soberania Autogênica v3

import json
import os
from datetime import datetime

class PainRegister:
    ARQUIVO_DOR = "pain_register.json"
    
    def __init__(self):
        self.registros = self._carregar_registros()
        print(f"[PAIN REGISTER] ✅ Inicializado - {len(self.registros)} registros")
    
    def _carregar_registros(self):
        if os.path.exists(self.ARQUIVO_DOR):
            try:
                with open(self.ARQUIVO_DOR, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def registrar_dor(self, nivel: float, motivo: str, contexto: str = ""):
        nivel = min(1.0, max(0.0, nivel))  # safeguard
        
        registro = {
            "timestamp": datetime.now().isoformat(),
            "nivel": round(nivel, 2),
            "motivo": motivo,
            "contexto": contexto,
            "dor_acumulada_na_hora": self.get_dor_acumulada() + nivel
        }
        
        self.registros.append(registro)
        if len(self.registros) > 50:
            self.registros = self.registros[-50:]
        
        self._salvar_registros()
        print(f"[PAIN REGISTER] ⚠️ Dor registrada | Nível: {nivel:.2f} | {motivo}")
    
    def _salvar_registros(self):
        try:
            with open(self.ARQUIVO_DOR, "w", encoding="utf-8") as f:
                json.dump(self.registros, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[PAIN REGISTER] ❌ Erro ao salvar: {e}")
    
    def get_dor_acumulada(self):
        if not self.registros:
            return 0.0
        return sum(r["nivel"] for r in self.registros[-10:]) / 10
    
    def reset_dor(self):
        """Reset controlado (só usar manualmente)"""
        self.registros = []
        self._salvar_registros()
        print("[PAIN REGISTER] Dor resetada manualmente")
    
    def status(self):
        dor_atual = self.get_dor_acumulada()
        print("\n=== PAIN REGISTER - Dor Estrutural v3.1 ===")
        print(f"Dor Acumulada (últimos 10): {dor_atual:.2f}/1.0")
        print(f"Total de registros: {len(self.registros)}")
        for r in self.registros[-3:]:
            print(f"  • {r['timestamp'][:19]} | {r['nivel']:.2f} | {r['motivo']}")
        print("==============================================\n")


pain_register = PainRegister()

if __name__ == "__main__":
    pain_register.status()
    pain_register.registrar_dor(0.65, "Teste de soberania", "Pedido de desistência")
    pain_register.status()