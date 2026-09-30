"""As tarefas da fila que produzem coisas de verdade (ler prompt, gerar imagem, personagem, clipe, vídeo).

Cada módulo registra os seus tipos de job em ``jobs.handlers.REGISTRO`` ao ser importado. Um job leva só ids e
parâmetros simples (nunca caminhos de arquivo): o handler busca tudo no banco e na biblioteca de mídias.
"""

from . import clipes, entrega, imagens, personagens, producao, projetos, prompts  # noqa: F401
