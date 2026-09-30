# Manual de uso (Fabulim Studio)

O Fabulim Studio é um estúdio **local** de vídeos infantis originais (2 a 5 anos): tudo roda no seu computador. Este manual explica cada página do app, do personagem ao vídeo pronto, e quanto tempo cada coisa leva **neste** computador (os tempos citados foram medidos num ThinkPad T14 Gen 2i, sem placa de vídeo dedicada; no seu eles podem variar).

## 1. Abrir e fechar

| Quero | Faça |
|---|---|
| Abrir o app | dois cliques em `iniciar.bat` (na pasta do projeto). Ele sobe o servidor numa janela minimizada, chamada **"Fabulim Studio: servidor"**, e abre o navegador em `http://127.0.0.1:8765` |
| Fechar o app | feche a janela **"Fabulim Studio: servidor"** |
| Ver a interface depois de eu mudar o código | `iniciar.bat --compilar` |
| Abrir sem abrir o navegador | `iniciar.bat --sem-navegador` |

O app só responde **nesta máquina** (endereço 127.0.0.1): nenhum outro computador da rede consegue abri-lo. Nada é enviado para fora, e não há telemetria.

## 2. O menu

No computador o menu fica à esquerda, numerado de 01 a 09; em tela média ele vira uma barra estreita só com os números; no celular, uma gaveta (botão de menu no canto superior). A **barra do topo** tem o indicador do **Claude**, o atalho com a **letra do perfil** da máquina (leva a "Sua máquina"), o botão de **tema** (claro/escuro) e o de **idioma** (PT/EN).

| Item | Para que serve |
|---|---|
| **01 Criar vídeo** | cole o enredo, escolha os personagens e crie o projeto. Abaixo, o caminho do enredo ao vídeo em sete etapas e como o seu computador se sai nas tarefas principais |
| **02 Personagens** | a biblioteca dos seus personagens: ficha, variações, PNG transparente de cada pose, voz e a versão em outro estilo (seção 4) |
| **03 Gerar imagem** | cenários, objetos e miniaturas no estilo dos seus personagens (seção 5) |
| **04 Clipes** | a biblioteca dos clipes: clipe rápido, unir, mudar de formato, continuar e enviar um vídeo seu (seção 6) |
| **05 Projetos** | cada vídeo é um projeto, com as sete etapas, aprovações e versões (seção 7) |
| **06 Fila** | onde roda tudo o que demora, e a **fila noturna** (seção 8) |
| **07 Modelos** | os programas e modelos de IA que o estúdio usa; **é aqui que você instala** (seção 11) |
| **08 Status** | serviços, "Sua máquina" e logs (seção 10) |
| **09 Configurações** | tema, idioma, pastas e conta do Claude |

## 3. Do personagem ao vídeo, em resumo

1. **Personagens**: crie a Lila (descrevendo, colando um prompt ou enviando uma imagem sua), gere variações e escolha a principal. O fundo é recortado sozinho (PNG transparente); gere as poses e ajuste a voz.
2. **Criar vídeo**: cole o enredo (ou escreva), escolha o formato (Short vertical ou vídeo longo), os personagens e crie o projeto.
3. **Projeto**, uma etapa de cada vez, **aprovando** cada uma: enredo → roteiro → storyboard → animação → áudio → montagem → revisão.
4. **Revisão e exportação**: baixe o MP4 e as legendas, escolha a miniatura, copie título, descrição e tags, e, se quiser, leve o projeto para outra máquina (pacote `.fabulim`) ou crie a versão em outro idioma ou formato.

Nada avança sozinho: cada etapa só libera a próxima quando **você** aprova. Voltar uma etapa não apaga o que já foi gerado.

## 4. Personagens

