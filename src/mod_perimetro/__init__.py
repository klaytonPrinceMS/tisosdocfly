"""Perímetro — auditoria de segurança física e de sinal RF do T! SOS DocFly.

Perimeter module — physical-security and RF-signal audit for the T! SOS DocFly.

Banco próprio `db_mod_perimetro.db`. O módulo NÃO acessa o banco do núcleo nem
de outro módulo: cliente/propriedade/voo chegam pela API pública de
`mod_tisosdocfly.voos`.

Cobre pontos cegos de câmera, vãos de cerca, iluminação deficiente, acessos
desprotegidos e vazamento de Wi-Fi/RF. A varredura RF é passiva e exige
autorização do responsável pela rede; o BSSID cru NUNCA é armazenado — apenas
o hash SHA-256 (`mod_tisosdocfly.rf_scan`).
"""
