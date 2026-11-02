# Conformidade ANAC, DECEA e SISANT

Checklist prático para operar o Skyrover X1 dentro das regras brasileiras:
cadastro, espaço aéreo, seguro, piloto, privacidade e evidências. O texto é
orientação de produto e operação, **não é parecer jurídico**. As regras mudam:
valide a norma vigente e o parecer do voo antes de cada operação. Em 2026, o
RBAC 100 substituiu o RBAC-E 94; a referência antiga ainda aparece em contratos
e checklists e não deve ser usada como se estivesse atual.

## Aviso de escopo

- Este documento resume o que a equipe precisa checar, não substitui a leitura
  da norma nem a análise jurídica do caso concreto.
- A responsabilidade pela operação é do operador e do piloto remoto.
- Regras de ANAC, DECEA, ANATEL, LGPD e legislação local se acumulam; cumprir
  uma não dispensa as outras.
- “Parecer favorável” no SARPAS não autoriza violar regra de privacidade,
  invadir propriedade ou operar sem seguro.
- Links oficiais estão no fim da página. Confirme sempre a versão publicada.

## Quadro de normas e sistemas

| Tema | Norma ou sistema | O que exige na prática |
|---|---|---|
| Operação de drone | **RBAC 100** (Regulamento Brasileiro da Aviação Civil, Resolução ANAC nº 805/2026) | categorias Aberta, Específica e Certificada; requisitos de piloto, seguro, manutenção e operação |
| Cadastro da aeronave | **SISANT** (Sistema de Aeronaves Não Tripuladas — ANAC) | cadastro do drone e certidão vinculada ao responsável legal |
| Espaço aéreo | **ICA 100-40/2026** (Instrução do Comando da Aeronáutica — DECEA) | solicitação prévia de acesso ao espaço aéreo |
| Autorização de voo | **SARPAS NG** (Sistema para Solicitação de Acesso ao Espaço Aéreo Brasileiro por Aeronaves Não Tripuladas — DECEA) | parecer de voo, NOTAM e coordenação quando aplicável |
| Telecomunicações | **ANATEL** | equipamentos de radiofrequência homologados e uso regular do espectro |
| Privacidade | **LGPD** (Lei nº 13.709/2018) e orientações da ANPD | base legal, finalidade, minimização, retenção, segurança e direitos do titular |
| Responsabilidade técnica | conselho profissional | ART ou documento equivalente quando o laudo exigir |

> **Atenção:** o RBAC 100 é a referência vigente para operações civis de UA.
> O RBAC-E 94 foi substituído. Se um contrato, seguro ou checklist citar apenas
> o RBAC-E 94, atualize a referência antes de assinar.

## Checklist ANAC / RBAC 100

### Enquadramento da operação

| Item | Regra prática | Evidência a guardar |
|---|---|---|
| Categoria | defina **Aberta**, **Específica** ou **Certificada** antes do voo | justificativa do enquadramento |
| Categoria Aberta | peso em voo ≤ 25 kg, VLOS (linha de visão) ou EVLOS (linha de visão estendida), até 120 m AGL, área distante de terceiros | plano de voo e análise de área |
| Distância de terceiros | no mínimo **30 m horizontais** de pessoas não envolvidas e não anuentes; barreira mecânica forte pode dispensar | mapa da área e registro de barreiras |
| Avaliação de risco | obrigatória na Aberta, atualizada nos últimos 12 meses; dispensável se > 150 m de terceiros ou barreira mecânica suficiente | documento assinado e datado |
| Categoria Específica | quando não cabe na Aberta: BVLOS, acima de 120 m, acima de 25 kg, proximidade sem barreira, entre outros | cenário padrão ou autorização operacional |
| Categoria Certificada | artigos perigosos de alto risco ou determinação da ANAC | certificação e documentos aplicáveis |

**120 m é altura acima do solo (AGL), não altitude.** O SARPAS pede altura e
altitude; as duas informações precisam estar coerentes. O limite de 30 m é
**piso regulatório**, não uma promessa de segurança: a avaliação de risco pode
exigir distância maior.

### Cadastro no SISANT

