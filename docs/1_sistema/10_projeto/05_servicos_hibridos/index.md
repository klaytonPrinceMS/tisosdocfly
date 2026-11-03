# Catálogo de serviços híbridos

O T! SOS DocFly combina drones próprios e de terceiros (**multidrone**), processamento próprio em **Python** e leitura
técnica para transformar voo em laudo utilizável. Este catálogo descreve três
serviços híbridos: auditoria de perímetro, inspeção de infraestrutura e
monitoramento de riscos. Cada oferta traz problema, entregáveis, módulos,
entradas e saídas, diferenciais, limites e o que depende de autorização ou
parceria. Preço e prazo são definidos em proposta; esta página não fixa valores.

## O que é um serviço híbrido

Serviço híbrido é a combinação de três camadas que precisam funcionar juntas:

| Camada | O que entra | O que sai |
|---|---|---|
| Campo | piloto, drone (qualquer modelo), plano de voo, autorizações | fotos, vídeos, metadados, pontos de interesse |
| Software | pipeline Python, bancos por módulo, telas NiceGUI | análise, ocorrências, mapas, histórico |
| Laudo | revisão humana e redação técnica | PDF com método, evidência, severidade e limites |

O diferencial não é “voar mais alto”. É entregar **evidência organizada**:
quem voou, quando, com qual equipamento, em qual altitude, com qual GSD, qual
método analisou e qual foi o resultado. Sem essa cadeia, a imagem é bonita e
não serve para decisão.

## Visão geral das ofertas

| Serviço | Dor principal | Módulos do produto | Entregável âncora |
|---|---|---|---|
| Auditoria de perímetro e segurança física/lógica | pontos cegos, cerca vulnerável, iluminação ruim, Wi-Fi exposto além do muro | `mod_perimetro`, `mod_tisosdocfly`, `mod_mapeamento` | laudo de perímetro + mapa + inventário RF com BSSID em hash |
| Inspeção de infraestrutura | acesso difícil a telhado, torre e painel solar; laudo lento e caro | `mod_vistoria_predial`, `mod_inspecao_industrial`, `mod_mapeamento` | laudo PDF com evidências, severidade e GSD |
| Monitoramento e gestão de riscos | dados dispersos, sem comparação temporal nem visão gerencial | `mod_defesa_civil`, `mod_obras`, `mod_ambiental`, `mod_mapeamento` | painel gerencial + relatórios por ciclo |

---

## 1. Auditoria de perímetro e segurança física/lógica integrada

### Problema do cliente

Indústrias, condomínios logísticos, subestações e grandes áreas muradas
costumam descobrir o problema tarde: a cerca tem vão, o portão secundário fica
sem câmera, a iluminação não cobre o fundo do terreno e o Wi-Fi corporativo
alcança o estacionamento e a rua. A auditoria tradicional olha o físico e o
lógico em relatórios separados, com fornecedores diferentes e sem correlação
entre os achados.

### O que o T! SOS DocFly entrega

| Frente | Entrega | Como é medido |
|---|---|---|
| Perímetro físico | mapa de setores com pontos cegos, vãos de cerca, portões, acessos, vegetação e falhas de iluminação | sobrevoo sistemático com sobreposição, registro fotográfico e marcação de pontos |
| Cobertura declarada de CFTV | cruzamento entre a posição e o campo de visão informados pelo cliente e o que o voo revela | quando o cliente fornece planta e posição das câmeras; não é auditoria certificada de CFTV |
| Perímetro lógico | inventário de redes Wi-Fi visíveis, intensidade de sinal, canais, criptografia e vazamento além do limite | varredura passiva em solo, com escopo autorizado e BSSID tratado por hash |
| Correlação | matriz de prioridade entre achado físico e lógico | probabilidade × impacto acordados no briefing |
| Relatório | PDF executivo e técnico, com evidência, severidade, recomendação e responsável sugerido | revisão humana e versão do método registrada |

