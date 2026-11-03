"""Ambiental — análise de voo para laudo de cobertura vegetal e passivo ambiental.

Environmental module — flight analysis for vegetation cover and environmental
liability reports.

Banco próprio `db_mod_ambiental.db`. O módulo NÃO acessa o banco do núcleo nem
de outro módulo: cliente/propriedade/voo chegam pela API pública de
`mod_tisosdocfly.voos`.
"""