| Item | Regra prática | Evidência a guardar |
|---|---|---|
| Obrigatoriedade | drones de **250 g a 150 kg** devem ser cadastrados, inclusive para uso recreativo | certidão de cadastro |
| Faixa inferior | até 249 g o cadastro é opcional, mas recomendado; o SARPAS continua exigindo solicitação na maioria dos casos | decisão documentada |
| Responsável legal | pessoa física ou jurídica com CPF/CNPJ no Brasil | vínculo no SISANT |
| Validade | certidão válida por **24 meses**; revalidar antes do vencimento | certidão vigente |
| Identificação | número de cadastro visível na aeronave, em local legível | foto da aeronave |
| Acima de 25 kg | projeto avaliado pela ANAC antes do cadastro, salvo exceções de pulverização agrícola | aprovação do projeto |
| Consistência | dados de fabricante, modelo, série e peso devem bater com o SARPAS | conferência SISANT × SARPAS |

O SISANT **não é registro de propriedade** e **não é homologação**. Ele vincula
a aeronave ao responsável legal pela operação. A certidão não substitui o
parecer do DECEA.

### Piloto e tripulação

| Item | Regra prática | Evidência a guardar |
|---|---|---|
| Exame teórico | piloto remoto deve ser aprovado no exame de conhecimento teórico da ANAC | comprovante de aprovação |
| Menor de 18 anos | só opera acompanhado, em todos os momentos, por piloto maior de 18 responsável | termo de acompanhamento |
| Categoria Específica | exige licença/habilitação conforme o cenário ou autorização; pode haver dispensa conforme o risco | licença, habilitação ou dispensa |
| Capacidade psicofísica | piloto e observador devem estar aptos e descansados | declaração do checklist |
| Observador | em EVLOS, o observador mantém contato visual direto e auxilia a separação | designação no plano de voo |
| Uma UA por piloto | o piloto opera uma aeronave por vez, salvo autorização da ANAC | registro de operação |

O calendário de transição do exame teórico deve ser conferido na ANAC. Não
trate “ainda não exigido na fiscalização” como autorização para operar sem
preparo.

### Seguro e responsabilidade

| Item | Regra prática | Evidência a guardar |
|---|---|---|
| Seguro | **RBAC 100, seção 100.37**: todas as operações sob o regulamento devem ter seguro com cobertura de danos a terceiros | apólice vigente e comprovante de pagamento |
| Exceções | entes controlados pelo Estado e aplicação agrícola em área desabitada, nos termos da norma | enquadramento documentado |
| Responsabilidade | operador responde pelo controle operacional; piloto tem autoridade final sobre o voo | contrato e plano de voo |
| Terceiros | pessoas não envolvidas e não anuentes não podem ser expostas a risco inaceitável | mapa e barreiras |

Não confunda seguro do drone com seguro de responsabilidade civil profissional
do laudo. São coberturas diferentes; verifique o que a apólice cobre.

### Operação e aeronavegabilidade

| Item | Regra prática | Evidência a guardar |
|---|---|---|
| Condição segura | só voar aeronave em condições seguras e conforme o projeto, quando aplicável | checklist pré-voo |
| Intervenção | o piloto deve poder intervir em qualquer fase do voo | configuração de failsafe e teste |
| Pré-voo | conhecer todas as informações de planejamento, obstáculos e meteorologia | briefing assinado |
| Autonomia | só iniciar com autonomia suficiente para voar e pousar com segurança | cálculo de bateria e reserva |
| Artigos perigosos | proibido transportar pessoas, animais ou artigos perigosos; artigos perigosos só nas exceções da norma | declaração de carga |
| Aeródromo | operação em aeródromo exige autorização do administrador | autorização anexa |
| Registro de voos | obrigatório na Específica/Certificada; recomendado em todas | log de voo |
| Manutenção | seguir o fabricante e manter registros; aeronave de tipo certificado tem regras próprias | caderno de manutenção |

### Autorizações especiais

