import { Routes } from '@angular/router';

// Todas as páginas carregam sob demanda (o primeiro carregamento fica leve). O `title` é uma chave de tradução.
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'criar' },
  {
    path: 'criar',
    title: 'nav.criar',
    loadComponent: () => import('./pages/criar-video/criar-video.page').then((m) => m.CriarVideoPage),
  },
  {
    path: 'personagens',
    title: 'nav.personagens',
    loadComponent: () => import('./pages/personagens/personagens.page').then((m) => m.PersonagensPage),
  },
  {
    path: 'personagens/:id',
    title: 'nav.personagens',
    loadComponent: () => import('./pages/personagens/personagem.page').then((m) => m.PersonagemPage),
  },
  {
    path: 'imagem',
    title: 'nav.imagem',
    loadComponent: () => import('./pages/imagem/imagem.page').then((m) => m.ImagemPage),
  },
  {
    path: 'clipes',
    title: 'nav.clipes',
    loadComponent: () => import('./pages/clipes/clipes.page').then((m) => m.ClipesPage),
  },
  {
    path: 'projetos',
    title: 'nav.projetos',
    loadComponent: () => import('./pages/projetos/projetos.page').then((m) => m.ProjetosPage),
  },
  {
    path: 'projetos/:id',
    title: 'nav.projetos',
    loadComponent: () => import('./pages/projetos/projeto.page').then((m) => m.ProjetoPage),
  },
  {
    path: 'modelos',
    title: 'nav.modelos',
    loadComponent: () => import('./pages/modelos/modelos.page').then((m) => m.ModelosPage),
  },
  {
    path: 'fila',
    title: 'nav.fila',
    loadComponent: () => import('./pages/fila/fila.page').then((m) => m.FilaPage),
  },
  {
    path: 'status',
    loadComponent: () => import('./pages/status/status.page').then((m) => m.StatusPage),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'servicos' },
      {
        path: 'servicos',
        title: 'status.tab.servicos',
        loadComponent: () => import('./pages/status/servicos.page').then((m) => m.ServicosPage),
      },
      {
        path: 'maquina',
        title: 'status.tab.maquina',
        loadComponent: () => import('./pages/status/maquina.page').then((m) => m.MaquinaPage),
      },
      {
        path: 'logs',
        title: 'status.tab.logs',
        loadComponent: () => import('./pages/status/logs.page').then((m) => m.LogsPage),
      },
    ],
  },
  {
    path: 'configuracoes',
    title: 'nav.config',
    loadComponent: () => import('./pages/configuracoes/configuracoes.page').then((m) => m.ConfiguracoesPage),
  },
  {
    path: '**',
    title: 'notfound.title',
    loadComponent: () => import('./pages/not-found.page').then((m) => m.NotFoundPage),
  },
];
