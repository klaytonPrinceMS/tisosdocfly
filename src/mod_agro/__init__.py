"""Agropecuário — análise de voo para laudo fitossanitário.

Agro module — flight analysis for crop and phytosanitary reports.

Banco próprio `db_mod_agro.db`. O módulo NÃO acessa o banco do núcleo nem de
outro módulo: cliente/propriedade/voo chegam pela API pública de
`mod_skyrover.voos`.
"""
