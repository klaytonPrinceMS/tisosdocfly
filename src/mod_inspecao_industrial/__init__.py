"""Inspeção Industrial — análise de voo para laudo de ativos industriais.

Industrial inspection module — flight analysis for industrial asset reports.

Banco próprio `db_mod_inspecao_industrial.db`. O módulo NÃO acessa o banco do
núcleo nem de outro módulo: cliente/propriedade/voo chegam pela API pública de
`mod_tisosdocfly.voos`.
"""
