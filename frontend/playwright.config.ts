import { defineConfig } from '@playwright/test';
import path from 'node:path';

// E2E: sobe um backend próprio (porta 8877, dados temporários, hardware da fixture do ThinkPad) e usa o Microsoft Edge já
// instalado (channel "msedge"), então nenhum navegador é baixado. Três tamanhos de tela: desktop, tablet e celular.
// Um segundo backend (porta 8878, e2e/servidor_falso.py) tem os motores de imagem, recorte e voz falsos e o ffmpeg de
// verdade: nele roda o projeto "ferramentas", que percorre do personagem ao vídeo final em segundos.
const PORT = 8877;
const PORT_FERRAMENTAS = 8878;
const raiz = path.resolve(__dirname, '..');
const python = path.join(raiz, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const dados = path.join(raiz, 'data', 'e2e');
const dadosFerramentas = path.join(raiz, 'data', 'e2e-ferramentas');
const emServidorFalso = /ferramentas\.spec\.ts$/;

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    channel: 'msedge',
    locale: 'pt-BR',
    colorScheme: 'light',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', testIgnore: emServidorFalso, use: { viewport: { width: 1440, height: 900 } } },
    { name: 'tablet', testIgnore: emServidorFalso, use: { viewport: { width: 820, height: 1180 } } },
    { name: 'mobile', testIgnore: emServidorFalso, use: { viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true } },
    {
      name: 'ferramentas',
      testMatch: emServidorFalso,
      timeout: 180_000,
      expect: { timeout: 20_000 }, // cada passo grava arquivos e chama o ffmpeg: no notebook carregado os 10 s padrão não bastam
      use: { viewport: { width: 1440, height: 900 }, baseURL: `http://127.0.0.1:${PORT_FERRAMENTAS}` },
    },
  ],
  webServer: [
    {
      command: `"${python}" "${path.join(raiz, 'scripts', 'servidor.py')}"`,
      url: `http://127.0.0.1:${PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 90_000,
      env: {
        FABULIM_PORT: String(PORT),
        FABULIM_DATA_DIR: dados,
        // programas e modelos também isolados: o resultado não depende do que já está instalado nesta máquina
        FABULIM_TOOLS_DIR: path.join(dados, 'tools'),
        FABULIM_MODELS_DIR: path.join(dados, 'models'),
        FABULIM_HARDWARE_JSON: path.join(dados, 'hardware.json'),
        FABULIM_AUTO_DIAGNOSTICO: '0',
      },
    },
    {
      command: `"${python}" "${path.join(raiz, 'frontend', 'e2e', 'servidor_falso.py')}"`,
      url: `http://127.0.0.1:${PORT_FERRAMENTAS}/api/health`,
      reuseExistingServer: false,
      timeout: 90_000,
      env: {
        FABULIM_PORT: String(PORT_FERRAMENTAS),
        FABULIM_DATA_DIR: dadosFerramentas,
        // o ffmpeg vem da pasta tools/ do projeto (ou do sistema); os modelos de IA não são usados (os motores são falsos)
        FABULIM_MODELS_DIR: path.join(dadosFerramentas, 'models'),
        FABULIM_HARDWARE_JSON: path.join(dadosFerramentas, 'hardware.json'),
        FABULIM_AUTO_DIAGNOSTICO: '0',
      },
    },
  ],
});
