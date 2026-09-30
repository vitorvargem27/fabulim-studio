import { HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { makeJob, provideTestHttp } from '../../testing/fixtures';
import { ApiService } from './api.service';

describe('ApiService', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: provideTestHttp() });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('lista as ferramentas e os modelos do catálogo', () => {
    let itens = 0;
    api.tools().subscribe((r) => (itens = r.items.length));
    const req = http.expectOne('/api/tools');
    expect(req.request.method).toBe('GET');
    req.flush({ items: [{ id: 'ffmpeg' }], tools_dir: 'a', models_dir: 'b' });
    expect(itens).toBe(1);
  });

  it('pede a instalação de um item pelo id, sem corpo', () => {
    api.installTool('flux2-klein-4b').subscribe();
    const req = http.expectOne('/api/tools/flux2-klein-4b/install');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toBeNull();
    req.flush(makeJob({ kind: 'ferramentas.instalar' }));
  });

  it('o diagnóstico leve manda o parâmetro light', () => {
    api.startDiagnostic(true).subscribe();
    const req = http.expectOne((r) => r.url === '/api/machine/diagnostic');
    expect(req.request.params.get('light')).toBe('true');
    req.flush(makeJob());
  });

  it('a busca de logs usa serviço, nível e o limite padrão de 200', () => {
    api.logs({ service: 'app', level: 'ERROR' }).subscribe();
    const req = http.expectOne((r) => r.url === '/api/logs');
    expect(req.request.params.get('service')).toBe('app');
    expect(req.request.params.get('level')).toBe('ERROR');
    expect(req.request.params.get('limit')).toBe('200');
    req.flush([]);
  });

  it('cria job com título opcional e age sobre um job existente', () => {
    api.createJob('demo.sleep', { seconds: 1 }, 'Teste').subscribe();
    const criar = http.expectOne('/api/jobs');
    expect(criar.request.body).toEqual({ kind: 'demo.sleep', params: { seconds: 1 }, title: 'Teste' });
    criar.flush(makeJob());

    api.jobAction('abc', 'pause').subscribe();
    http.expectOne('/api/jobs/abc/pause').flush(makeJob());
  });
});