- **Criar**: três jeitos. (a) **Descrever ou colar um prompt** (seção 12): o formulário é preenchido para você revisar. (b) Escrever a ficha à mão. (c) **Importar imagem do computador** (botão no alto da página, ou *Enviar uma imagem* na seção *Criar personagem*): abre o seletor de arquivos do Windows (Explorer) para escolher um PNG, JPG ou WebP de até 15 MB; o nome do arquivo vira o nome do personagem, você marca que tem o direito de usar e clica em *Enviar e criar*; o app recorta o fundo e usa a imagem como principal.
- **Variações e imagem principal**: escolha quantas (1 a 4) e a qualidade (**Rascunho** é o mais rápido). O app mostra o tempo estimado para o seu computador. Cada variação aparece assim que fica pronta; **Escolher esta** define a principal e recorta o fundo automaticamente.
- **Folha de referência**: cada pose (frente, três quartos, lado) e expressão (feliz, triste, surpreso, com sono, bravinho) vira um **PNG transparente**. Os vídeos usam **esses recortes**, é por isso que o personagem fica igual em todas as cenas. Cada recorte tem o campo **Olha para** (frente, esquerda ou direita): o app vira o personagem para o lado certo em cada cena.
- **Voz**: escolha a voz (Kokoro, gerada no seu computador), a velocidade e o tom, e **ouça** uma frase antes de salvar.
- **Ficha e prompt técnico**: editar a ficha refaz o prompt técnico (o texto em inglês que vai para o modelo); no bloco avançado dá para editar o prompt técnico à mão.
- **Versão em outro estilo**: 2D e 3D são personagens separados (todas as imagens seguem um estilo só); **Criar a versão 3D/2D** parte da imagem principal como referência.
- **Levar para outra máquina**: **Baixar a biblioteca (.fabulim)** e **Importar personagens** (seção 9).

Tempos medidos: uma variação de 512 px leva ~90 s; o recorte do fundo ~25 s; cada pose da folha ~3 min (usa a imagem principal como referência).

## 5. Gerar imagem

Descreva (ou cole um prompt de imagem), escolha o **tipo** (cenário, objeto, miniatura ou livre), o **estilo** (2D ou 3D), o **formato** (16:9, 9:16 ou 1:1) e, se quiser, até 3 **personagens da biblioteca** (a aparência deles é mantida). **Gerar parecida** usa uma imagem sua como base. Escolha 1 a 4 variações, a qualidade e, se quiser, a semente (mesma semente + mesmo texto = mesma imagem). O **prompt técnico** aparece no bloco avançado, para você ver ou editar. As variações aparecem lado a lado; toque numa imagem para ver em tela grande, copiar o prompt ou baixar. Tudo fica guardado em **Suas imagens**, com busca.

## 6. Clipes

- **Clipe rápido**: um personagem e uma frase de ação ("pulando de alegria num jardim florido") viram um clipe de 3 a 10 s. O cenário é gerado por IA e o personagem é **animado por código** (não há vídeo por IA neste computador).
- **Biblioteca**: filtre por tipo (rápido, enviado, unido, outro formato, vídeo final).
- **Unir**: marque **Para unir**, arraste (ou use ↑ ↓) para a ordem, escolha a transição (corte, fade ou suave) e o tamanho do resultado. Formatos e volumes diferentes são acertados.
- **Outro formato**: cria uma cópia em 9:16, 16:9, 1:1 ou 720p, mostrando o vídeo inteiro (fundo desfocado) ou preenchendo a tela.
- **Continuar**: cria um projeto que começa igual ao último quadro do clipe. Como não há modelo que enxergue a imagem, diga o que aparece no final.
- **Enviar um vídeo seu** (MP4, MOV ou WebM, até 1 GB): o arquivo é conferido **de verdade** (tipo, duração, tamanho) antes de entrar.

## 7. Criar vídeo e Projetos: as sete etapas

**Criar vídeo** tem o formulário do enredo (título, formato, duração, idioma, estilo, personagens, tema, cenários, história, música). Só aparecem os personagens que já têm o PNG transparente. Depois de **Criar o projeto**, ele abre na etapa 1. Em **Projetos** ficam todos os vídeos, com a etapa em que estão.

