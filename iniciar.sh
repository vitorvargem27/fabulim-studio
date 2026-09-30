#!/usr/bin/env bash
# Fabulim Studio: sobe o app (backend + interface) e abre o navegador.
# Uso: ./iniciar.sh [--compilar] [--sem-navegador]
# Nada aqui instala coisas no sistema: usa o .venv e o node_modules do próprio projeto.
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

COMPILAR=0
ABRIR=1
for a in "$@"; do
  case "$a" in
    --compilar) COMPILAR=1 ;;
    --sem-navegador) ABRIR=0 ;;
  esac
done

PY=.venv/bin/python

echo
echo "  Fabulim Studio"
echo "  ------------------------------------------------------------"

if [ ! -x "$PY" ]; then
  echo "  [ERRO] Não encontrei o ambiente Python do projeto (.venv). Veja docs/SETUP.md."
  exit 1
fi

# configuração válida e porta efetiva (variável de ambiente > .env > 8765); o erro, se houver, aparece na tela
PORTA=$("$PY" scripts/servidor.py --porta) || { echo "  Corrija o arquivo .env (veja .env.example) e rode de novo."; exit 1; }
export FABULIM_PORT="$PORTA"
URL="http://127.0.0.1:${PORTA}"

[ -f frontend/dist/frontend/browser/index.html ] || COMPILAR=1
if [ "$COMPILAR" = 1 ]; then
  command -v node >/dev/null 2>&1 || { echo "  [ERRO] Node.js não encontrado. Veja docs/SETUP.md."; exit 1; }
  [ -d frontend/node_modules ] || { echo "  Instalando as dependências da interface (só na primeira vez)..."; npm --prefix frontend ci || exit 1; }
  echo "  Compilando a interface..."
  npm --prefix frontend run build || exit 1
fi

saudavel() { "$PY" -c "import sys,urllib.request as u; sys.exit(0 if u.urlopen('$URL/api/health', timeout=2).status==200 else 1)" >/dev/null 2>&1; }

if saudavel; then
  echo "  O Fabulim já está no ar em $URL"
else
  echo "  Subindo o servidor em $URL ..."
  mkdir -p data/logs
  nohup "$PY" scripts/servidor.py >data/logs/servidor.out 2>&1 &
  echo $! > data/servidor.pid
  for _ in $(seq 1 40); do saudavel && break; sleep 1; done
  saudavel || { echo "  [ERRO] O servidor não respondeu em 40 s. Veja data/logs/servidor.out."; exit 1; }
  echo "  Servidor no ar. Uma coleta leve do hardware roda ao iniciar: acompanhe em Fila e em Status."
fi

if [ "$ABRIR" = 1 ]; then
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1
  elif command -v open >/dev/null 2>&1; then open "$URL"; fi
fi
echo
echo "  Abra:   $URL"
echo "  Status: $URL/status/servicos"
echo "  Para encerrar: kill \$(cat data/servidor.pid)"
echo
