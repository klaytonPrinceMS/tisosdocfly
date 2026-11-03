# Roadmap de módulos

## Estado atual

- `mod_tisosdocfly` — núcleo com voos, mídia e laudo base.
- `mod_gest_cad_usuario` — usuários.
- `mod_agro` — MVP.
- `mod_vistoria_predial` — MVP.
- `mod_seguranca` — MVP.

## Ondas

### Onda 1 — base de voo e laudo (concluída em MVP)

- [x] Cliente, propriedade e voo no núcleo.
- [x] Upload de fotos/vídeos com hash e storage.
- [ ] EXIF/geotag e fila de processamento.
- [ ] Laudo base em PDF com cabeçalho, metodologia e evidências.

### Onda 2 — agro (MVP concluído)

- [x] Análise por voo, talhão, cultura, índice e área.
- [x] Ocorrências com severidade, confiança e revisão humana.
- [x] Laudo textual.
- [ ] Índices de vegetação e reflectância calculados.
- [ ] Estresse metabólico, ferrugem, oídio, nematoides.
- [ ] Contagem de plantas, estande e mapa de falhas.
- [ ] Matocompetição e topografia de solo.
- [ ] Culturas: soja, milho, tomate, café, banana e frutíferas.
- [ ] PDF.

### Onda 3 — vistoria predial (MVP concluído)

- [x] Vistoria por voo, imóvel e tipo.
- [x] Patologias com severidade, área e revisão humana.
- [x] Laudo textual.
- [ ] Detecção automática de trinca/infiltração/vegetação.
- [ ] Comparativo entre vistorias.
- [ ] Severidade e recomendação no PDF.

### Onda 4 — segurança pública (MVP concluído)

- [x] Triagem por voo, tipo e nível de risco.
- [x] Ocorrências com classe, quantidade, confiança e revisão humana.
- [x] Aviso de limite jurídico e auditoria.
- [ ] Aglomeração e fluxo por IA.
- [ ] Pessoas, veículos, placas e objetos de risco.
- [ ] Consulta a bases oficiais (quando houver convênio).
- [ ] Relatório com evidência e trilha de revisão.

### Onda 5 — módulos complementares (MVP concluído)

- [x] Ambiental: análise, ocorrências e laudo textual.
- [x] Obras: análise, ocorrências e avanço.
- [x] Mapeamento: análise e produtos geoespaciais.
- [x] Defesa Civil: análise, ocorrências e laudo textual.
- [x] Inspeção Industrial: análise, ocorrências e laudo textual.
- [x] Eventos: análise, ocorrências e público.
- [ ] IA/geoprocessamento/PDF específicos de cada módulo.

### Onda 6 — pipeline transversal

- [x] Análise de imagem por baseline RGB (índices, bordas, proporções).
- [x] GSD, métricas e thumbnails.
- [x] Laudo PDF.
- [ ] Modelos treinados/homologados (ONNX/Torch).
- [ ] Ortomosaico/GDAL, EXIF/geotag e fila de processamento.
- [ ] Integração com bases oficiais de segurança.

## Regra de entrada de um módulo

Um módulo só entra no produto quando tem:

1. Banco próprio e migração idempotente.
2. `bd_manipulador.py`, `telas.py` e `telas_administracao.py`.
3. Permissão por papel e auditoria.
4. Laudo ou saída concreta.
5. Testes standalone e caso E2E.
6. Documentação em `docs/1_sistema/06_modulos/` e manual em `docs/2_manuais/`.

Sem os seis, é protótipo — e protótipo não vai para produção.