| Etapa | O que acontece | Como aprovar |
|---|---|---|
| **1 Enredo e personagens** | revise a história e quem aparece; mudar a história volta as etapas seguintes para "não aprovada" (o gerado fica guardado) | **Aprovar a etapa** |
| **2 Roteiro** | o modelo local escreve as cenas (3 a 8 s, com narração e falas simples, sugestões marcadas), ou **Roteiro simples (sem IA)** divide a história. Edite cada cena: título, o que se vê, ação, câmera, emoção, narração, falas, letra, efeitos. Cada edição vira uma **versão** e dá para voltar | aprove as cenas uma a uma ou **Aprovar N cenas restantes e a etapa** |
| **3 Storyboard** | cada cena ganha um **cenário gerado por IA** com os personagens (PNG) por cima; escolha entre opções, ajuste a posição, o tamanho, a pose e o movimento de cada um | idem |
| **4 Animação** | os personagens ganham vida **por código** (respiram, pulam, andam, entram em cena, mexem a boca no ritmo da voz, câmera suave). **Rascunho rápido** confere o movimento em resolução menor | idem |
| **5 Áudio** | vozes (narrador e personagens), **música instrumental** original, efeitos sonoros, mistura com a voz sempre à frente; sai junto o arquivo de **legendas (SRT)** | **Aprovar a etapa** |
| **6 Montagem** | junta os clipes e o áudio no MP4 final (H.264 e AAC, volume em -14 LUFS, sem flashes) | **Aprovar a etapa** |
| **7 Revisão e exportação** | checklist de qualidade (conteúdo para 2 a 5 anos, ritmo das cenas, flashes, volume, duração, legendas, originalidade); baixar o **MP4** e o **SRT**; **miniaturas** 1280×720; **título, descrição e tags** em português e inglês; **outras versões**; **pacote .fabulim** | **Aprovar a etapa** |

**Renderizar o aprovado** (no alto do projeto) enfileira o próximo trabalho pesado que as suas aprovações já liberaram.

- **Miniaturas**: até 6 variações, com os personagens do vídeo sobre os cenários do storyboard, desenhadas em segundos, **sem o logo do estúdio**. Dá para pôr um texto curto.
- **Título, descrição e tags**: "Sugerir com o modelo local" ou "Usar o modelo pronto (sem IA)"; editável, com os limites do YouTube, botões de copiar e **Salvar os textos**.
- **Versão em outro idioma**: cria um projeto novo com o mesmo visual e o roteiro, as falas, as letras e o título traduzidos (pelo modelo local) ou copiados (você traduz). Você revisa antes de seguir; a animação e o áudio são refeitos com as vozes do idioma.
- **Versão Short/Vídeo longo**: reaproveita o roteiro e os personagens no outro formato; os cenários são gerados de novo com a mesma semente para manter o estilo.

Tempos medidos (roteiro de 3 cenas, ~33 s de vídeo, Short 1080×1920): roteiro pelo modelo local ~2,5 min; cenários em rascunho ~93 s por cena; animação ~2 min (com as vozes); áudio ~6 s; montagem ~10 s; miniaturas ~3 s; textos do YouTube ~1 min; versão em inglês ~1,5 min.

## 8. Fila e Fila noturna

A fila é onde tudo o que demora roda (diagnóstico, benchmark, instalações, imagens, roteiros, animação...). **Um job roda por vez**, para não travar o computador.

- **Executando agora**: barra de progresso, porcentagem e tempo restante, ao vivo.
- **Na fila**: mude a ordem **arrastando** ou pelos botões ↑ ↓ (os botões funcionam pelo teclado). A ordem é guardada, inclusive se você fechar o app.
- **Pausar / Retomar / Cancelar** em cada job. A pausa e o cancelamento acontecem no próximo ponto seguro do job, não no meio de uma gravação.
- **Concluídos**: histórico, com o botão **Limpar concluídos**.
- **Se o app fechar no meio de um job**, ele volta para a fila e é refeito ao abrir de novo (o bloco mostra "tentativa 2").
- O botão **Job de demonstração** cria uma tarefa de teste, útil para ver a fila funcionando sem gastar recurso do computador.
- A etiqueta **Ao vivo** indica que o progresso está chegando em tempo real; **Reconectando** aparece se a ligação com o servidor cair (ela volta sozinha).

**Fila noturna**: renderiza enquanto você dorme o que você **já aprovou**. Ela lista, para cada projeto, o **próximo trabalho liberado** pelas suas aprovações (cenários, animação, áudio ou montagem) e enfileira **um por projeto** (o que já está na fila não se repete). Ela **nunca aprova nada por conta própria**: de manhã você revisa e aprova.

## 9. Pacotes .fabulim (levar para outra máquina)

Escreva e aprove no notebook e renderize no desktop, ou faça uma cópia de segurança.

