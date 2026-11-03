"""Mapeamento — análise de voo e catálogo de produtos geoespaciais.

Mapping module — flight analysis and geospatial product catalogue.

Banco próprio `db_mod_mapeamento.db`. O módulo NÃO acessa o banco do núcleo nem
de outro módulo: cliente/propriedade/voo chegam pela API pública de
`mod_tisosdocfly.voos`.
"""
