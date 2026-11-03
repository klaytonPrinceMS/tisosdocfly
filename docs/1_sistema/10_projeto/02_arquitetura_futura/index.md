# Arquitetura futura — voos, mídia e laudos

Este documento fixa as entidades e as fronteiras que os próximos módulos vão
usar. Nada aqui está implementado ainda; é o contrato para não nascer torto.

## Entidades centrais

| Entidade | Onde deve viver | Observação |
|---|---|---|
| `Cliente` | núcleo (`mod_tisosdocfly`) | quem contrata o laudo |
| `Propriedade` / `Imóvel` | núcleo | endereço, geometria, talhões |
| `Voo` | núcleo | data, piloto, drone, plano, GSD, clima |
| `Captura` | núcleo | conjunto de arquivos de um voo |
| `ArquivoMidia` | núcleo | foto/vídeo, hash, EXIF, geotag, storage key |
| `Laudo` | núcleo + módulo | cabeçalho comum; corpo específico do módulo |
| `Amostra` | módulo | recorte/tile analisado |
| `Inferencia` | módulo | modelo, versão, parâmetros, resultado |
| `Evidencia` | módulo | recorte + coordenada + confiança + revisão humana |

## Fronteiras

```
mod_tisosdocfly
  ├─ contas, sessões, temas, configurações
  ├─ clientes, propriedades, voos, capturas, arquivos
  ├─ storage de mídia (abstrato: local/S3/MinIO)
  └─ laudos: cabeçalho, PDF, versionamento, auditoria

mod_agro            ── lê voo/arquivo, grava análise e laudo agro
mod_vistoria_predial── lê voo/arquivo, grava análise e laudo predial
mod_seguranca       ── lê voo/arquivo, grava análise e laudo de segurança
```

Regra: **módulo não acessa o banco de outro módulo**. O núcleo expõe fachada
(`integracoes.py` ou API interna) para leitura de voo/arquivo e para registro
de laudo. Análise pesada roda em worker, não no request HTTP.

## Armazenamento de mídia

- Banco guarda **metadados**; o binário fica em storage.
- Chave sugerida: `clientes/<id>/voos/<id>/<hash>.<ext>`.
- Hash SHA-256 na ingestão; duplicata não é recoletada.
- Retenção configurável por cliente e por tipo de laudo.
- Acesso a mídia sempre por rota autenticada e auditada — nunca por caminho
  público adivinhável.

## Pipeline de processamento

```
Upload → validação → hash → EXIF/geo → thumbnail
      → fila de processamento → ortômosaico/índices → inferência
      → pós-processo → laudo → revisão humana → entrega
```

Cada etapa tem estado (`pendente`, `processando`, `falhou`, `concluido`) e
retry. O usuário vê o andamento; falha não perde o arquivo original.

## Modelos de IA

- Registro de modelo: nome, versão, arquitetura, dataset, métricas, hash.
- Inferência grava `modelo_versao` e parâmetros — sem isso o laudo não é
  reproduzível.
- Um modelo novo não reescreve laudo antigo.
- Validação mínima: matriz de confusão, precisão/recall por classe e revisão
  por amostragem.
- Conformal/limiar explícito: o laudo mostra confiança e incerteza.

## Geoprocessamento

- Entrada: fotos com EXIF/RTK; GSD alvo; sobreposição.
- Produtos: ortomosaico, DSM, índice espectral, nuvem de pontos (quando
  houver LiDAR).
- Formatos: GeoTIFF, COG, GeoJSON; nunca raster gigante dentro do banco.
- Cálculos de área, distância e contagem sempre com unidade e datum
  declarados.

## Segurança pública — arquitetura e limites

- Detecção de pessoas/veículos/objetos é **triagem**, não veredito.
- Confronto com lista oficial só com convênio e base legal registrados.
- Toda consulta a lista é auditada; resultado exige revisão humana.
- Não armazenar biometria além do necessário; preferir hash/embedding com
  prazo de descarte.
- Laudo de segurança não pode expor dado pessoal além do estritamente
  necessário à autoridade competente.

## Roadmap de implementação

| Fase | Entrega |
|---|---|
| 1 | Núcleo + usuários (atual) |
| 2 | Clientes, propriedades, voos, upload de mídia e laudo base em PDF |
| 3 | Módulo agro: índices, contagem, estande e mapa de falhas |
| 4 | Vistoria predial: patologias e comparativo temporal |
| 5 | Segurança: aglomeração, pessoas, veículos e placas |
| 6 | Ambiental, obras, mapeamento e demais módulos |

Cada fase entrega módulo completo (banco, telas, laudo, testes), não apenas
modelo de IA solto.