| Situação | Caminho provável |
|---|---|
| acima de 120 m AGL | Categoria Específica; SARPAS com antecedência maior e possível NOTAM |
| BVLOS | Categoria Específica; BVLOS (além da linha de visão), espaço aéreo segregado, produto AIS e prazo maior |
| acima de 25 kg | Categoria Específica ou Certificada, conforme o caso; projeto e autorização |
| proximidade de pessoas sem barreira | sair da Aberta ou obter anuência expressa e avaliação de risco |
| área próxima de aeródromo ou heliponto | coordenação com o administrador e possível Termo de Coordenação |
| área sensível | autorização do órgão responsável, além das regras de voo |

## Checklist DECEA / SARPAS

### Regra geral

A **ICA 100-40/2026** exige solicitação prévia de acesso ao espaço aéreo por
meio do **SARPAS** para aeronaves não tripuladas, **inclusive as de até 250 g**.
As exceções previstas são operação em área confinada e operação recreativa em
espaço aéreo condicionado destinado a aeromodelos. Na dúvida, solicite.

### Passo a passo

1. Acesse o SARPAS NG com conta **gov.br** (pessoa física nível prata ou
   superior; pessoa jurídica com administrador designado).
2. Sincronize a aeronave cadastrada no **SISANT**. CPF/CNPJ da conta do SARPAS
   deve ser o mesmo do cadastro da aeronave.
3. Informe local, coordenadas do ponto de decolagem, altura, altitude, perfil
   da operação, data e janela de voo.
4. Anexe Termo de Coordenação quando houver interseção com **FRZ** ou **EAC**.
5. Receba o parecer **favorável** ou **desfavorável**. Guarde o protocolo.
6. Consulte **NOTAM** e cartas no **AISWEB** antes de decolar.
7. Leve o parecer e o checklist para o campo. O parecer não dispensa leitura
   de NOTAM nem julgamento do piloto.

### Prazos de antecedência

| Prazo | Quando se aplica |
|---|---|
| **30 minutos** | Categoria Aberta; operação em zona UTM ou área adequada; operação aérea especial; Específica/Certificada até 25 kg, VLOS, até 120 m, sem interseção com EAC ou FRZ |
| **4 dias corridos** | aerolevantamento; área de voo superior a 100 km²; operação até 25 kg, VLOS, até 120 m, com interseção com EAC ou FRZ |
| **8 dias corridos** | BVLOS; acima de 120 m; acima de 25 kg; operação atípica ou que exija produto AIS/NOTAM |

Regras adicionais: a solicitação não pode ser feita com mais de 90 dias de
antecedência nem ter duração superior a 90 dias. Autorização com NOTAM pode
ser estendida por 60 dias, mediante pedido com 8 dias de antecedência.

### Áreas e coordenação

| Situação | O que fazer |
|---|---|
| **FRZ** (zona de restrição de voo) | Termo de Coordenação com o permissionário ou administrador; análise manual do DECEA |
| **EAC** (espaço aéreo condicionado) | consultar o detentor no AIP-Brasil/AISWEB; TCo quando aplicável |
| **Área proibida** | não é autorizável; não insista |
| **Aeródromo ou heliponto** | contato do administrador no AISWEB; autorização e coordenação |
| **BVLOS** | espaço aéreo segregado, produto AIS e prazo de 8 dias |
| **Segurança pública/defesa civil** | condições especiais somente para órgãos acreditados pelo DECEA, com acordo operacional |

O SARPAS **não substitui** o SISANT. Os dois sistemas precisam estar
consistentes: número de cadastro, responsável, fabricante, modelo, série e
peso máximo de decolagem.

## LGPD e privacidade

### O que é dado pessoal em voo

- Imagem de pessoa identificável, mesmo em plano aberto, é dado pessoal.
- Placa de veículo, fachada de residência e número de unidade podem permitir
  identificação indireta; trate com o mesmo cuidado.
- Áudio, quando capturado, também é dado pessoal e raramente é necessário.
- Localização de pessoas em área privada pode revelar hábitos e rotina.

### Princípios operacionais

