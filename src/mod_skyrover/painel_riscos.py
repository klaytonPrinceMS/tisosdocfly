"""Painel de riscos — agrega resumos dos módulos pela API pública.

Risk dashboard — aggregates module summaries through each module's public
`bd_manipulador.resumo()`. No cross-query: cada módulo lê o próprio banco.

Usado pela rota `/riscos` (monitoramento municipal/corporativo).
"""
from importlib import import_module

MODULOS = (
    ("defesa_civil", "Defesa Civil", "mod_defesa_civil",
     "/defesa-civil", "emergency"),
    ("ambiental", "Ambiental", "mod_ambiental", "/ambiental", "forest"),
    ("obras", "Obras", "mod_obras", "/obras", "construction"),
    ("seguranca", "Segurança Pública", "mod_seguranca", "/seguranca",
     "shield"),
    ("inspecao_industrial", "Inspeção Industrial",
     "mod_inspecao_industrial", "/inspecao-industrial",
     "precision_manufacturing"),
    ("perimetro", "Perímetro e Segurança", "mod_perimetro",
     "/perimetro", "security"),
)


def coletar():
    """Coleta os resumos e devolve totais para o painel."""
    itens = []
    total_analises = 0
    total_ocorrencias = 0
    pendentes = 0
    for chave, nome, pacote, rota, icone in MODULOS:
        try:
            mod = import_module(f"{pacote}.bd_manipulador")
            r = mod.resumo() or {}
        except Exception:
            r = {}
        item = {
            "chave": chave,
            "nome": nome,
            "rota": rota,
            "icone": icone,
            "total": int(r.get("total", 0) or 0),
            "concluido": int(r.get("concluido", 0) or 0),
            "ocorrencias": int(r.get("ocorrencias", 0) or 0),
            "pendentes_revisao": int(r.get("pendentes_revisao", 0) or 0),
        }
        itens.append(item)
        total_analises += item["total"]
        total_ocorrencias += item["ocorrencias"]
        pendentes += item["pendentes_revisao"]
    return {
        "modulos": itens,
        "total_analises": total_analises,
        "total_ocorrencias": total_ocorrencias,
        "pendentes_revisao": pendentes,
    }
