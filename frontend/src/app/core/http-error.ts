import { HttpErrorResponse } from '@angular/common/http';

/**
 * O texto que cabe na tela para um erro da API. O backend responde `{"detail": "mensagem em português"}` (409, 422, 503...)
 * ou, na validação de campos, uma lista de erros do FastAPI: mostramos a primeira mensagem, sem o caminho técnico.
 */
export function errorMessage(error: unknown, fallback = 'Algo deu errado. Tente de novo.'): string {
  if (error instanceof HttpErrorResponse) {
    if (error.status === 0) return 'Não consegui falar com o servidor do estúdio. Confira se o Fabulim está aberto.';
    const detail = (error.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown; loc?: unknown[] };
      const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1] ?? '') : '';
      const msg = typeof first.msg === 'string' ? first.msg : '';
      if (msg) return field && field !== 'body' ? `${field}: ${msg}` : msg;
    }
    if (error.status === 413) return 'O arquivo é grande demais.';
    if (error.status === 404) return 'Não encontrei isso no estúdio (talvez já tenha sido apagado).';
    if (error.status >= 500) return 'O estúdio teve um erro interno. Veja os detalhes em Status > Logs.';
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

/** O id que o backend devolve em conflitos de nome (`409` com `existing_id`), quando existe. */
export function existingId(error: unknown): string | null {
  if (error instanceof HttpErrorResponse && error.status === 409) {
    const id = (error.error as { existing_id?: unknown } | null)?.existing_id;
    return typeof id === 'string' ? id : null;
  }
  return null;
}