- **Projeto**: em *Revisão e exportação* → **Baixar o pacote .fabulim** (opcionalmente incluindo os vídeos e o áudio já gerados). Guarda enredo, roteiro, cenas com todas as versões, aprovações, personagens e cenários, **sem os modelos**.
- **Personagens**: em *Personagens* → **Baixar a biblioteca (.fabulim)**.
- **Importar**: em *Projetos* → **Importar um projeto** (ou *Personagens* → **Importar personagens**). O pacote é **conferido por inteiro** antes de entrar (estrutura, tamanhos, tipo real de cada arquivo, caminhos e hashes) e **nada que já existe é sobrescrito**: o que tiver o mesmo nome ganha "(importado)". Sem os vídeos no pacote, as etapas de animação, áudio e montagem voltam a "não aprovada" e são refeitas na máquina que importou; o app avisa o que a máquina nova não consegue fazer.

## 10. Status

São três abas.

### Serviços
Um bloco por serviço, em três grupos: **Precisam de atenção** (algo pede uma ação sua), **Funcionando** e **Ainda não ativos** (programas e modelos que ainda não foram instalados ou conectados; nada ali atrapalha o resto). Cada serviço mostra o estado **em texto e forma** (não só cor) e, quando há o que fazer, um **Como corrigir** que abre o passo a passo (funciona com mouse, toque e teclado).

| Estado | Significa |
|---|---|
| **Funcionando** | tudo certo |
| **Atenção** | funciona, mas há algo a resolver (ex.: pouco espaço livre em disco, ou o ffmpeg ainda não instalado) |
| **Com problema** | não funciona; o bloco diz o que fazer |
| **Inativo** | ainda não é usado (por exemplo, um modelo que você não instalou) |

"Ver logs" abre a aba de logs já filtrada por aquele serviço.

### Sua máquina
- **Perfil** (A, B, C ou D) com a justificativa. Os perfis descrevem o que a máquina consegue rodar localmente: **A** estação forte (tudo, incluindo vídeo por IA); **B** GPU intermediária (tudo quantizado; vídeo por IA só em clipes curtos); **C** notebook ou GPU integrada (LLM pequeno, imagem leve, voz e música leves; **sem vídeo por IA local**); **D** abaixo do mínimo (só planejamento). Os limites são referências: quem decide é o benchmark.
- **Hardware detectado**: processador, memória, placa de vídeo, disco, sistema e ferramentas.
- **Caminho de aceleração**: quais aceleradores existem (CUDA, Vulkan, DirectML, OpenVINO, NPU) e se estão em uso.
- **Benchmark de calibração**: mede a velocidade real desta máquina, de verdade, com o que estiver instalado em **Modelos**: o **texto** (LLM local, em tokens por segundo), a **voz** (quanto tempo leva para falar), o **recorte de fundo** e **uma imagem gerada** (512 px, 4 passos). Leva uns 4 a 6 minutos e roda pela Fila (dá para pausar e cancelar). O que não está instalado aparece como **"não medido"**, com o caminho para instalar; a música e a animação por IA ainda não têm medição. Nada é estimado às escondidas.
- **Matriz de capacidades**: as 21 funcionalidades do app, cada uma **Disponível**, **Lenta** (com o tempo, e se ele foi **medido** ou **estimado**) ou **Indisponível** (com o motivo e o que fazer). Depois do benchmark, os tempos de imagem, voz e recorte passam de estimados para medidos. Dá para filtrar por estado.
- **Refazer diagnóstico**: coleta de novo os dados da máquina (cerca de 1 minuto) e recalcula tudo. Ao abrir, o app enfileira sozinho um diagnóstico: **leve** (~7 s) se já existe uma coleta anterior, **completo** (~1 min) na primeira vez. Depois de instalar programas em **Modelos**, um diagnóstico leve roda sozinho para o app enxergar o que foi instalado.

### Logs
Registro dos eventos do app, com filtro por serviço e nível e atualização automática opcional. Chaves e senhas são mascaradas antes de gravar. O arquivo fica em `data/logs/app.jsonl`.

## 11. Modelos: instalar o que o estúdio usa

A página lista tudo o que o estúdio precisa, em grupos: **Montagem de vídeo** (ffmpeg), **Imagens** (motor e modelo de imagens), **Voz** (Kokoro e as vozes) e **Recorte de fundo** (BiRefNet). Cada item mostra **para que serve**, a **licença** e o **tamanho** (aproximado do download, antes de instalar).

