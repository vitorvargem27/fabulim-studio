#!/usr/bin/env bash
# Fabulim Studio: diagnóstico da máquina (Linux e macOS).
# Não instala nada e não pede root. Coleta fatos e grava config/hardware.json (mesmo formato do .ps1).
# Se houver Python 3.10+, chama scripts/perfil.py para classificar o perfil e gerar docs/AMBIENTE.md.
#
# Uso: bash scripts/diagnostico.sh [--leve] [--saida ARQUIVO] [--docs ARQUIVO] [--sem-perfil] [--silencioso]
#   --leve  só confere se a máquina mudou desde a última coleta (não reescreve o restante do JSON)

# Saída dos utilitários em inglês para o parse funcionar em qualquer idioma do sistema.
LC_ALL=C
export LC_ALL

LEVE=0
SEM_PERFIL=0
SILENCIOSO=0
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAIDA="$RAIZ/config/hardware.json"
DOCS="$RAIZ/docs/AMBIENTE.md"

uso() { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --leve) LEVE=1 ;;
    --sem-perfil) SEM_PERFIL=1 ;;
    --silencioso) SILENCIOSO=1 ;;
    --saida) SAIDA="${2:?--saida precisa de um caminho}"; shift ;;
    --docs) DOCS="${2:?--docs precisa de um caminho}"; shift ;;
    -h|--ajuda|--help) uso; exit 0 ;;
    *) echo "Opção desconhecida: $1" >&2; uso >&2; exit 2 ;;
  esac
  shift
done

# ---------------------------------------------------------------- utilidades
msg() { [ "$SILENCIOSO" = 1 ] || printf '%s\n' "$*"; }
tem() { command -v "$1" >/dev/null 2>&1; }

# tempo limite portátil: com_timeout SEGUNDOS comando args...
com_timeout() {
  local s="$1"; shift
  if tem timeout; then timeout "$s" "$@"
  elif tem gtimeout; then gtimeout "$s" "$@"
  else "$@"; fi
}

# primeira versão (N.N ou N.N.N) que aparece na saída de um comando
ver() { "$@" 2>&1 | head -n 5 | grep -o '[0-9][0-9]*\.[0-9][0-9]*\(\.[0-9][0-9]*\)*' | head -n 1; }

# --- JSON sem dependências ---
jstr() {  # texto entre aspas, ou null se vazio
  if [ -z "${1:-}" ]; then printf 'null'; return; fi
  local s
  s=$(printf '%s' "$1" | tr '\n\r\t' '   ' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')
  printf '"%s"' "$s"
}
jnum() { case "${1:-}" in ''|*[!0-9]*) printf 'null' ;; *) printf '%s' "$1" ;; esac; }
jbool() { if [ "${1:-0}" = 1 ]; then printf 'true'; else printf 'false'; fi; }
jtri() { case "${1:-}" in 1) printf 'true' ;; 0) printf 'false' ;; *) printf 'null' ;; esac; }
jlista() {  # lista JSON de textos a partir de argumentos
  local primeiro=1 x
  printf '['
  for x in "$@"; do
    [ -n "$x" ] || continue
    [ "$primeiro" = 1 ] || printf ', '
    primeiro=0
    jstr "$x"
  done
  printf ']'
}
sha16() {
  if tem sha256sum; then sha256sum | cut -c1-16
  elif tem shasum; then shasum -a 256 | cut -c1-16
  else cksum | cut -d' ' -f1; fi
}

# ---------------------------------------------------------------- sistema operacional
UNAME_S=$(uname -s 2>/dev/null)
UNAME_M=$(uname -m 2>/dev/null)
case "$UNAME_S" in
  Linux) FAMILIA=linux ;;
  Darwin) FAMILIA=macos ;;
  *) echo "Sistema não suportado por este script: $UNAME_S. No Windows use scripts/diagnostico.ps1." >&2; exit 2 ;;
esac
case "$UNAME_M" in arm64|aarch64) ARCH=arm64 ;; *) ARCH=x64 ;; esac
if [ "$FAMILIA" = macos ] && [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ]; then ARCH=arm64; fi

if [ "$FAMILIA" = linux ]; then
  SO_NOME=$( (. /etc/os-release 2>/dev/null; printf '%s' "${PRETTY_NAME:-Linux}") )
  SO_VERSAO=$( (. /etc/os-release 2>/dev/null; printf '%s' "${VERSION_ID:-}") )
  [ -n "$SO_VERSAO" ] || SO_VERSAO=$(uname -r)
  if grep -qi microsoft /proc/version 2>/dev/null; then SO_NOME="$SO_NOME (WSL)"; fi
else
  SO_NOME="$(sw_vers -productName 2>/dev/null) $(sw_vers -productVersion 2>/dev/null)"
  SO_VERSAO=$(sw_vers -productVersion 2>/dev/null)
fi
SO_KERNEL=$(uname -r 2>/dev/null)

