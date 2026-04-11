from core.classifier import classificar
frases = [
    'como estao seus circuitos?',
    'essa que e a graca da brincadeira',
    'se eu te disser o numero acaba o teste',
    'me diz uma centena',
]
for f in frases:
    r = classificar(f)
    print(r['escopo'].ljust(20), '|', f[:50])
