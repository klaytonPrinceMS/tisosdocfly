# Manual — Perímetro

## Antes de começar

Cadastre cliente, propriedade e voo em `/voos`. A auditoria de perímetro
sempre parte de um voo.

A varredura Wi-Fi/RF é **opcional** e só pode ser feita em rede própria ou com
autorização escrita do responsável pelo ambiente.

## Criar auditoria

1. Abra `/perimetro`.
2. Clique em **Nova auditoria**.
3. Selecione o voo, informe o local e escolha o tipo: **perímetro**,
   **fachada**, **acesso**, **iluminação** ou **RF**.
4. Salve. A auditoria nasce como **Rascunho**.

## Registrar achados

Cada achado recebe uma classe: ponto cego de câmera, vão de cerca, iluminação
deficiente, acesso desprotegido, Wi-Fi exposto, vazamento de sinal, RF
vulnerável ou outro. Informe severidade, confiança, evidência e, quando
possível, latitude/longitude.

Clique em **Revisar** quando a equipe conferir o achado em campo. Sem revisão
humana, o achado continua pendente no resumo.

## Importar varredura RF

1. Na auditoria, clique em **Importar RF**.
2. Cole o conteúdo CSV/JSON ou clique em **Varrer agora** para tentar
   `nmcli`/`iw` no equipamento.
3. Confira o formato e importe.

Campos aceitos: `ssid`, `bssid`, `banda`, `canal`, `rssi`, `seguranca`,
`latitude`, `longitude`. Apelidos em inglês (`mac`, `signal`, `security`,
`channel`) também são aceitos.

O BSSID é convertido para hash SHA-256 antes de entrar no banco. A tela mostra
apenas o SSID, o hash abreviado e a classificação de risco.

### Como ler o risco

- **Aberta/WEP com sinal forte** é o caso mais grave: rede utilizável e sem
  proteção adequada.
- **WPA2/WPA3** aparece como risco baixo: a rede está protegida; o registro
  serve para inventário e comparação.
- **Fora do perímetro** sobe um nível de risco apenas quando o sinal é forte.
  Rede fraca de vizinho não é vazamento do seu perímetro.

A classificação é triagem. Quem decide se há exposição real é a revisão
humana, com a planta e a medição de campo.

## Concluir

O botão **Concluir** muda o status para **Concluído** e grava o resumo do
laudo. O PDF e o mapa do perímetro entram na próxima etapa.

## Boas práticas

- Peça autorização por escrito antes de qualquer varredura de rede.
- Não tente quebrar senha, capturar tráfego ou acessar conteúdo de terceiros.
- Use massa fictícia em teste; nunca dado real de pessoa.
- Trate o hash do BSSID como dado sensível: ele é pseudônimo, não anonimização
  irreversível.
- Registre a evidência do achado (foto, ângulo, coordenada) antes de concluir.