| Princípio | Aplicação no Skyrover |
|---|---|
| Finalidade | capturar para o laudo contratado, não para marketing ou uso genérico |
| Base legal | contrato, legítimo interesse, consentimento, exercício regular de direitos ou política pública, conforme o caso; documentar |
| Minimização | voar só a área necessária; evitar pessoas; recortar ou mascarar o que não é objeto |
| Retenção | definir prazo; apagar originais depois do laudo quando não houver dever de guarda |
| Segurança | acesso por papel, sessão revogável, criptografia em trânsito, log de acesso |
| Transparência | informar o cliente sobre o que é capturado e por quê |
| Direitos do titular | canal para acesso, correção, eliminação e informação |
| Compartilhamento | só com base legal; não vender e não repassar a terceiros sem contrato |
| Incidente | comunicar a ANPD e o titular quando houver risco relevante, nos termos da LGPD |

### Regras práticas

- Não faça reconhecimento facial, biometria ou identificação de pessoas sem
  base legal específica e revisão humana.
- Em segurança pública, o produto entrega **triagem e evidência**, nunca
  decisão automática de culpa; exige base legal, convênio, retenção limitada e
  auditoria.
- Evite overflight de multidão, escola, hospital e área residencial quando o
  objeto é outro.
- Se a imagem de pessoa for inevitável, aplique mascaramento antes de
  compartilhar o laudo com terceiros.
- Guarde o termo de retenção e o registro de exclusão.
- Para cliente público, verifique a política de tratamento e o encarregado de
  dados do órgão.

## Operação: rotina e evidências

### Antes do voo

| Item | Verificação |
|---|---|
| Documentação | SISANT vigente, SARPAS com parecer favorável, seguro, autorização do local |
| Piloto | exame teórico, habilitação quando exigida, descanso e aptidão |
| Espaço aéreo | NOTAM, AISWEB, FRZ/EAC, proximidade de aeródromo/heliponto |
| Meteorologia | vento, chuva, visibilidade, trovoada, temperatura e umidade |
| Aeronave | bateria, hélices, motores, firmware, calibração, câmera e gimbal |
| Site | pessoas, veículos, linhas de energia, animais, obstáculos e rota de fuga |
| Área de pouso | local seguro, sinalizado e fora do alcance de terceiros |
| Privacidade | necessidade da captura, pessoas na área, base legal e retenção |
| Comunicação | equipe de campo, cliente e contato de emergência |
| Checklist | assinado pelo piloto e pelo observador, quando houver |

### Durante o voo

- Mantenha **VLOS** ou **EVLOS** conforme o plano; BVLOS só com autorização e
  segregação.
- Respeite altura, distância de terceiros e limites da área autorizada.
- Não sobrevoe pessoas não envolvidas; se a trajetória mudou, reavalie.
- Interrompa imediatamente se aparecer aeronave tripulada, helicóptero,
  emergência ou pessoa na área de pouso.
- Não persiga pessoas, veículos ou animais; não capture áudio sem necessidade.
- Registre horário, bateria, ocorrências e qualquer desvio do plano.

### Depois do voo

| Item | Ação |
|---|---|
| Log | data, hora, piloto, drone, série, local, altura, duração, bateria e incidentes |
| Mídia | download, conferência, hash SHA-256 e backup |
| Ocorrências | registrar intercorrências operacionais e de privacidade |
| Bateria | armazenar conforme o fabricante; não guardar descarregada nem cheia por longos períodos |
| Manutenção | registrar inspeção, troca de hélice e firmware |
| Laudo | versão, método, modelo, limitações e revisão humana |
| Retenção | aplicar prazo e registrar exclusão quando aplicável |

### Manutenção

| Item | Frequência sugerida |
|---|---|
| Hélices e fixações | antes de cada voo e troca por trinca ou deformação |
| Motores e rolamentos | conforme fabricante, com escuta e folga |
| Bateria | ciclos, células, inchaço e resistência interna |
| Firmware e apps | antes de campanha, com registro da versão |
| Calibração | conforme fabricante e após incidente |
| Limpeza de sensor | antes de cada campanha, com material adequado |
| Registro | caderno ou sistema, com data, responsável e peça |

### Áreas sensíveis

Considere restrição adicional ou autorização específica para: aeródromo,
heliponto, FRZ, EAC, área militar, unidade prisional, hospital, escola,
unidade de conservação, terra indígena, área de segurança pública, faixa de
duto, subestação e infraestrutura crítica. Nessas áreas, o parecer do SARPAS
não substitui a autorização do órgão ou proprietário.

