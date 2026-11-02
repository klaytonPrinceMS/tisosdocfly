# Embrapa — drones e IA para monitoramento de gado

Referência aplicada ao Skyrover X1.

## Fonte

- **Título:** Drones e Inteligência Artificial para o monitoramento de gado
- **Autor:** Jayme Garcia Arnal Barbedo
- **Unidade:** Embrapa Agricultura Digital (Campinas/SP)
- **Publicação:** capítulo do livro *Agricultura de Precisão: Um Novo Olhar na
  Era Digital*, 2024, p. 636–644.
- **DOI:** <https://doi.org/10.4322/978-65-86819-38-0.1000057>
- **Acesso aberto:** CC BY-NC-ND (sem fins comerciais, sem alterações, com
  citação).
- **PDF:** <https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1169578/1/AP-Drones-inteligencia-2024.pdf>

## O que o capítulo ensina

### 1. Por que drone no lugar de satélite ou aeronave tripulada

Satélites ainda não têm resolução espacial para identificar animais
individuais e sofrem com nuvens. Aeronave tripulada tem custo, ruído que
perturba o rebanho e risco de acidente. O drone resolve resolução, custo e
ruído, mas impõe planejamento e legislação.

### 2. Plataforma

| Tipo | Vantagens | Limites |
|---|---|---|
| Asa rotativa (cóptero) | paira, decola/pousa vertical, estável, fácil de operar | autonomia curta, carga baixa, área pequena por voo, vento > 25 km/h |
| Asa fixa | mais rápida, cobre área maior, melhor no vento, carga maior | cara, difícil de operar, menos manobrável, mais borrão |
| Híbrido / dirigível | autonomia/carga em nichos | maturidade e operação |

Para pecuária extensiva, a área coberta por voo e a autonomia pesam mais que a
capacidade de pairar. O Skyrover X1 é usado como plataforma de captura; o
planejamento deve registrar **GSD, altitude, sobreposição e vento**.

### 3. Sensores

| Sensor | Uso no gado |
|---|---|
| RGB | detecção/contagem, comportamento, pastagem; barato e alta resolução |
| Multiespectral | assinatura espectral, índices de pastagem, espécies |
| Hiperespectral | atributos sutis (raça, doença); caro e resolução espacial menor |
| Termográfico | animal mais quente que o entorno; funciona à noite; resolução menor |

O pipeline do Skyrover trabalha com RGB por padrão; térmico/multiespectral
entram como bandas adicionais no futuro.

### 4. Legislação (Brasil, ANAC — base 2022)

- Licença de piloto para aeronaves acima de 25 kg.
- Distância horizontal mínima de 30 m de pessoas, salvo autorização.
- Autorização especial acima de 120 m ou fora da linha de visão.
- Voos totalmente autônomos sem intervenção imediata são vedados.
- Manter contato visual e seguir o voo; planejar obstáculos e pouso.
- Regras mudam: consultar a ANAC antes de cada operação.

O capítulo destaca que a **linha de visão** é a restrição que mais limita
levantamentos em propriedades extensas.

### 5. Operação prática

- Planejar pontos-âncora, ordem da rota, altitude **AGL** (acima do solo, não
  do ponto de decolagem) e velocidade compatível com o sensor para evitar
  borrão.
- Evitar sombras: voar próximo ao meio-dia ou em dia nublado; se o
  comportamento animal muda ao longo do dia, escolher a janela que representa
  o problema.
- Levar baterias de reserva; recarga é mais longa que o voo.
- Fazer voos de teste curtos antes da missão real.
- Acompanhar decolagem/pouso visualmente e checar copas/obstáculos.
- Em terreno acidentado, altitude relativa ao ponto de decolagem não garante
  AGL constante.

### 6. IA: arquiteturas e treinamento

- **Detecção:** YOLO, Mask R-CNN — indicam onde o animal está.
- **Segmentação:** DeepLabv3, SegNet, U-Net — delineiam o animal.
- **Classificação:** útil, mas menos informativa que detecção/segmentação.
- **Transfer learning:** usar pesos pré-treinados (ImageNet) acelera e
  costuma superar treino do zero.
- **Balanceamento de classes:** limitar a classe majoritária ou aumentar a
  minoritária.
- **Aumentação:** rotação, inversão, deslocamento, contraste/equalização —
  **somente no treino**, nunca antes de dividir treino/teste.
- **Divisão:** 70/30 ou 80/20, com 10% de validação; parar quando a acurácia
  estabiliza (evitar overfitting).
- **Validação cruzada:** pelo menos 5-fold quando o dataset é pequeno.
- **Conjunto independente:** essencial. O capítulo chama de *covariate shift*
  a queda de acurácia quando o modelo vê imagens de outro sensor, região ou
  estação.
- **Adaptação de domínio:** alternativa para aproximar os dados novos dos
  dados de treino.

### 7. Variabilidade que o dataset precisa cobrir

- Fundo: pasto, solo exposto, árvores, pedras.
- Iluminação: ângulo solar, estação, nuvens, sombra.
- Variação intraclasse: pelagem entre raças e entre animais da mesma raça.
- Configuração de sensor/câmera: o modelo deve ser treinado com as mesmas
  configurações usadas em campo.

### 8. Anotação

Anotar é caro e subjetivo (viés, ilusão de ótica, erro humano). A recomendação
é usar **várias pessoas** na anotação, com critérios e revisão, para reduzir
inconsistência. Uma anotação ruim contamina o modelo e o laudo.

### 9. Uso prático e honestidade

- Acurácia alta no dataset não garante acurácia em campo.
- Resultados confiáveis só são esperados em situações parecidas com o treino.
- Testar com pecuaristas e reter os erros para retreinar é o caminho para
  melhorar generalização.
- Modelos leves importam para tempo real; modelos grandes podem não caber no
  drone/edge.

## O que foi aplicado no Skyrover

### Módulo `mod_agro`

- `tb_agro_analise` ganhou:
  - `tipo_analise` (`lavoura`, `pastagem`, `rebanho`);
  - `cabecas_estimadas` (contagem declarada/revisada);
  - `area_pastagem_ha`.
- Classes de ocorrência de pecuária:
  - `contagem_gado`, `animal_isolado`, `aglomeracao_animal`,
    `animal_caido`, `pastagem_degradada`, `sombra_agua`.
- A tela `/agro` permite criar análise de rebanho/pastagem e registrar
  ocorrências com revisão humana.
- O baseline em Python puro mede pastagem e cor, mas **não conta gado**:
  contagem exige detector treinado e anotação. O resultado do baseline em
  modo rebanho devolve `revisao_humana_obrigatoria=True` e resumo explícito.

### Pipeline de IA

- O registro de modelo aceita `ia.registrar_modelo("agro", "detector-gado-x",
  funcao)`.
- Um detector real deve devolver as classes acima; o núcleo normaliza a saída
  e mantém a revisão humana.
- O laudo PDF registra modelo/versão e ocorrências.

### O que ainda depende de dados/parceria

- Dataset anotado de gado do cliente (raças, pelagens, pastos, horários).
- Treinamento/validação com conjunto independente e 5-fold.
- Teste de campo com pecuaristas e retreino dos erros.
- Definição de limiar de contagem e critério de aceite por cliente.

## Como citar

BARBEDO, J. G. A. **Drones e Inteligência Artificial para o monitoramento de
gado.** In: AGRICULTURA DE PRECISÃO: Um Novo Olhar na Era Digital. 2024.
p. 636–644. DOI: 10.4322/978-65-86819-38-0.1000057.
