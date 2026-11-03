"""Eventos — análise de voo para laudo de público, fluxo e ocupação.

Events module — flight analysis for crowd, flow and occupancy reports.

Banco próprio `db_mod_eventos.db`. O módulo NÃO acessa o banco do núcleo nem
de outro módulo: cliente/propriedade/voo chegam pela API pública de
`mod_tisosdocfly.voos`.
"""
