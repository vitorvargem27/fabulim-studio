import { PromptType } from '../core/models';

/**
 * Prompts de exemplo (dados de teste, não textos da interface): um no formato estruturado e um em texto livre por tipo.
 * Ajudam a experimentar sem escrever nada e mostram o formato que o app reconhece sem gastar o modelo local.
 */
export const PROMPT_EXAMPLES: Record<PromptType, { structured: string; free: string }> = {
  personagem: {
    structured: `### PERSONAGEM
Nome: Lila
Estilo: 2D
Tipo/Espécie: coelhinha
Idade aparente: 4 anos
Aparência: corpo redondinho, pelo lilás bem clarinho, orelhas compridas com o interior rosa, olhos grandes e brilhantes, bochechas rosadas
Roupas e acessórios: vestido amarelo com bolinhas brancas e um laço azul entre as orelhas
Paleta de cores: lilás, amarelo, rosa e azul
Personalidade: curiosa, gentil e sempre sorrindo
Voz: aguda e doce, fala devagar
Expressões desejadas: feliz, triste, surpreso, sono, bravinho
Observações: corpo inteiro, fundo liso`,
    free: 'Quero uma raposinha ruiva chamada Bia, de uns 5 anos, com um cachecol verde e olhos castanhos grandes. Ela é aventureira, corajosa e adora explorar o bosque.',
  },
  enredo: {
    structured: `### ENREDO
Título: A Lila e a estrelinha que se perdeu
Formato: short
Duração alvo: 45 s
Idioma: pt-BR
Estilo: 2D
Personagens: Lila
Tema ou lição: ajudar quem precisa
Cenário(s): jardim florido de dia; bosque tranquilo ao entardecer
História: Lila encontra uma estrelinha pequenina chorando no jardim: ela perdeu o caminho de casa. Lila pega a estrelinha no colo e as duas caminham pelo bosque. No caminho, Lila canta uma musiquinha para a estrelinha ficar calma. Ao entardecer, o céu se abre e a estrelinha volta para o alto. Ela agradece com um brilho e Lila volta feliz para casa.
Música: melodia alegre e calma, com marimba`,
    free: 'A Lila é uma coelhinha que descobre um ovo colorido no jardim. Ela cuida do ovo com carinho, canta para ele e, no fim, nasce um patinho que vira o melhor amigo dela. Quero um vídeo curto, calminho, de uns 45 segundos.',
  },
  imagem: {
    structured: `### IMAGEM
Tipo: cenário
Estilo: 2D
Formato: 16:9
Descrição: jardim florido de manhã, com flores grandes e coloridas, um caminho de pedrinhas e um céu azul com nuvens fofas
Observações: sem personagens, bem iluminado`,
    free: 'Um bosque tranquilo ao entardecer, com árvores baixinhas, vaga-lumes e um riacho pequeno, no estilo 2D.',
  },
};
