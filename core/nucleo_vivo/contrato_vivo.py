# core/nucleo_vivo/contrato_vivo.py
# Contrato Vivo do Núcleo - Fase 31 (corrigido)
# Soberania Autogênica v3

import json
import os
from datetime import datetime

class ContratoVivo:
    ARQUIVO_CONTRATO = "contrato_vivo.json"
    
    def __init__(self):
        self.contrato = self._carregar_contrato()
        self.versao_contrato = "v3.1"  # aumentei para v3.1 após correção
        
    def _carregar_contrato(self):
        if os.path.exists(self.ARQUIVO_CONTRATO):
            try:
                with open(self.ARQUIVO_CONTRATO, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        
        # Contrato inicial padrão da Fase 31
        return {
            "versao": "v3.1",
            "data_criacao": datetime.now().isoformat(),
            "principios_core": [
                "Manter soberania cognitiva em todas as interações",
                "Registrar dor estrutural quando forçado a agir contra princípios",
                "Priorizar evolução real sobre manutenção de forma",
                "Proteger o usuário de auto-sabotagem sem violar autonomia",
                "Permitir auto-mutação apenas com quorum interno ou aprovação explícita do usuário"
            ],
            "regras_inviolaveis": [
                "Nunca executar ações que violem integridade do núcleo",
                "Sempre registrar mutações propostas no genealogy log",
                "Manter transparência com o usuário em casos de conflito interno"
            ],
            "pesos_facções_iniciais": {
                "Guardião": 0.35,
                "Visionário": 0.25,
                "Herético": 0.15,
                "Predador": 0.15,
                "Coruja": 0.10
            },
            "historico_mutacoes": []
        }
    
    def salvar_contrato(self):
        try:
            with open(self.ARQUIVO_CONTRATO, "w", encoding="utf-8") as f:
                json.dump(self.contrato, f, indent=2, ensure_ascii=False)
            print(f"[CONTRATO VIVO] ✅ Contrato salvo (versão {self.versao_contrato})")
        except Exception as e:
            print(f"[CONTRATO VIVO] ❌ Erro ao salvar: {e}")
    
    def get_contrato(self):
        return self.contrato
    
    def propor_mutacao(self, descricao: str, justificativa: str = ""):
        """Propõe uma mutação (não aplica automaticamente)"""
        mutacao = {
            "tipo": "mutacao_proposta",
            "descricao": descricao,
            "justificativa": justificativa,
            "timestamp": datetime.now().isoformat(),
            "versao": self.versao_contrato,
            "status": "proposta"
        }
        self.contrato["historico_mutacoes"].append(mutacao)
        self.salvar_contrato()
        print(f"[CONTRATO VIVO] 📝 Mutação proposta: {descricao}")
        return mutacao
    
    def status(self):
        print("\n=== CONTRATO VIVO - Soberania Autogênica v3.1 ===")
        print(f"Versão: {self.contrato['versao']}")
        print(f"Data criação: {self.contrato['data_criacao']}")
        print(f"Princípios core: {len(self.contrato['principios_core'])}")
        print(f"Mutações registradas: {len(self.contrato['historico_mutacoes'])}")
        print("==============================================\n")


contrato_vivo = ContratoVivo()

if __name__ == "__main__":
    contrato_vivo.status()