# ---------------------------------------------------------------- sistema, bateria, energia
CHASSI=""
if [ "$FAMILIA" = linux ]; then
  DMI=/sys/class/dmi/id
  SIS_FAB=$(cat "$DMI/sys_vendor" 2>/dev/null)
  SIS_MOD=$(cat "$DMI/product_name" 2>/dev/null)
  SIS_COM=$(cat "$DMI/product_version" 2>/dev/null)
  if [ -z "$SIS_MOD" ] && [ -r /proc/device-tree/model ]; then SIS_MOD=$(tr -d '\0' < /proc/device-tree/model); fi
  CHASSI=$(cat "$DMI/chassis_type" 2>/dev/null)
else
  SIS_FAB=Apple
  SIS_MOD=$(sysctl -n hw.model 2>/dev/null)
  SIS_COM=$(system_profiler SPHardwareDataType 2>/dev/null | awk -F': ' '/Model Name/{print $2; exit}')
fi
case "$SIS_COM" in ''|None|'System Version'|'Not Specified'|'To be filled'*|'Default string'|1.0|0) SIS_COM="" ;; esac

BAT_PRESENTE=0; BAT_PCT=""; BAT_TOMADA=""
if [ "$FAMILIA" = linux ]; then
  for b in /sys/class/power_supply/BAT*; do
    [ -e "$b/capacity" ] || continue
    BAT_PRESENTE=1; BAT_PCT=$(cat "$b/capacity" 2>/dev/null); break
  done
  for a in /sys/class/power_supply/*; do
    [ "$(cat "$a/type" 2>/dev/null)" = Mains ] || continue
    if [ "$(cat "$a/online" 2>/dev/null)" = 1 ]; then BAT_TOMADA=1; elif [ -z "$BAT_TOMADA" ]; then BAT_TOMADA=0; fi
  done
else
  PM=$(pmset -g batt 2>/dev/null)
  case "$PM" in *InternalBattery*) BAT_PRESENTE=1; BAT_PCT=$(printf '%s' "$PM" | grep -o '[0-9]*%' | head -n 1 | tr -d '%') ;; esac
  case "$PM" in *"AC Power"*) BAT_TOMADA=1 ;; *"Battery Power"*) BAT_TOMADA=0 ;; esac
fi

PORTATIL=0
[ "$BAT_PRESENTE" = 1 ] && PORTATIL=1
case "$CHASSI" in 8|9|10|11|14|30|31|32) PORTATIL=1 ;; esac
if [ "$FAMILIA" = macos ]; then case "$SIS_MOD" in *MacBook*) PORTATIL=1 ;; esac; fi

PLANO=""
if [ "$FAMILIA" = linux ]; then
  if tem powerprofilesctl; then PLANO=$(powerprofilesctl get 2>/dev/null)
  elif [ -r /sys/firmware/acpi/platform_profile ]; then PLANO=$(cat /sys/firmware/acpi/platform_profile 2>/dev/null); fi
else
  case "$(pmset -g 2>/dev/null)" in *"lowpowermode 1"*) PLANO="Economia de energia (modo de baixo consumo)" ;; *) PLANO="Normal" ;; esac
fi

# ---------------------------------------------------------------- CPU
CPU_MODELO=""; CPU_NUCLEOS=""; CPU_THREADS=""; CPU_MHZ=""
CPU_AVX=0; CPU_AVX2=0; CPU_AVX512=0; CPU_SSE42=0; CPU_NEON=0
if [ "$FAMILIA" = linux ]; then
  CPU_MODELO=$(lscpu 2>/dev/null | awk -F': *' '/^Model name/{print $2; exit}')
  [ -n "$CPU_MODELO" ] || CPU_MODELO=$(awk -F': ' '/^(model name|Model|Hardware)/{print $2; exit}' /proc/cpuinfo 2>/dev/null)
  CPU_THREADS=$(nproc --all 2>/dev/null)
  [ -n "$CPU_THREADS" ] || CPU_THREADS=$(grep -c '^processor' /proc/cpuinfo 2>/dev/null)
  NPS=$(lscpu 2>/dev/null | awk -F': *' '/^Core\(s\) per socket/{print $2; exit}')
  SOCK=$(lscpu 2>/dev/null | awk -F': *' '/^Socket\(s\)/{print $2; exit}')
  if [ -n "$NPS" ] && [ -n "$SOCK" ]; then
    CPU_NUCLEOS=$((NPS * SOCK))
  else
    # sem lscpu: "cpu cores" do /proc/cpuinfo é por soquete; multiplica pelos soquetes distintos
    NPS=$(awk -F': ' '/^cpu cores/{print $2; exit}' /proc/cpuinfo 2>/dev/null)
    SOCK=$(awk -F': ' '/^physical id/{s[$2]=1} END{n=0; for (k in s) n++; print (n ? n : 1)}' /proc/cpuinfo 2>/dev/null)
    if [ -n "$NPS" ]; then CPU_NUCLEOS=$((NPS * SOCK)); else CPU_NUCLEOS="$CPU_THREADS"; fi
  fi
  CPU_MHZ=$(lscpu 2>/dev/null | awk -F': *' '/^CPU max MHz/{printf "%d", $2; exit}')
  FLAGS=" $(grep -m1 -i '^flags\|^Features' /proc/cpuinfo 2>/dev/null | cut -d: -f2) "
  case "$FLAGS" in *" avx "*) CPU_AVX=1 ;; esac
  case "$FLAGS" in *" avx2 "*) CPU_AVX2=1 ;; esac
  case "$FLAGS" in *" avx512f "*) CPU_AVX512=1 ;; esac
  case "$FLAGS" in *" sse4_2 "*) CPU_SSE42=1 ;; esac
  case "$FLAGS" in *" asimd "*|*" neon "*) CPU_NEON=1 ;; esac
else
  CPU_MODELO=$(sysctl -n machdep.cpu.brand_string 2>/dev/null)
  CPU_NUCLEOS=$(sysctl -n hw.physicalcpu 2>/dev/null)
  CPU_THREADS=$(sysctl -n hw.logicalcpu 2>/dev/null)
  if [ "$ARCH" = arm64 ]; then
    CPU_NEON=1
  else
    FLAGS=" $(sysctl -n machdep.cpu.features machdep.cpu.leaf7_features 2>/dev/null | tr '\n' ' ') "
    case "$FLAGS" in *" AVX1.0 "*) CPU_AVX=1 ;; esac
    case "$FLAGS" in *" AVX2 "*) CPU_AVX2=1 ;; esac
    case "$FLAGS" in *" AVX512F "*) CPU_AVX512=1 ;; esac
    case "$FLAGS" in *" SSE4.2 "*) CPU_SSE42=1 ;; esac
  fi
fi
NPU_PRESENTE=0; NPU_NOME=""
if [ "$FAMILIA" = macos ] && [ "$ARCH" = arm64 ]; then
  NPU_PRESENTE=1; NPU_NOME="Apple Neural Engine"
elif [ "$FAMILIA" = linux ]; then
  if [ -e /dev/accel/accel0 ]; then NPU_PRESENTE=1; NPU_NOME="NPU (/dev/accel/accel0)"; fi
fi

# ---------------------------------------------------------------- memória e disco
if [ "$FAMILIA" = linux ]; then
  RAM_TOTAL_MB=$(awk '/^MemTotal:/{printf "%d", $2/1024}' /proc/meminfo 2>/dev/null)
  # MemAvailable é o certo; MemFree é o plano B em kernels e ambientes que não o informam
  RAM_LIVRE_MB=$(awk '/^MemAvailable:/{a=$2} /^MemFree:/{f=$2} END{printf "%d", (a ? a : f)/1024}' /proc/meminfo 2>/dev/null)
else
  RAM_TOTAL_MB=$(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%d", $1/1048576}')
  PAG=$(sysctl -n hw.pagesize 2>/dev/null)
  RAM_LIVRE_MB=$(vm_stat 2>/dev/null | awk -v pag="${PAG:-4096}" '/^Pages (free|inactive|speculative):/{gsub(/\./,"",$NF); n+=$NF} END{printf "%d", n*pag/1048576}')
fi

DF=$(df -Pk "$RAIZ" 2>/dev/null | tail -n 1)
DISCO_TOTAL_MB=$(printf '%s' "$DF" | awk '{printf "%d", $2/1024}')
DISCO_LIVRE_MB=$(printf '%s' "$DF" | awk '{printf "%d", $4/1024}')
DISCO_MONTAGEM=$(printf '%s' "$DF" | awk '{print $NF}')
DISCO_TIPO=desconhecido
if [ "$FAMILIA" = linux ] && tem lsblk; then
  DEV=$(df -P "$RAIZ" 2>/dev/null | awk 'NR==2{print $1}')
  ROTA=$(lsblk -ndo ROTA "$DEV" 2>/dev/null | head -n 1 | tr -d ' ')
  case "$DEV" in *nvme*) BUS=" (NVMe)" ;; *) BUS="" ;; esac
  case "$ROTA" in 0) DISCO_TIPO="SSD$BUS" ;; 1) DISCO_TIPO=HDD ;; esac
elif [ "$FAMILIA" = macos ]; then
  case "$(diskutil info / 2>/dev/null | awk -F': *' '/Solid State/{print $2; exit}')" in Yes) DISCO_TIPO=SSD ;; No) DISCO_TIPO=HDD ;; esac
fi

# ---------------------------------------------------------------- GPUs
# Uma linha por GPU: fabricante|nome|dedicada_mb|compartilhada_mb|driver|tipo|pci
coletar_gpus_linux() {
  if tem nvidia-smi; then
    com_timeout 10 nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits 2>/dev/null |
      while IFS=',' read -r nome mem drv; do
        nome=$(printf '%s' "$nome" | sed 's/^ *//;s/ *$//'); mem=$(printf '%s' "$mem" | tr -d ' '); drv=$(printf '%s' "$drv" | tr -d ' ')
        [ -n "$nome" ] && printf 'nvidia|%s|%s||%s||\n' "$nome" "${mem%.*}" "$drv"
      done
  fi
  local c d ven fab slot nome ded comp drv dev
  for c in /sys/class/drm/card[0-9]*; do
    case "$c" in *-*) continue ;; esac  # ignora conectores (card0-eDP-1)
    d="$c/device"; [ -r "$d/vendor" ] || continue
    ven=$(cat "$d/vendor" 2>/dev/null)
    case "$ven" in
      0x10de) continue ;;  # NVIDIA já coberta pelo nvidia-smi
      0x8086) fab=intel ;;
      0x1002|0x1022) fab=amd ;;
      0x1af4|0x15ad|0x1234|0x1b36|0x1414) continue ;;  # GPUs virtuais
      *) fab=unknown ;;
    esac
    dev=$(cat "$d/device" 2>/dev/null)
    slot=$(awk -F= '/^PCI_SLOT_NAME/{print $2}' "$d/uevent" 2>/dev/null)
    nome=""
    if tem lspci && [ -n "$slot" ]; then
      nome=$(lspci -s "$slot" -mm 2>/dev/null | sed -E 's/^[^"]*"[^"]*" "([^"]*)" "([^"]*)".*/\1 \2/')
    fi
    [ -n "$nome" ] || nome="GPU $ven:$dev"
    ded=""; comp=""
    [ -r "$d/mem_info_vram_total" ] && ded=$(awk '{printf "%d", $1/1048576}' "$d/mem_info_vram_total")
    [ -r "$d/mem_info_gtt_total" ] && comp=$(awk '{printf "%d", $1/1048576}' "$d/mem_info_gtt_total")
    drv=$(basename "$(readlink -f "$d/driver" 2>/dev/null)" 2>/dev/null)
    printf '%s|%s|%s|%s|%s||%s\n' "$fab" "$nome" "$ded" "$comp" "$drv" "$ven:$dev"
  done
}

