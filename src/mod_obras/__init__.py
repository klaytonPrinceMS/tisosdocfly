"""Obras — análise de voo para acompanhamento de avanço e não conformidades.

Construction module — flight analysis for progress tracking and non-conformity
reports.

Banco próprio `db_mod_obras.db`. O módulo NÃO acessa o banco do núcleo nem de
outro módulo: cliente/propriedade/voo chegam pela API pública de
`mod_tisosdocfly.voos`.
"""
