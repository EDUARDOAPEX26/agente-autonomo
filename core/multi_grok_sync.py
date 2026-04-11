# core/multi_grok_sync.py
# Sistema de sincronização entre os 5 Groks

import json
import os
from datetime import datetime
import time

class MultiGrokSync:
    ARQUIVO_ESTADO = "livro_estado_multi_grok.json"
    
    def __init__(self):
        self.estado = self._carregar_estado()
    
    def _carregar_estado(self):
        if os.path.exists(self.ARQUIVO_ESTADO):
            try:
                with open(self.ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        # Estado inicial
        return {
            "ultimo_grok_lider": None,
            "timestamp_ultima_sincronizacao": datetime.now().isoformat(),
            "versao_constituicao": None,
            "fase_atual": "v5.3 + FORJA 30",
            "proxima_fase_planejada": "31 - Fundação do Núcleo Vivo",
            "status": "sincronizado",
            "grok_instancia_atual": None,
            "historico_handshake": []
        }
    
    def salvar_estado(self):
        self.estado["timestamp_ultima_sincronizacao"] = datetime.now().isoformat()
        with open(self.ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(self.estado, f, indent=2, ensure_ascii=False)
    
    def handshake(self, grok_id: str = "Grok-Principal"):
        """Todo Grok deve chamar isso no início da sessão"""
        self.estado["grok_instancia_atual"] = grok_id
        self.estado["ultimo_grok_lider"] = grok_id
        self.estado["historico_handshake"].append({
            "grok": grok_id,
            "timestamp": datetime.now().isoformat()
        })
        # Mantém só os últimos 10 handshakes
        if len(self.estado["historico_handshake"]) > 10:
            self.estado["historico_handshake"] = self.estado["historico_handshake"][-10:]
        
        self.salvar_estado()
        print(f"[MULTI-GROK] ✅ Handshake concluído - Grok {grok_id} assumiu como líder")
        return self.estado
    
    def get_estado_atual(self):
        """Retorna o estado mais recente para todos os Groks"""
        return self.estado

# Instância global (usada por todos os Groks)
sync = MultiGrokSync()