"""Logs estruturados em JSON (uma linha por evento), com máscara de chaves e tokens (briefing, seção 11)."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

NOME_ARQUIVO = "app.jsonl"
LOGGER_RAIZ = "fabulim"
NIVEIS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

_PADROES_SEGREDO: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
)
_PADRAO_CHAVE_VALOR = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|senha|authorization)([\"']?\s*[:=]\s*[\"']?)([^\s\"',}]+)"
)


def mascarar(texto: str) -> str:
    """Troca chaves, tokens e senhas por ``***`` (mesmo que apareçam no meio de uma frase)."""
    for padrao in _PADROES_SEGREDO:
        texto = padrao.sub("***", texto)
    return _PADRAO_CHAVE_VALOR.sub(lambda m: f"{m.group(1)}{m.group(2)}***", texto)


class MascaraSegredos(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mascarar(record.getMessage())
        record.args = ()
        return True


class FormatadorJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entrada: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": getattr(record, "service", record.name.removeprefix(f"{LOGGER_RAIZ}.")),
            "msg": record.getMessage(),
        }
        job_id = getattr(record, "job_id", None)
        if job_id:
            entrada["job_id"] = job_id
        if record.exc_info:
            entrada["exc"] = mascarar(self.formatException(record.exc_info))
        return json.dumps(entrada, ensure_ascii=False)


def configurar_logging(log_dir: Path, *, console: bool = True) -> logging.Logger:
    """Configura o logger ``fabulim``: arquivo JSONL rotativo e, opcionalmente, console."""
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_RAIZ)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()

    arquivo = RotatingFileHandler(log_dir / NOME_ARQUIVO, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    arquivo.setFormatter(FormatadorJson())
    arquivo.addFilter(MascaraSegredos())
    logger.addHandler(arquivo)

    if console:
        saida = logging.StreamHandler(sys.stderr)
        saida.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
        saida.addFilter(MascaraSegredos())
        logger.addHandler(saida)
    return logger


def logger_do_servico(servico: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_RAIZ}.{servico}")


def ler_logs(
    log_dir: Path,
    *,
    servico: str | None = None,
    nivel: str | None = None,
    job_id: str | None = None,
    limite: int = 200,
    max_bytes: int = 1_000_000,
) -> list[dict[str, Any]]:
    """Últimas entradas do log (ordem cronológica), com filtros. Só lê o arquivo fixo do log."""
    arquivo = log_dir / NOME_ARQUIVO
    if not arquivo.is_file():
        return []
    tamanho = arquivo.stat().st_size
    with arquivo.open("rb") as f:
        f.seek(max(0, tamanho - max_bytes))
        bruto = f.read().decode("utf-8", errors="replace")
    minimo = NIVEIS.get((nivel or "").upper(), 0)
    saida: list[dict[str, Any]] = []
    for linha in bruto.splitlines():
        try:
            e = json.loads(linha)
        except json.JSONDecodeError:
            continue  # primeira linha cortada pelo seek, ou linha corrompida
        if not isinstance(e, dict):
            continue
        if servico and e.get("service") != servico:
            continue
        if job_id and e.get("job_id") != job_id:
            continue
        if NIVEIS.get(str(e.get("level")), 0) < minimo:
            continue
        saida.append(e)
    return saida[-limite:]