coletar_gpus_macos() {
  system_profiler SPDisplaysDataType 2>/dev/null | awk '
    function flush() { printf "%s|%s|%s|||%s|\n", fab, nome, ded, (fab == "apple" ? "unified" : ""); nome = "" }
    /Chipset Model:/ { if (nome != "") flush(); sub(/^.*Chipset Model: */, ""); nome = $0; ded = ""; fab = "unknown" }
    /Vendor:/ { v = tolower($0); if (v ~ /apple/) fab = "apple"; else if (v ~ /amd|ati/) fab = "amd"; else if (v ~ /intel/) fab = "intel"; else if (v ~ /nvidia/) fab = "nvidia" }
    /VRAM \(/ { if (match($0, /[0-9]+/)) { n = substr($0, RSTART, RLENGTH) + 0; if ($0 ~ /GB/) n = n * 1024; ded = n } }
    END { if (nome != "") flush() }'
}

if [ "$FAMILIA" = linux ]; then GPUS_LINHAS=$(coletar_gpus_linux); else GPUS_LINHAS=$(coletar_gpus_macos); fi
# formato macOS tem 7 campos (fab|nome|ded|comp|driver|kind|pci): garante 7 campos nas linhas do Linux também
GPUS_LINHAS=$(printf '%s\n' "$GPUS_LINHAS" | awk -F'|' 'NF>0 && $2!=""{printf "%s|%s|%s|%s|%s|%s|%s\n", $1,$2,$3,$4,$5,$6,$7}')

AGORA=$(date +%Y-%m-%dT%H:%M:%S%z | sed -E 's/([+-][0-9]{2})([0-9]{2})$/\1:\2/')

# ---------------------------------------------------------------- impressão digital (detecta mudança de máquina)
PARTES="$CPU_MODELO;$RAM_TOTAL_MB;$FAMILIA $SO_VERSAO;$PORTATIL;$(printf '%s' "$GPUS_LINHAS" | awk -F'|' '{printf "%s|%s;", $2, $5}')"
FINGERPRINT=$(printf '%s' "$PARTES" | sha16)

# ---------------------------------------------------------------- perfil (classificador em Python)
achar_python() {
  local c
  for c in python3.12 python3.13 python3 python; do
    if tem "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      printf '%s' "$c"; return 0
    fi
  done
  return 1
}

rodar_perfil() {  # $1 = completo|leve
  if [ "$SEM_PERFIL" = 1 ]; then return; fi
  local py; py=$(achar_python)
  if [ -z "$py" ]; then
    msg "Python 3.10+ não encontrado: coleta feita, mas o perfil não foi classificado (instale o Python 3.12 e rode de novo)."
    return
  fi
  if [ "$1" = completo ]; then
    "$py" "$RAIZ/scripts/perfil.py" --hardware "$SAIDA" --docs "$DOCS"
  else
    "$py" "$RAIZ/scripts/perfil.py" --hardware "$SAIDA" --sem-docs
  fi
}

# ---------------------------------------------------------------- modo leve: só confere se a máquina mudou
if [ "$LEVE" = 1 ] && [ -f "$SAIDA" ]; then
  ANTERIOR=$(grep -o '"fingerprint": *"[^"]*"' "$SAIDA" 2>/dev/null | sed -E 's/.*: *"([^"]*)"/\1/')
  if [ "$ANTERIOR" = "$FINGERPRINT" ]; then
    MUDOU=false
    msg "Máquina inalterada desde a última coleta."
  else
    MUDOU=true
    msg "AVISO: a máquina mudou desde a última coleta (CPU, RAM, GPU/driver ou sistema). Rode scripts/diagnostico.sh sem --leve para refazer o perfil."
  fi
  sed -E "s/\"changed_since_last_run\": *(true|false)/\"changed_since_last_run\": $MUDOU/" "$SAIDA" > "$SAIDA.tmp" && mv "$SAIDA.tmp" "$SAIDA"
  rodar_perfil leve
  exit 0
fi
[ "$LEVE" = 1 ] && msg "Modo leve sem coleta anterior: fazendo o diagnóstico completo."
msg "Fabulim Studio: diagnóstico da máquina (completo)"

# ---------------------------------------------------------------- aceleração
NV_CUDA=""; NV_DRIVER=""
if tem nvidia-smi; then
  NV_CUDA=$(com_timeout 10 nvidia-smi 2>/dev/null | grep -o 'CUDA Version: *[0-9.]*' | grep -o '[0-9][0-9.]*$')
  NV_DRIVER=$(com_timeout 10 nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1 | tr -d ' ')
fi

ROCM_GFX=""; ROCM_OK=0
if tem rocminfo; then
  ROCM_GFX=$(com_timeout 20 rocminfo 2>/dev/null | grep -o 'gfx[0-9a-f]\{3,4\}' | sort -u | tr '\n' ' ' | sed 's/ *$//')
  [ -n "$ROCM_GFX" ] && ROCM_OK=1
fi

VK_TXT=""; VK_OK=0; VK_VER=""
if tem vulkaninfo; then
  VK_TXT=$(com_timeout 20 vulkaninfo --summary 2>/dev/null)
  VK_VER=$(printf '%s\n' "$VK_TXT" | sed -nE 's/^Vulkan Instance Version: *([0-9.]+).*/\1/p' | head -n 1)
elif tem ldconfig && ldconfig -p 2>/dev/null | grep -q libvulkan; then
  VK_OK=1
fi
VK_DEVS=$(printf '%s\n' "$VK_TXT" | awk '
  /^GPU[0-9]+:/ { if (n != "") print n "|" t; n = ""; t = "" }
  /deviceName/ { sub(/^[^=]*= */, ""); n = $0 }
  /deviceType/ { sub(/.*PHYSICAL_DEVICE_TYPE_/, ""); t = tolower($0) }
  END { if (n != "") print n "|" t }')
[ -n "$VK_DEVS" ] && VK_OK=1

METAL_OK=0; METAL_TXT=""
if [ "$FAMILIA" = macos ]; then
  METAL_OK=1
  METAL_TXT=$(system_profiler SPDisplaysDataType 2>/dev/null | awk -F': *' '/Metal (Support|Family)/{print $2; exit}')
fi

# ---------------------------------------------------------------- ferramentas
PY_CMD=""; for c in python3 python; do if tem "$c"; then PY_CMD=$(command -v "$c"); break; fi; done
PY_VER=""; [ -n "$PY_CMD" ] && PY_VER=$(ver "$PY_CMD" --version)
PY_VERS=""; for v in 3.9 3.10 3.11 3.12 3.13 3.14 3.15; do tem "python$v" && PY_VERS="$PY_VERS $v"; done

ferramenta_json() {  # $1 = comando, $2 = argumento de versão (padrão --version)
  local p v
  p=$(command -v "$1" 2>/dev/null)
  if [ -z "$p" ]; then printf '{"installed": false, "version": null, "path": null}'; return; fi
  v=$(ver "$p" "${2:---version}")
  printf '{"installed": true, "version": %s, "path": %s}' "$(jstr "$v")" "$(jstr "$p")"
}

FF_PATH=""; if [ -x "$RAIZ/tools/ffmpeg/bin/ffmpeg" ]; then FF_PATH="$RAIZ/tools/ffmpeg/bin/ffmpeg"; else FF_PATH=$(command -v ffmpeg 2>/dev/null); fi; FF_VER=""; FF_ENC=""
if [ -n "$FF_PATH" ]; then
  FF_VER=$("$FF_PATH" -version 2>/dev/null | sed -nE 's/^ffmpeg version ([^ ]+).*/\1/p' | head -n 1)
  FF_ENC=$("$FF_PATH" -hide_banner -encoders 2>/dev/null | grep -o 'libx264\|h264_qsv\|h264_nvenc\|h264_amf\|h264_videotoolbox\|h264_vaapi' | sort -u | tr '\n' ' ')
fi

OLL_PATH=$(command -v ollama 2>/dev/null); OLL_VER=""; OLL_ATIVO=0; OLL_MODELOS=""; OLL_CARREGADOS=""; OLL_GPUS=""; OLL_DROP=0
if [ -n "$OLL_PATH" ] && tem curl; then
  V=$(curl -s -m 2 http://127.0.0.1:11434/api/version 2>/dev/null)
  case "$V" in *version*)
    OLL_ATIVO=1
    OLL_VER=$(printf '%s' "$V" | sed -E 's/.*"version" *: *"([^"]*)".*/\1/')
    OLL_MODELOS=$(curl -s -m 3 http://127.0.0.1:11434/api/tags 2>/dev/null | grep -o '"name":"[^"]*","model":"[^"]*","modified_at":"[^"]*","size":[0-9]*' | sed -E 's/"name":"([^"]*)".*"size":([0-9]*)/\1|\2/')
    # /api/ps traz todos os modelos numa linha só; o awk quebra em uma linha por modelo (sed com \n não é portátil)
    OLL_CARREGADOS=$(curl -s -m 3 http://127.0.0.1:11434/api/ps 2>/dev/null | awk '{gsub(/\},\{"name"/, "}\n{\"name\""); print}' |
      sed -nE 's/.*"name":"([^"]*)".*"size":([0-9]+),.*"size_vram":([0-9]+).*/\1|\2|\3/p')
    ;;
  esac
fi
[ -n "$OLL_PATH" ] && [ -z "$OLL_VER" ] && OLL_VER=$(ver ollama --version)
if [ -n "$OLL_PATH" ]; then
  OLL_LOG=""
  if [ -r "$HOME/.ollama/logs/server.log" ]; then
    OLL_LOG=$(grep -E 'discovering available GPUs|dropping integrated GPU|msg="inference compute"' "$HOME/.ollama/logs/server.log" 2>/dev/null | tail -n 40)
  elif tem journalctl; then
    OLL_LOG=$(journalctl -u ollama --no-pager 2>/dev/null | grep -E 'discovering available GPUs|dropping integrated GPU|msg="inference compute"' | tail -n 40)
  fi
  OLL_GPUS=$(printf '%s\n' "$OLL_LOG" | awk '
    /discovering available GPUs/ { n = 0; next }
    /dropping integrated GPU|msg="inference compute"/ {
      drop = ($0 ~ /dropping integrated GPU/) ? 1 : 0; lib = ""; desc = ""
      if (match($0, /library=[^ ]+/)) lib = substr($0, RSTART + 8, RLENGTH - 8)
      if (match($0, /description="[^"]*"/)) desc = substr($0, RSTART + 13, RLENGTH - 14)
      else if (match($0, /description=[^ ]+/)) desc = substr($0, RSTART + 12, RLENGTH - 12)
      n++; L[n] = lib "|" desc "|" drop
    }
    END { for (i = 1; i <= n; i++) print L[i] }')
  case "$OLL_GPUS" in *"|1") OLL_DROP=1 ;; esac
fi

CL_PATH=$(command -v claude 2>/dev/null); CL_ORIGEM=path
if [ -z "$CL_PATH" ]; then
  for f in "$HOME/.claude/local/claude" "$HOME/.local/bin/claude"; do [ -x "$f" ] && CL_PATH="$f" && break; done
fi
if [ -z "$CL_PATH" ] && [ "$FAMILIA" = macos ]; then
  CL_PATH=$(ls -d "$HOME/Library/Application Support/Claude/claude-code"/*/claude 2>/dev/null | sort -V | tail -n 1)
  [ -n "$CL_PATH" ] && CL_ORIGEM=app
fi
CL_VER=""; CL_LOGADO=""; CL_METODO=""; CL_PLANO=""
if [ -n "$CL_PATH" ]; then
  CL_VER=$(ver "$CL_PATH" --version)
  # `claude auth status` é o caminho oficial; nunca lemos arquivos de credencial. Guardamos só o essencial.
  AUTH=$(com_timeout 20 "$CL_PATH" auth status 2>/dev/null | tr -d '\n')
  CL_LOGADO=$(printf '%s' "$AUTH" | sed -nE 's/.*"loggedIn" *: *(true|false).*/\1/p')
  CL_METODO=$(printf '%s' "$AUTH" | sed -nE 's/.*"authMethod" *: *"([^"]*)".*/\1/p')
  CL_PLANO=$(printf '%s' "$AUTH" | sed -nE 's/.*"subscriptionType" *: *"([^"]*)".*/\1/p')
fi

OV_OK=0; OV_VER=""; OV_CAND=0
case "$GPUS_LINHAS" in intel\|*|*$'\n'intel\|*) OV_CAND=1 ;; esac
case "$CPU_MODELO" in *Intel*) OV_CAND=1 ;; esac
if [ -n "$PY_CMD" ]; then
  OV_VER=$(com_timeout 25 "$PY_CMD" -c 'import openvino; print(openvino.__version__)' 2>/dev/null | head -n 1)
  [ -n "$OV_VER" ] && OV_OK=1
fi

# ---------------------------------------------------------------- monta o JSON
gpus_json() {
  local primeiro=1 fab nome ded comp drv kind pci gfx gfxsrc
  printf '['
  while IFS='|' read -r fab nome ded comp drv kind pci; do
    [ -n "$nome" ] || continue
    gfx="null"; gfxsrc="null"
    if [ "$fab" = amd ] && [ "$ROCM_OK" = 1 ] && [ "$(printf '%s' "$ROCM_GFX" | wc -w | tr -d ' ')" = 1 ]; then
      gfx=$(jstr "$ROCM_GFX"); gfxsrc=$(jstr "rocminfo (medido)")
    fi
    [ "$primeiro" = 1 ] || printf ','
    primeiro=0
    printf '\n    {"vendor": %s, "name": %s, "kind": %s, "dedicated_mb": %s, "shared_mb": %s, "driver": %s, "driver_date": null, "driver_model": null, "d3d12_ml": null, "pci_id": %s, "gfx_arch": %s, "gfx_arch_source": %s}' \
      "$(jstr "$fab")" "$(jstr "$nome")" "$(jstr "$kind")" "$(jnum "$ded")" "$(jnum "$comp")" "$(jstr "$drv")" "$(jstr "$pci")" "$gfx" "$gfxsrc"
  done <<EOF
$GPUS_LINHAS
EOF
  printf '\n  ]'
}

vulkan_dispositivos_json() {
  local primeiro=1 nome tipo
  printf '['
  while IFS='|' read -r nome tipo; do
    [ -n "$nome" ] || continue
    [ "$primeiro" = 1 ] || printf ', '
    primeiro=0
    printf '{"name": %s, "type": %s}' "$(jstr "$nome")" "$(jstr "$tipo")"
  done <<EOF
$VK_DEVS
EOF
  printf ']'
}

ollama_modelos_json() {
  local primeiro=1 nome tam
  printf '['
  while IFS='|' read -r nome tam; do
    [ -n "$nome" ] || continue
    [ "$primeiro" = 1 ] || printf ', '
    primeiro=0
    printf '{"name": %s, "size_mb": %s}' "$(jstr "$nome")" "$(printf '%s' "$tam" | awk '{printf "%d", $1/1048576}')"
  done <<EOF
$OLL_MODELOS
EOF
  printf ']'
}

ollama_carregados_json() {
  local primeiro=1 nome tam vram
  printf '['
  while IFS='|' read -r nome tam vram; do
    [ -n "$nome" ] || continue
    [ "$primeiro" = 1 ] || printf ', '
    primeiro=0
    printf '{"name": %s, "size_mb": %s, "size_vram_mb": %s}' "$(jstr "$nome")" \
      "$(printf '%s' "$tam" | awk '{printf "%d", $1/1048576}')" "$(printf '%s' "$vram" | awk '{printf "%d", $1/1048576}')"
  done <<EOF
$OLL_CARREGADOS
EOF
  printf ']'
}

ollama_gpus_json() {
  local primeiro=1 lib nome drop
  printf '['
  while IFS='|' read -r lib nome drop; do
    [ -n "$lib" ] || continue
    [ "$primeiro" = 1 ] || printf ', '
    primeiro=0
    printf '{"library": %s, "name": %s, "dropped_integrated": %s}' "$(jstr "$lib")" "$(jstr "$nome")" "$(jbool "$drop")"
  done <<EOF
$OLL_GPUS
EOF
  printf ']'
}

emitir_json() {
  printf '{\n'
  printf '  "schema_version": 1,\n'
  printf '  "collected_at": %s,\n' "$(jstr "$AGORA")"
  printf '  "full_collected_at": %s,\n' "$(jstr "$AGORA")"
  printf '  "mode": "full",\n'
  printf '  "os": {"family": "%s", "name": %s, "version": %s, "build": null, "arch": "%s", "kernel": %s},\n' \
    "$FAMILIA" "$(jstr "$SO_NOME")" "$(jstr "$SO_VERSAO")" "$ARCH" "$(jstr "$SO_KERNEL")"
  printf '  "system": {"vendor": %s, "model": %s, "marketing_name": %s, "is_laptop": %s, "battery": {"present": %s, "percent": %s, "on_ac": %s}, "power_plan": %s, "power_plan_guid": null},\n' \
    "$(jstr "$SIS_FAB")" "$(jstr "$SIS_MOD")" "$(jstr "$SIS_COM")" "$(jbool "$PORTATIL")" "$(jbool "$BAT_PRESENTE")" "$(jnum "$BAT_PCT")" "$(jtri "$BAT_TOMADA")" "$(jstr "$PLANO")"
  printf '  "cpu": {"model": %s, "cores": %s, "threads": %s, "max_mhz": %s, "features": {"avx": %s, "avx2": %s, "avx512": %s, "sse42": %s, "neon": %s}, "npu": {"present": %s, "name": %s}},\n' \
    "$(jstr "$CPU_MODELO")" "$(jnum "$CPU_NUCLEOS")" "$(jnum "$CPU_THREADS")" "$(jnum "$CPU_MHZ")" \
    "$(jbool "$CPU_AVX")" "$(jbool "$CPU_AVX2")" "$(jbool "$CPU_AVX512")" "$(jbool "$CPU_SSE42")" "$(jbool "$CPU_NEON")" "$(jbool "$NPU_PRESENTE")" "$(jstr "$NPU_NOME")"
  printf '  "memory": {"ram_total_mb": %s, "ram_free_mb": %s},\n' "$(jnum "$RAM_TOTAL_MB")" "$(jnum "$RAM_LIVRE_MB")"
  printf '  "disk": {"path": %s, "drive": %s, "total_mb": %s, "free_mb": %s, "kind": %s},\n' \
    "$(jstr "$RAIZ")" "$(jstr "$DISCO_MONTAGEM")" "$(jnum "$DISCO_TOTAL_MB")" "$(jnum "$DISCO_LIVRE_MB")" "$(jstr "$DISCO_TIPO")"
  printf '  "gpus": %s,\n' "$(gpus_json)"
  printf '  "acceleration": {\n'
  if [ -n "$NV_CUDA$NV_DRIVER" ]; then
    printf '    "cuda": {"available": true, "detail": %s, "version": %s},\n' "$(jstr "driver $NV_DRIVER; CUDA $NV_CUDA")" "$(jstr "$NV_CUDA")"
  else
    printf '    "cuda": {"available": false, "detail": null, "version": null},\n'
  fi
  printf '    "rocm": {"available": %s, "detail": %s, "version": null},\n' "$(jbool "$ROCM_OK")" "$(jstr "${ROCM_GFX:+arquiteturas: $ROCM_GFX}")"
  printf '    "directml": {"available": false, "detail": "somente Windows", "version": null},\n'
  printf '    "vulkan": {"available": %s, "api_version": %s, "devices": %s},\n' "$(jbool "$VK_OK")" "$(jstr "$VK_VER")" "$(vulkan_dispositivos_json)"
  printf '    "metal": {"available": %s, "detail": %s, "version": null},\n' "$(jbool "$METAL_OK")" "$(jstr "$METAL_TXT")"
  printf '    "openvino": {"available": %s, "candidate": %s, "version": %s}\n' "$(jbool "$OV_OK")" "$(jbool "$OV_CAND")" "$(jstr "$OV_VER")"
  printf '  },\n'
  printf '  "tools": {\n'
  # shellcheck disable=SC2086
  printf '    "python": {"installed": %s, "version": %s, "path": %s, "versions_available": %s},\n' \
    "$([ -n "$PY_CMD" ] && echo true || echo false)" "$(jstr "$PY_VER")" "$(jstr "$PY_CMD")" "$(jlista $PY_VERS)"
  printf '    "node": %s,\n' "$(ferramenta_json node)"
  printf '    "npm": %s,\n' "$(ferramenta_json npm)"
  printf '    "git": %s,\n' "$(ferramenta_json git)"
  # shellcheck disable=SC2086
  printf '    "ffmpeg": {"installed": %s, "version": %s, "path": %s, "encoders": %s},\n' \
    "$([ -n "$FF_PATH" ] && echo true || echo false)" "$(jstr "$FF_VER")" "$(jstr "$FF_PATH")" "$(jlista $FF_ENC)"
  printf '    "ollama": {"installed": %s, "version": %s, "path": %s, "server_active": %s, "host": "127.0.0.1:11434", "models": %s, "loaded": %s, "gpu_discovery": %s, "igpu_dropped": %s},\n' \
    "$([ -n "$OLL_PATH" ] && echo true || echo false)" "$(jstr "$OLL_VER")" "$(jstr "$OLL_PATH")" "$(jbool "$OLL_ATIVO")" \
    "$(ollama_modelos_json)" "$(ollama_carregados_json)" "$(ollama_gpus_json)" "$(jbool "$OLL_DROP")"
  printf '    "claude_code": {"installed": %s, "version": %s, "path": %s, "source": %s, "logged_in": %s, "auth_method": %s, "subscription": %s}\n' \
    "$([ -n "$CL_PATH" ] && echo true || echo false)" "$(jstr "$CL_VER")" "$(jstr "$CL_PATH")" "$(jstr "${CL_PATH:+$CL_ORIGEM}")" \
    "$(case "$CL_LOGADO" in true) echo true ;; false) echo false ;; *) echo null ;; esac)" "$(jstr "$CL_METODO")" "$(jstr "$CL_PLANO")"
  printf '  },\n'
  printf '  "fingerprint": %s,\n' "$(jstr "$FINGERPRINT")"
  printf '  "changed_since_last_run": false\n'
  printf '}\n'
}

mkdir -p "$(dirname "$SAIDA")"
emitir_json > "$SAIDA.tmp" && mv "$SAIDA.tmp" "$SAIDA"

msg "  Sistema : $SO_NOME ($ARCH)"
msg "  Máquina : ${SIS_FAB:-?} ${SIS_COM:-${SIS_MOD:-desconhecida}}$([ "$PORTATIL" = 1 ] && echo ' (notebook)')"
msg "  CPU     : $CPU_MODELO ($CPU_NUCLEOS núcleos, $CPU_THREADS threads)"
msg "  RAM     : $RAM_TOTAL_MB MB total, $RAM_LIVRE_MB MB livres"
msg "  GPUs    : $(printf '%s\n' "$GPUS_LINHAS" | awk -F'|' 'NF>1 && $2!=""{printf "%s%s", (n++ ? "; " : ""), $2}')"
msg "  Disco   : $((DISCO_LIVRE_MB / 1024)) GB livres em $DISCO_MONTAGEM"
msg "  Salvo em: $SAIDA"
rodar_perfil completo
msg "Concluído."