## Varredura Wi-Fi e segurança física e lógica

Esta seção vale para o serviço de [auditoria de perímetro](../10_projeto/05_servicos_hibridos/index.md).
A regra é simples: **com autorização escrita, passivo por padrão, sem capturar
conteúdo e sem explorar falha**.

### O que é permitido com autorização

- Varredura passiva de redes visíveis: SSID quando broadcast, BSSID, canal,
  intensidade de sinal e tipo de criptografia.
- Medição de alcance do sinal dentro e fora do perímetro autorizado.
- Inventário de pontos de acesso e comparação com a lista fornecida pelo
  cliente.
- Identificação de rede aberta ou criptografia fraca, sem conectar e sem
  testar credencial.
- Registro de data, hora, operador, equipamento e local da medição.
- Relatório com achado, evidência, risco e recomendação.

### O que é proibido

- Interceptar, gravar ou ler conteúdo de comunicação de terceiros.
- Capturar handshake, quebrar senha, usar força bruta ou dicionário.
- Enviar *deauth*, *jamming*, pacotes de injeção ou qualquer transmissão não
  autorizada.
- Conectar a rede, alterar configuração, criar usuário ou exfiltrar dado.
- Varrer rede fora do escopo, mesmo que o sinal alcance.
- Guardar MAC de cliente, payload ou URL acessada.
- Usar ferramenta de exploração sem contrato e sem profissional habilitado.

### Controles técnicos

| Controle | Implementação |
|---|---|
| Escopo | lista de SSIDs/BSSID e geofence autorizados; horário definido |
| Passividade | adaptador em modo monitor/passivo, sem injeção |
| Pseudonimização | BSSID com SHA-256; o MAC cru nunca é gravado; hash determinístico não é anonimização irreversível |
| Produto | `mod_perimetro` grava SSID, BSSID em hash, banda, canal, RSSI, segurança, fora do perímetro e risco; não grava payload |
| Minimização | guardar só metadados necessários ao laudo |
| Cadeia de custódia | hash do relatório, assinatura do escopo e log do operador |
| Separação | evidência em cofre com acesso restrito |
| Relatório | achados e recomendações, sem passo a passo de exploração |
| Retenção | prazo curto para dados brutos; laudo fica pelo prazo contratual |

O hash do BSSID é **pseudonimização**, não anonimização irreversível: o espaço
de endereços MAC é pequeno e candidatos podem ser testados. Trate o hash como
dado sensível e restrinja o acesso ao inventário.

### Base legal e riscos

Varredura sem autorização pode configurar ilícito civil e penal, além de
violação de sigilo e de proteção de dados. Interceptação de comunicação e
acesso não autorizado a sistema têm tratamento próprio na legislação. O
contrato deve definir escopo, finalidade, prazo, responsável e devolução ou
exclusão dos dados. Na dúvida, consulte o jurídico antes de ligar o adaptador.

Transmissão de radiofrequência também é regulada pela ANATEL. Varredura
passiva não transmite; qualquer teste ativo ou equipamento emissor exige
conformidade e autorização específica. *Jammer* não faz parte do serviço.

## Matriz de riscos de conformidade

| Risco | Consequência possível | Controle |
|---|---|---|
| Voar sem SARPAS | infração de tráfego aéreo, processo na JJAER, multa e interrupção | checklist + parecer arquivado |
| Drone sem SISANT | operação irregular e dificuldade de responsabilização | cadastro e certidão vigentes |
| Sem seguro | responsabilidade civil direta do operador | apólice e cobertura de terceiros |
| Expor pessoas | dano, ação civil e violação de LGPD | distância, barreira, minimização e base legal |
| Varredura sem autorização | ilícito civil/penal e perda de evidência | escopo assinado e modo passivo |
| Laudo sem responsável técnico | questionamento técnico e jurídico | ART ou parecer habilitado |
| Modelo sem validação | laudo frágil e reprodutibilidade baixa | versão, cartão de modelo e revisão humana |
| Dado fora do Brasil | transferência internacional irregular | servidor local e contrato |
| Área sensível sem autorização | interdição, apreensão e sanção | consulta prévia ao órgão |
| Retenção indefinida | passivo de privacidade | prazo, exclusão e registro |

