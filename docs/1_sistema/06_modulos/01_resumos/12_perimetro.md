# Perímetro

Pacote: `src/mod_perimetro/` — chave de banco `perimetro` — rota `/perimetro`.

## Estado

MVP funcional: auditoria de segurança física do perímetro corporativo com
pontos cegos de câmera, vãos de cerca, iluminação deficiente, acessos
desprotegidos e leitura de varredura Wi-Fi/RF. A classificação é **triagem
para revisão humana**; o módulo não quebra cifra, não captura tráfego e não
emite laudo automático de invasão.

## Banco

`db_mod_perimetro.db`:

| Tabela | Conteúdo |
|---|---|
| `tb_perimetro_auditoria` | voo, cliente/propriedade (IDs), local, tipo (`perimetro`, `fachada`, `acesso`, `iluminacao`, `rf`), status, resumo |
| `tb_perimetro_achado` | classe, severidade, confiança, revisão humana, evidência, latitude/longitude |
| `tb_perimetro_rf` | SSID, hash SHA-256 do BSSID, banda, canal, RSSI, segurança, fora do perímetro, risco, evidência |

## Fluxo

1. Cadastre cliente, propriedade e voo em `/voos`.
2. Em `/perimetro`, clique em **Nova auditoria** e selecione o voo.
3. Informe o local e o tipo de auditoria.
4. Registre os achados físicos com classe, severidade, confiança e
   coordenadas.
5. Importe a varredura RF (CSV, JSON ou nmcli/iw) quando houver autorização.
6. Marque a revisão humana e clique em **Concluir**.

## Varredura Wi-Fi/RF

`src/mod_skyrover/rf_scan.py` é Python puro (só stdlib) e lê:

| Entrada | Função |
|---|---|
| CSV/TSV com cabeçalho | `parse_csv` |
| Lista ou objeto JSON | `parse_json` |
| `nmcli -t -f SSID,BSSID,SIGNAL,SECURITY dev wifi list` | `parse_nmcli` |
| `iw dev <interface> scan` | `parse_iw` |

```bash
poetry run python -m mod_skyrover.rf_scan --csv varredura.csv --out saida.json
poetry run python -m mod_skyrover.rf_scan --json varredura.json --out saida.json
```

O JSON de saída contém `gerado_em`, `total`, `resumo` e `registros`
sanitizados. A varredura ao vivo (`escanear_ao_vivo`) é opcional e fail-soft:
usa `nmcli` sem root e `iw` quando disponível; sem ferramenta/permissão,
devolve lista vazia. `SKYROVER_RF_VIVO=0` desliga a varredura.

### Privacidade do BSSID

O BSSID cru **nunca** é gravado nem exportado. `normalizar_registro` troca o
MAC pelo SHA-256 do endereço canônico (`aa:bb:cc:dd:ee:ff`). O hash é
determinístico e permite reconhecer a mesma rede entre auditorias, mas é
**pseudonimização local, não anonimização irreversível**: o espaço de MACs é
pequeno e candidatos podem ser testados. Trate-o como dado sensível.

### Risco

`classificar_risco` aplica regra documentada:

- aberta/WEP com sinal forte (≥ −70 dBm) = `alto`; fraco = `medio`;
- segurança desconhecida com sinal forte = `medio`; fraco = `baixo`;
- WPA2/WPA3 = `baixo` (visibilidade, não quebra de cifra);
- fora do perímetro eleva um nível, somente com sinal forte (vizinho fraco
  não é vazamento).

## Regras

- Cada auditoria referencia um `voo_id` do núcleo via API pública
  (`mod_skyrover.voos`); o módulo não faz cross-query.
- Varredura RF exige autorização escrita do responsável pela rede.
- Achado e rede são triagem; `revisao_humana` registra a conferência.
- Nenhum dado de cliente/propriedade é copiado para o banco do módulo além
  dos IDs de referência.
- Nenhum BSSID cru em banco, tela, log ou JSON de saída.

## Próximas capacidades

- Mapa do perímetro com sobreposição de câmeras e pontos cegos.
- Detecção de vãos de cerca e acessos por imagem (modelo treinado).
- Geração de PDF do laudo e comparativo entre auditorias.