- **Instalar** baixa só aquele item. **Instalar tudo o que falta** baixa todos que ainda não estão instalados (cerca de 6 GB no total).
- A instalação **só acontece quando você clica**. Ela entra na **Fila** e o item mostra a barra de progresso; você pode continuar usando o app.
- Tudo vem de **fontes oficiais** (GitHub e Hugging Face) e só é aceito se o **SHA-256 publicado pela fonte** bater com o arquivo baixado. Se o download cair, ele **continua de onde parou**. O app confere o espaço livre antes de começar.
- Os arquivos ficam **dentro do projeto**: programas em `tools/`, modelos em `models/`. Nada é instalado no sistema.
- Para usar **outro disco**, veja `FABULIM_TOOLS_DIR` e `FABULIM_MODELS_DIR` em [SETUP.md](SETUP.md).
- Pela linha de comando: `.venv\Scripts\python scripts\instalar.py --lista` mostra o estado; `--tudo` instala tudo o que falta.

O **modelo de texto** (roteiro, textos do YouTube, tradução, prompt em texto livre) é o **Ollama** que você já tem instalado: o app o usa se estiver no ar. Sem ele, tudo continua funcionando com os **modos sem IA** (roteiro simples, modelo pronto de título e tags, versão sem traduzir, prompt no formato estruturado) e o app diz o que fazer.

## 12. Configurações

- **Aparência**: tema (Claro, Escuro ou Sistema) e idioma (Português ou English). As duas escolhas ficam guardadas neste navegador.
- **Pastas**: onde ficam os dados, os modelos e os programas (mudam pelas variáveis `FABULIM_DATA_DIR`, `FABULIM_MODELS_DIR` e `FABULIM_TOOLS_DIR`; veja [SETUP.md](SETUP.md)).
- **Conta do Claude**: o Claude é **opcional**. A página explica o que é e o que não é enviado, e tem o botão de conectar, que ainda não está ativo nesta versão. O chip **"Claude: desconectado"** do topo leva até este bloco. Ele continua "desconectado" mesmo que o Claude Code esteja logado no seu computador: **"conectado" só aparece depois que você conectar a conta pelo próprio app**. Até lá, **nada é enviado ao Claude**.
- **Sobre**: versão e endereço do servidor.

## 13. Formatos de prompt

Em **Personagens**, **Criar vídeo** e **Gerar imagem** há uma caixa para colar o prompt. O app lê **dois formatos** e preenche o formulário para você **revisar** (nada é gerado ainda). Os botões *Exemplo estruturado* e *Exemplo em texto livre* mostram cada um.

**Estruturado** (lido na hora, sem modelo de IA): um cabeçalho e linhas `Campo: valor`.

```
### PERSONAGEM
Nome: Lila
Estilo: 2D
Tipo/Espécie: coelhinha
Aparência: corpo redondinho, pelo lilás clarinho, orelhas compridas
Roupas e acessórios: vestido amarelo com bolinhas
Voz: aguda e doce, fala devagar
```

Cabeçalhos: `### PERSONAGEM`, `### ENREDO` e `### IMAGEM`. Campos do personagem: Nome, Estilo, Tipo/Espécie, Idade aparente, Aparência, Roupas e acessórios, Paleta de cores, Personalidade, Voz, Expressões desejadas, Observações. Do enredo: Título, Formato, Duração alvo, Idioma, Estilo, Personagens, Tema ou lição, Cenário(s), História, Música, Observações. Da imagem: Tipo, Estilo, Formato, Personagens, Descrição, Observações. Sem acento e com ou sem maiúsculas também vale; o que sobrar dos textos de exemplo do modelo de prompt é ignorado.

**Texto livre**: escreva com as suas palavras. O **modelo local** (Ollama) extrai os campos e o formulário volta preenchido; isso roda pela Fila e pode levar alguns minutos. Se o prompt for de outro tipo (um enredo colado em *Personagens*), o app avisa. O **histórico** guarda os prompts que você já colou.

Textos colados são tratados como **dado**, nunca como instrução: ordens escondidas num prompt não fazem nada, e o filtro de conteúdo para 2 a 5 anos examina tudo o que entra.

## 14. Problemas comuns

Veja [SETUP.md](SETUP.md#problemas-comuns).