## Dossiê do voo

Monte um dossiê por operação. Ele é a defesa do laudo e do piloto.

| Documento | Quando | Observação |
|---|---|---|
| Certidão SISANT | sempre | conferir validade de 24 meses |
| Apólice de seguro | sempre | cobertura de danos a terceiros |
| Parecer SARPAS | sempre | protocolo e janela autorizada |
| NOTAM/AISWEB | sempre | impressão ou PDF com data |
| Autorização do proprietário | área privada | escopo, acesso e rede |
| Termo de Coordenação | FRZ/EAC/aeródromo | quando aplicável |
| Checklist pré-voo | sempre | assinado pelo piloto |
| Log de voo | sempre | data, local, altura, duração, bateria |
| Hash das mídias | sempre | SHA-256 e backup |
| Laudo PDF | sempre | versão, método e limitações |
| Termo de retenção | quando há dado pessoal | prazo e responsável |
| Relatório de incidente | se houver | causa, ação e comunicação |

## Resumo em uma página

- [ ] Categoria da operação definida e documentada.
- [ ] SISANT vigente e número visível na aeronave.
- [ ] SARPAS com parecer favorável e NOTAM consultado.
- [ ] Seguro de danos a terceiros vigente.
- [ ] Piloto com exame teórico e habilitação aplicável.
- [ ] Distância de 30 m de terceiros e avaliação de risco.
- [ ] Altura de 120 m AGL respeitada.
- [ ] Autorização do proprietário e do órgão local.
- [ ] LGPD: finalidade, base legal, minimização e retenção.
- [ ] Wi-Fi: escopo assinado, modo passivo, BSSID em hash.
- [ ] Dossiê do voo completo e laudo com revisão humana.

## Links oficiais

| Órgão | Link |
|---|---|
| ANAC — Drones | <https://www.gov.br/anac/pt-br/assuntos/regulados/aviacao-geral/drones> |
| ANAC — RBAC 100 | <https://www.anac.gov.br/assuntos/legislacao/legislacao-1/boletim-de-pessoal/2026/bps-v-21-no-24-15-a-19-06-2026/rbac-100-emd-00/visualizar_ato_normativo> |
| ANAC — Categorias de operações | <https://www.gov.br/anac/pt-br/assuntos/regulados/aviacao-geral/drones/categoria-de-operacoes> |
| ANAC — SISANT | <https://www.gov.br/anac/pt-br/sistemas/sisant> |
| ANAC — Orientações SISANT | <https://www.gov.br/anac/pt-br/assuntos/regulados/aviacao-geral/drones/orientacoes-aos-usuarios-do-sisant> |
| ANAC — Regras de todos os órgãos | <https://www.gov.br/anac/pt-br/assuntos/regulados/aviacao-geral/drones/regras-de-todos-os-orgaos-brasileiros-sobre-operacao-de-drones> |
| DECEA — Portal Drone | <https://www.decea.mil.br/drone/> |
| DECEA — SARPAS | <https://servicos.decea.mil.br/sarpas/> |
| DECEA — ICA 100-40 | <https://publicacoes.decea.mil.br/publicacao/ICA-100-40> |
| DECEA — AISWEB | <https://aisweb.decea.mil.br/> |
| gov.br — Autorização de voo | <https://www.gov.br/pt-br/servicos/solicitar-autorizacao-para-voo-de-aeronaves-remotamente-pilotadas> |
| ANPD | <https://www.gov.br/anpd/pt-br> |
| LGPD — Lei nº 13.709/2018 | <https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm> |
| ANATEL | <https://www.gov.br/anatel/pt-br> |

> Links verificados na elaboração desta página. Regras e URLs mudam; confirme
> a versão vigente antes de cada operação.

## Referências internas

- [Catálogo de serviços híbridos](../10_projeto/05_servicos_hibridos/index.md)
- [Visão de produto — Skyrover X1](../10_projeto/01_visao_produto/index.md)
- [Contas de fábrica](01_contas_de_fabrica.md)
- [IA, índices e geoprocessamento](../01_ferramentas/ia_geoprocessamento.md)
