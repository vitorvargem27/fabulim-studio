#!/usr/bin/env bash
# Fabulim Studio: roda lint, tipos, testes e cobertura com um comando. Use "./testar.sh --hw" para incluir o hardware real.
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
if [ -x .venv/bin/python ]; then PY=.venv/bin/python
elif command -v python3.12 >/dev/null 2>&1; then PY=python3.12
elif command -v python3 >/dev/null 2>&1; then PY=python3
else PY=python; fi
exec "$PY" scripts/testar.py "$@"