O laudo separa **achado**, **evidência** e **recomendação**. “Cerca com vão de
aproximadamente 1,2 m no setor 4” é achado; a foto georreferenciada é evidência;
“priorizar reparo e instalar barreira vegetal” é recomendação. O relatório não
transforma hipótese em certeza.

### Como funciona

```text
Briefing e escopo
  └─ autorização escrita do proprietário
       └─ checagem regulatória (SISANT, SARPAS, seguro, LGPD)
            └─ plano de voo por setores, altitude e sobreposição
                 └─ captura com drone
                      └─ upload com hash e metadados
                           └─ análise de imagem + marcação GeoJSON
                                └─ varredura Wi-Fi passiva em solo
                                     └─ correlação dos achados no mod_perimetro
                                          └─ revisão humana
                                               └─ laudo PDF + anexos
```

A varredura Wi-Fi é feita **em solo**, com adaptador em modo passivo, dentro
do perímetro autorizado. O objetivo é medir exposição e alcance, não invadir
rede. O detalhamento legal e operacional está em
[Conformidade ANAC, DECEA e SISANT](../../11_seguranca/02_conformidade_anac_decea_sisant.md#varredura-wi-fi-e-seguranca-fisica-e-logica).

### Módulos usados

| Módulo | Papel no serviço |
|---|---|
| `mod_perimetro` | auditoria de perímetro, achados físicos e registros RF sanitizados; banco próprio `db_mod_perimetro.db` |
| `mod_tisosdocfly` | cadastro do voo, upload, hash, metadados, laudo PDF e trilha de auditoria |
| `mod_mapeamento` | organização espacial, GSD, GeoJSON e produtos geoespaciais quando a captura permitir |
| `mod_inspecao_industrial` | complemento para ativos do perímetro: subestação, torre, casa de máquinas, estruturas |
| `mod_seguranca` | **não** é usado em perímetro privado; ele é o módulo de segurança pública, com limites jurídicos próprios |

O `mod_perimetro` trabalha com três registros: **auditoria** (voo, local, tipo,
status), **achado** (classe, severidade, confiança, revisão humana, latitude e
longitude) e **RF** (SSID, BSSID em hash, banda, canal, RSSI, segurança, fora
do perímetro e risco). As classes de achado já cobrem `ponto_cego_camera`,
`vao_cerca`, `iluminacao_deficiente`, `acesso_desprotegido`, `wifi_exposto`,
`vazamento_sinal` e `rf_vulneravel`. O módulo organiza a evidência; ele não
executa exploração ofensiva.

O módulo registra a auditoria e os achados; o botão **Gerar laudo PDF** usa a
camada de laudo do núcleo e inclui os achados físicos e as redes RF (BSSID em
hash) na tabela de ocorrências. A leitura RF usa `mod_tisosdocfly/rf_scan.py`, que aceita CSV, JSON,
`nmcli` e `iw` e normaliza o BSSID antes de gravar.

### Entradas e saídas

| Entradas | Saídas |
|---|---|
| endereço, limites e planta do perímetro | PDF executivo e técnico |
| posição e campo de visão das câmeras (opcional) | mapa de setores e pontos de interesse (GeoJSON quando houver georreferência) |
| autorização escrita do proprietário | inventário de redes com BSSID em hash |
| lista de SSIDs e áreas autorizadas | CSV de achados com severidade e recomendação |
| janela de voo e restrições de acesso | fotos e vídeos organizados por setor |
| dados do piloto, drone e seguro | registro de método, versão e limitações |

### Diferenciais

- **Uma cadeia de evidência**, não dois relatórios desconectados: o achado
  físico e o lógico saem do mesmo briefing e do mesmo voo.
- **Operação própria de drone**, sem depender de locação de terceiros para cada
  campanha; o perímetro é dividido em setores compatíveis com a autonomia e a
  troca de bateria.
- **Processamento em Python**, sem licença por assento de software de GIS ou
  de segurança: o método, o limiar e a versão ficam registrados.
- **Privacidade por padrão**: BSSID em hash, sem captura de conteúdo, sem
  payload, sem tráfego de terceiros.
- **Laudo em minutos**: o Perímetro e a Inspeção Industrial geram PDF direto
  pela tela, com achados/ocorrências e evidências. O prazo total inclui voo,
  revisão humana e assinatura.

### Limites

- Não é auditoria de segurança certificada nem garantia contra invasão.
- A varredura Wi-Fi é amostral e passiva; não substitui monitoramento
  contínuo, IDS/IPS ou pentest ofensivo.
- Intensidade de sinal não é localização precisa: reflexão, obstáculos e
  multipath alteram a leitura. O relatório fala em alcance aproximado.
- O voo não vê dentro de galpões, subsolos ou áreas cobertas.
- Cobertura de câmeras só é analisada se o cliente fornecer posição e campo de
  visão; a análise é declaratória, não uma medição óptica certificada.
- Chuva, vento forte, baixa luminosidade e restrições de espaço aéreo podem
  reduzir a janela ou exigir novo voo.
- Não há monitoramento 24×7 nesta oferta; acompanhamento contínuo é outro
  escopo.

### O que depende de parceria ou autorização

| Dependência | Por quê |
|---|---|
| autorização escrita do proprietário | acesso à área e à rede; define escopo, horário e o que pode ser medido |
| SISANT, SARPAS e seguro | operação regular do voo; ver [conformidade](../../11_seguranca/02_conformidade_anac_decea_sisant.md) |
| coordenação com aeródromo, heliponto ou FRZ | áreas próximas exigem Termo de Coordenação e análise do DECEA |
| autorização de autoridade local | área pública, via, evento ou entorno de órgão sensível |
| parceiro de RF e equipamento homologado | qualquer teste ativo de transmissão; o padrão do T! SOS DocFly é passivo |
| profissional de segurança habilitado | interpretação de risco físico e plano de mitigação, quando o cliente exigir |

---

## 2. Inspeção de infraestrutura com relatórios automatizados em Python

### Problema do cliente

Telhados, torres e usinas solares têm três problemas recorrentes: acesso
difícil e perigoso, inspeção visual incompleta e laudo que demora semanas.
O cliente recebe fotos soltas, sem GSD, sem data confiável e sem critério de
severidade. Quando o relatório chega, o problema já evoluiu.

### O que o T! SOS DocFly entrega

| Entregável | Conteúdo |
|---|---|
| Laudo PDF | capa, metodologia, dados do voo, GSD, evidências, tabela de ocorrências, severidade, recomendação e limitações |
| Prontuário do ativo | histórico de inspeções, comparativo entre voos e linha do tempo |
| Anexos técnicos | fotos recortadas, miniaturas, CSV/JSON de ocorrências e GeoJSON quando houver georreferência |
| Parecer de triagem | classes aparentes com confiança e revisão humana obrigatória |
| Trilha de auditoria | hash dos arquivos, modelo/versão e parâmetros usados |

O laudo não promete “diagnóstico automático de trinca”. Ele entrega **triagem
com evidência**: onde olhar, com qual severidade aparente e qual a próxima
verificação em campo. A conclusão estrutural é de responsável técnico
habilitado.

### Como funciona

```text
Briefing do ativo e objetivo
  └─ autorização de acesso e checagem regulatória
       └─ plano de voo (altitude, GSD, sobreposição, ângulos)
            └─ captura com drone
                 └─ upload com hash, EXIF e vínculo ao voo
                      └─ decode e métricas de imagem
                           └─ baseline Python ou modelo homologado
                                └─ revisão humana
                                     └─ laudo PDF + anexos
```

O pipeline padrão é a **avaliação pura em Python**: decode de PNG/BMP/PPM pela
stdlib, JPEG/WebP com Pillow apenas como decoder, métricas de cor, contraste,
borda, entropia e blobs. Quando existe modelo homologado registrado, ele
assume a análise e o laudo registra o nome e a versão. Sem modelo, o resultado
é explicitamente `avaliacao-pura-v1` — nunca uma rede neural simulada. O
detalhamento está em [IA, índices e geoprocessamento](../../01_ferramentas/ia_geoprocessamento.md).

O PDF é montado em **ReportLab** (`mod_tisosdocfly/relatorio.py`), com metadados,
tabela de ocorrências, métricas e imagens. PyMuPDF não é dependência
obrigatória; quando o cliente exige conferência ou composição externa, ele
pode ser usado como leitor/verificador, sem alterar a fonte do laudo.

### Módulos usados

| Módulo | Papel no serviço |
|---|---|
| `mod_vistoria_predial` | fachadas, telhados, calhas, reservatórios e patologias aparentes |
| `mod_inspecao_industrial` | torres, estruturas, linhas, equipamentos e ativos industriais |
| `mod_mapeamento` | GSD, área, camadas e produtos geoespaciais |
| `mod_tisosdocfly` | voo, mídia, hash, laudo e auditoria |

Para usina solar, o módulo de inspeção industrial organiza os painéis por
setor e o mapeamento dá a referência espacial. Detecção de *hot spot* exige
câmera térmica e entra como serviço complementar, não como padrão da captura.

### Entradas e saídas

| Entradas | Saídas |
|---|---|
| identificação do ativo e endereço | laudo PDF com metodologia e evidências |
| fotos e vídeos do voo | tabela de ocorrências com classe, severidade e confiança |
| data, piloto, drone, altitude e GSD | recortes de evidência e miniaturas |
| laudo anterior (opcional) | comparativo temporal quando houver base |
| acesso e autorização do proprietário | CSV/JSON e GeoJSON de ocorrências |
| restrições operacionais do site | registro de modelo, versão e limitações |

### Diferenciais

- **Laudo em minutos após o upload** para o lote típico, sem esperar fila de
  software comercial.
- **Processamento próprio em Python**: sem licença por assento, sem caixa-preta
  e com possibilidade de rodar on-premise.
- **Reprodutibilidade**: o laudo guarda método, versão, limiar e hash da mídia.
- **O drone reduz andaime e trabalho em altura**, com captura em ângulos que a
  inspeção no chão não alcança.
- **Comparativo entre voos**: o mesmo ativo, a mesma metodologia e a evolução
  documentada.
- **Integração com o fluxo do cliente**: CSV/JSON e GeoJSON para o sistema que
  ele já usa.

### Limites

- Não substitui laudo estrutural, ART ou parecer de engenheiro habilitado.
- A avaliação pura é triagem por pixel; borda alta pode ser telhado, cerca,
  sombra ou vegetação, não necessariamente trinca.
- Sem GSD e calibração, não há medida confiável de largura de fissura.
- Modelo treinado só entra com dataset, validação e cartão de modelo; não há
  promessa de classe sem modelo homologado.
- Térmico, multiespectral e fotogrametria completa dependem de sensor e de
  etapa externa (ODM/Metashape ou camada seguinte).
- Reflexo em painel solar, sombra e sujeira podem gerar falso positivo.
- O laudo sempre pede revisão humana; a decisão de intervir é do cliente e do
  responsável técnico.

### O que depende de parceria ou autorização

| Dependência | Por quê |
|---|---|
| autorização de acesso ao ativo | telhado, torre, subestação e área industrial têm regras próprias |
| responsável técnico habilitado | assinatura, ART e conclusão estrutural |
| SISANT, SARPAS e seguro | operação regular do voo |
| coordenação com o site | parada de linha, bloqueio de área, acompanhamento de segurança |
| sensor adicional | térmico, multiespectral ou RTK, quando o objetivo exigir |
| software de fotogrametria | ortomosaico e modelo 3D, quando contratados |

---

## 3. Monitoramento e gestão de riscos municipais e corporativos

### Problema do cliente

Municípios e empresas acumulam dados de áreas de risco, obras e passivos
ambientais em planilhas, pastas de fotos e relatórios isolados. Falta uma visão
única: o que mudou desde o último ciclo, qual obra está fora do cronograma,
qual área exige vistoria e qual evidência sustenta a decisão. Sem comparação
temporal, cada gestão recomeça do zero.

### O que o T! SOS DocFly entrega

| Entregável | Conteúdo |
|---|---|
| Linha de base | mapa de áreas de risco, obras e pontos ambientais priorizados |
| Ciclo de monitoramento | voos periódicos com o mesmo plano, GSD e metodologia |
| Painel gerencial | telas NiceGUI com mapa, filtros, status, indicadores e histórico |
| Relatório de ciclo | PDF executivo e técnico com evidências, ocorrências e comparativo |
| Fluxo de ocorrência | responsável, prazo, evidência e status de tratativa |
| Trilha de auditoria | acesso, versão do laudo, hash da mídia e histórico de alteração |

O painel não é um *dashboard* decorativo. Ele responde a perguntas de gestão:
qual área piorou, qual obra avançou, qual ocorrência está vencida e qual
evidência foi usada. Cada módulo mantém o próprio banco; o painel consolida a
leitura sem cross-query entre bancos. No MVP, o painel é a soma das telas dos
módulos contratados; um dashboard único com mapa consolidado é a camada
seguinte.

### Como funciona

```text
Definição do território e dos indicadores
  └─ linha de base (voos, camadas e dados do cliente)
       └─ painel configurado por módulo
            └─ ciclo de voo e atualização
                 └─ análise e ocorrências
                      └─ revisão humana
                           └─ relatório de ciclo
                                └─ comparativo e priorização
```

### Módulos usados

| Módulo | Papel no serviço |
|---|---|
| `mod_defesa_civil` | áreas de risco, dano pós-desastre e risco geológico |
| `mod_obras` | avanço físico, medição, ocorrências e cronograma |
| `mod_ambiental` | desmatamento, APP, queimada e recuperação |
| `mod_mapeamento` | base geoespacial, GSD, GeoJSON e produtos |
| `mod_eventos` | público, fluxo e ocupação, quando o território tiver eventos |
| `mod_tisosdocfly` | voo, mídia, laudo e auditoria |

### Entradas e saídas

| Entradas | Saídas |
|---|---|
| limites do território e prioridades | painel gerencial com mapa e indicadores |
| camadas GeoJSON/Shapefile e dados históricos | relatório PDF por ciclo |
| cronograma de voos e janelas de acesso | ocorrências com responsável e prazo |
| dados públicos e do cliente | comparativo entre ciclos |
| validação de campo | CSV/JSON e GeoJSON para integração |
| autorizações e contatos locais | trilha de auditoria e versão do laudo |

### Diferenciais

- **Visão única** de risco, obra e ambiente, com bancos independentes por
  módulo e consolidação no painel.
- **Comparação temporal**: o mesmo enquadramento e a mesma metodologia
  mostram o que mudou, não apenas o retrato do dia.
- **Python de ponta a ponta**, sem licença de plataforma proprietária e com
  possibilidade de implantação on-premise.
- **Drone para resposta rápida**: após um evento, o voo entra na fila e o laudo
  sai em minutos após o upload.
- **Evidência para decisão pública**: ocorrência, foto, data, responsável e
  histórico, com revisão humana.
- **Escopo modular**: o cliente contrata só o que precisa e liga o restante
  quando fizer sentido.

### Limites

- Não é sistema de alerta em tempo real nem substitui central de defesa civil.
- Não faz modelo hidrológico, geotécnico ou climático; mede o que a imagem
  mostra e o que o dado do cliente informa.
- A qualidade do painel depende da qualidade das camadas e da validação de
  campo.
- A análise de imagem padrão é triagem; classes sensíveis exigem modelo
  homologado e revisão humana.
- Não há decisão automática de culpa, interdição ou responsabilidade.
- Monitoramento contínuo exige contrato de ciclos; um voo isolado é retrato,
  não série histórica.

### O que depende de parceria ou autorização

| Dependência | Por quê |
|---|---|
| órgão municipal ou defesa civil | prioridade, acesso e validação de campo |
| autorização de acesso | área privada, obra, unidade de conservação ou área militar |
| dados públicos e do cliente | linha de base e indicadores |
| responsável técnico | parecer, ART e conclusão |
| SISANT, SARPAS e seguro | operação regular do voo |
| acordo de tratamento de dados | LGPD, retenção e compartilhamento |

---

## Vantagens técnicas comuns

| Vantagem | O que significa na prática |
|---|---|
| Autonomia operacional do drone | operação própria, planejamento por setores e resposta rápida; o tempo de voo é confirmado no briefing e depende de vento, carga e bateria |
| Processamento próprio em Python | sem licença por assento, sem software comercial engessado; método, limiar e versão auditáveis |
| Laudo em minutos | após o upload, o pipeline do núcleo monta o PDF; Perímetro e Inspeção Industrial têm botão de laudo na própria tela. O prazo total inclui voo, revisão e assinatura |
| Evidência rastreável | hash da mídia, metadados do voo, versão do modelo e trilha de acesso |
| Privacidade por padrão | minimização, retenção definida, BSSID em hash e nenhuma captura de conteúdo |
| Conformidade regulatória | SISANT, SARPAS, seguro e LGPD checados antes do voo; dossiê anexo ao laudo |
| Operação on-premise | a stack Python pode rodar no ambiente do cliente, sem dependência de nuvem de terceiros |
| Modularidade | cada módulo tem banco próprio; o cliente liga apenas o que contratou |

## O que não está incluído

- Preço fechado, desconto, SLA ou prazo comercial nesta página.
- Monitoramento 24×7, central de alarmes ou resposta a incidentes.
- Pentest ofensivo, exploração de falhas, quebra de senha ou interceptação.
- Parecer jurídico, laudo estrutural, ART ou responsabilidade técnica.
- Treinamento de modelo sem dataset, validação e cartão de modelo.
- Aquisição de dados de terceiros, bases oficiais ou imagens de satélite.
- Garantia de detecção de todas as patologias ou de todos os pontos cegos.

## Como um serviço vira proposta

| Etapa | O que acontece | Saída |
|---|---|---|
| 1. Briefing | objetivo, área, ativo, restrições e expectativa | escopo preliminar |
| 2. Viabilidade | checagem de espaço aéreo, acesso, clima e dados disponíveis | go/no-go técnico |
| 3. Conformidade | SISANT, SARPAS, seguro, LGPD e autorizações | dossiê do voo |
| 4. Campo | plano de voo, captura e varredura autorizada | mídia com hash e metadados |
| 5. Processamento | análise, ocorrências e revisão humana | laudo e anexos |
| 6. Entrega | apresentação, dúvidas e plano de ação | relatório final |
| 7. Ciclo | novo voo com a mesma metodologia | comparativo |

## Referências internas

- [Visão de produto — T! SOS DocFly](../01_visao_produto/index.md)
- [Roadmap de módulos](../03_roadmap/index.md)
- [IA, índices e geoprocessamento](../../01_ferramentas/ia_geoprocessamento.md)
- [Processamento multiespectral](../../01_ferramentas/processamento_multiespectral.md)
- [Conformidade ANAC, DECEA e SISANT](../../11_seguranca/02_conformidade_anac_decea_sisant.md)
- [Mapeamento](../../06_modulos/01_resumos/08_mapeamento.md)
- [Inspeção industrial](../../06_modulos/01_resumos/10_inspecao_industrial.md)
- [Vistoria predial](../../06_modulos/01_resumos/04_vistoria_predial.md)
- [Defesa civil](../../06_modulos/01_resumos/09_defesa_civil.md)
- [Obras](../../06_modulos/01_resumos/07_obras.md)
- [Ambiental](../../06_modulos/01_resumos/06_ambiental.md)
