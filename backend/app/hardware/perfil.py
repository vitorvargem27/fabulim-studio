"""Classificação de perfil de hardware do Fabulim Studio (briefing, seção 2.2).

Entrada: o dicionário de ``config/hardware.json``, coletado por ``scripts/diagnostico.ps1|.sh``.
Saída: perfil A/B/C/D com justificativa em português, avisos e o caminho de aceleração sugerido.

Só usa a biblioteca padrão, para rodar antes de qualquer instalação. Os limites abaixo são
referências (seção 2.2 do briefing): a decisão final vem do benchmark de calibração (2.4).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# --- Limites de referência -------------------------------------------------------------
# "16 GB" nominais aparecem como ~15,5 GB no sistema, por isso a folga nos números.
RAM_MIN_MB = 15_000
RAM_APERTADA_MB = 24_000
RAM_RESERVA_SO_MB = 8_192
DISCO_MIN_GB = 20
DISCO_CONFORTAVEL_GB = 100
VRAM_A_MB = 11_000  # placas de "12 GB" reportam ~11,9 a 12,3 GB
VRAM_B_MB = 7_000  # placas de "8 GB" reportam ~7,9 a 8,2 GB
APPLE_A_MB = 30_000  # "32 GB" de memória unificada
MEMORIA_IA_MIN_MB = 4_096

PERFIS: dict[str, str] = {
    "A": "Estação forte",
    "B": "GPU intermediária",
    "C": "Notebook ou GPU integrada",
    "D": "Abaixo do mínimo",
}

_FAMILIAS_SO = {"windows", "linux", "macos"}
_ARQUITETURAS = {"x64", "arm64"}
_TIPOS_GPU = {"integrated", "discrete", "unified"}


class HardwareInvalido(ValueError):
    """``hardware.json`` incompleto ou de versão incompatível."""

    def __init__(self, erros: list[str]) -> None:
        super().__init__("; ".join(erros))
        self.erros = erros


@dataclass(frozen=True)
class Classificacao:
    perfil: str
    nome: str
    justificativa: tuple[str, ...]
    avisos: tuple[str, ...]
    aceleracao: tuple[str, ...]
    gpu_principal: str | None
    memoria_ia_mb: int

    def para_dict(self) -> dict[str, Any]:
        return {
            "perfil": self.perfil,
            "nome": self.nome,
            "justificativa": list(self.justificativa),
            "avisos": list(self.avisos),
            "aceleracao": list(self.aceleracao),
            "gpu_principal": self.gpu_principal,
            "memoria_ia_mb": self.memoria_ia_mb,
        }


@dataclass(frozen=True)
class Pendencia:
    item: str
    estado: str
    acao: str


# --- Validação -------------------------------------------------------------------------
def obter(dados: Any, caminho: str, padrao: Any = None) -> Any:
    """Lê ``a.b.c`` de dicionários aninhados sem levantar erro."""
    atual = dados
    for parte in caminho.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return padrao
        atual = atual[parte]
    return atual


_get = obter


def _inteiro(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def validar_hardware(hw: Any) -> list[str]:
    """Devolve a lista de problemas encontrados (vazia se o dicionário serve)."""
    if not isinstance(hw, dict):
        return ["hardware.json deve ser um objeto JSON"]
    erros: list[str] = []
    if hw.get("schema_version") != SCHEMA_VERSION:
        erros.append(f"schema_version deve ser {SCHEMA_VERSION} (veio {hw.get('schema_version')!r})")
    if _get(hw, "os.family") not in _FAMILIAS_SO:
        erros.append(f"os.family deve ser um de {sorted(_FAMILIAS_SO)}")
    if _get(hw, "os.arch") not in _ARQUITETURAS:
        erros.append(f"os.arch deve ser um de {sorted(_ARQUITETURAS)}")
    if not isinstance(_get(hw, "cpu.model"), str):
        erros.append("cpu.model deve ser texto")
    if not _inteiro(_get(hw, "cpu.threads")):
        erros.append("cpu.threads deve ser inteiro")
    ram = _get(hw, "memory.ram_total_mb")
    if not _inteiro(ram) or ram <= 0:
        erros.append("memory.ram_total_mb deve ser inteiro positivo")
    livre = _get(hw, "disk.free_mb")
    if not _inteiro(livre) or livre < 0:
        erros.append("disk.free_mb deve ser inteiro não negativo")
    if not isinstance(_get(hw, "system.is_laptop"), bool):
        erros.append("system.is_laptop deve ser verdadeiro ou falso")
    gpus = hw.get("gpus")
    if not isinstance(gpus, list):
        erros.append("gpus deve ser uma lista (pode ser vazia)")
    else:
        for i, gpu in enumerate(gpus):
            if not isinstance(gpu, dict):
                erros.append(f"gpus[{i}] deve ser um objeto")
                continue
            if not isinstance(gpu.get("name"), str) or not isinstance(gpu.get("vendor"), str):
                erros.append(f"gpus[{i}] precisa de vendor e name em texto")
            if gpu.get("kind") is not None and gpu.get("kind") not in _TIPOS_GPU:
                erros.append(f"gpus[{i}].kind deve ser nulo (inferir) ou um de {sorted(_TIPOS_GPU)}")
            for campo in ("dedicated_mb", "shared_mb"):
                valor = gpu.get(campo)
                if valor is not None and (not _inteiro(valor) or valor < 0):
                    erros.append(f"gpus[{i}].{campo} deve ser inteiro não negativo ou nulo")
    return erros


# --- Normalização: o que os coletores deixam para Python inferir ----------------------------
_INTEL_DEDICADA = re.compile(r"\bArc(?:\(TM\))?\s+(?:Pro\s+)?[AB]\d{2,3}", re.IGNORECASE)
_AMD_INTEGRADA = re.compile(
    r"Radeon(?:\(TM\))?\s+(?:Graphics|\d{3}M|8\d{2}M|Vega)|Vega\s*\d+\s*Graphics|Ryzen", re.IGNORECASE
)
_AMD_DEDICADA = re.compile(r"\bRX\b|\bPro\s+W|\bVII\b|Instinct|\bR[579]\s", re.IGNORECASE)

# Arquitetura gfx estimada pelo nome da placa (o Windows não a expõe sem o HIP SDK).
_GFX_AMD: tuple[tuple[str, str], ...] = (
    (r"RX\s*9070", "gfx1201"),
    (r"RX\s*9060", "gfx1200"),
    (r"RX\s*7900", "gfx1100"),
    (r"RX\s*7[78]00", "gfx1101"),
    (r"RX\s*7600", "gfx1102"),
    (r"RX\s*6[89]\d0", "gfx1030"),
    (r"RX\s*67[05]0", "gfx1031"),
    (r"RX\s*66[05]0", "gfx1032"),
    (r"RX\s*6[45]\d0", "gfx1034"),
    (r"RX\s*5[67]00", "gfx1010"),
    (r"RX\s*[45][78]0\b", "gfx803"),
    (r"Radeon VII", "gfx906"),
    (r"Vega\s*(?:56|64)", "gfx900"),
    (r"\b890M", "gfx1150"),
    (r"\b80[56]0S|Ryzen AI Max", "gfx1151"),
    (r"\b7[468]0M", "gfx1103"),
    (r"\b6[68]0M", "gfx1035"),
)


def estimar_gfx_amd(nome: str) -> str | None:
    """Identificador de arquitetura (gfxNNNN) estimado pelo nome, ou ``None`` se não conhecido."""
    for padrao, gfx in _GFX_AMD:
        if re.search(padrao, nome, re.IGNORECASE):
            return gfx
    return None


def inferir_tipo_gpu(vendor: str | None, nome: str, dedicada_mb: int | None) -> str:
    """``integrated``, ``discrete`` ou ``unified`` a partir de fabricante e nome."""
    v = (vendor or "").lower()
    if v == "apple":
        return "unified"
    if v == "nvidia":
        return "discrete"
    if v == "intel":
        return "discrete" if _INTEL_DEDICADA.search(nome) else "integrated"
    if v == "amd":
        if _AMD_INTEGRADA.search(nome):
            return "integrated"
        if _AMD_DEDICADA.search(nome):
            return "discrete"
    return "discrete" if (dedicada_mb or 0) >= 2048 else "integrated"


def normalizar_hardware(hw: dict[str, Any]) -> dict[str, Any]:
    """Cópia de ``hw`` com ``kind`` e ``gfx_arch`` preenchidos onde o coletor deixou nulo."""
    copia = copy.deepcopy(hw)
    for gpu in copia.get("gpus", []):
        if gpu.get("kind") is None:
            gpu["kind"] = inferir_tipo_gpu(gpu.get("vendor"), gpu.get("name", ""), gpu.get("dedicated_mb"))
        if gpu.get("vendor") == "amd" and not gpu.get("gfx_arch"):
            gfx = estimar_gfx_amd(gpu.get("name", ""))
            if gfx:
                gpu["gfx_arch"] = gfx
                gpu["gfx_arch_source"] = "tabela por nome (estimado)"
    return copia


# --- Utilidades de texto ---------------------------------------------------------------
def fmt_gb(mb: float, casas: int = 1) -> str:
    """Formata MB como GB com vírgula decimal (padrão pt-BR)."""
    return f"{mb / 1024:.{casas}f}".replace(".", ",") + " GB"


def _disponivel(hw: dict[str, Any], caminho: str) -> bool:
    return bool(_get(hw, f"acceleration.{caminho}.available", False))


# --- GPU principal ---------------------------------------------------------------------
def _gpu_principal(gpus: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not gpus:
        return None
    dedicadas = [g for g in gpus if g["kind"] in ("discrete", "unified")]
    if dedicadas:
        return max(dedicadas, key=lambda g: g.get("dedicated_mb") or 0)
    return gpus[0]


def _descrever_gpu(gpu: dict[str, Any]) -> str:
    nome = gpu["name"]
    if gpu["kind"] == "unified":
        return f"{nome} (memória unificada com a RAM)"
    if gpu["kind"] == "integrated":
        dedicada = gpu.get("dedicated_mb")
        compartilhada = gpu.get("shared_mb")
        partes = []
        if dedicada is not None:
            partes.append(f"{dedicada} MB dedicados")
        if compartilhada is not None:
            partes.append(f"{compartilhada} MB compartilhados com a RAM")
        detalhe = "; ".join(partes) if partes else "memória compartilhada com a RAM"
        return f"{nome} (integrada: {detalhe})"
    vram = gpu.get("dedicated_mb")
    return f"{nome} (dedicada, {fmt_gb(vram)} de VRAM)" if vram else f"{nome} (dedicada)"


# --- Decisão do perfil -----------------------------------------------------------------
def _decidir(
    hw: dict[str, Any], gpu: dict[str, Any] | None, ram_mb: int, livre_gb: float
) -> tuple[str, list[str], list[str]]:
    """Devolve (perfil, justificativas, avisos)."""
    justificativa: list[str] = []
    avisos: list[str] = []

    # Perfil D: abaixo do mínimo, independentemente da GPU.
    motivos_d = []
    if ram_mb < RAM_MIN_MB:
        motivos_d.append(f"RAM de {fmt_gb(ram_mb)} está abaixo do mínimo de 16 GB para rodar modelos de IA")
    if livre_gb < DISCO_MIN_GB:
        motivos_d.append(f"só {fmt_gb(livre_gb * 1024)} livres no disco do projeto (mínimo de {DISCO_MIN_GB} GB)")
    if motivos_d:
        return "D", [*motivos_d, "gerações pesadas ficam desativadas; planejamento e roteiros continuam"], avisos

    familia = _get(hw, "os.family")
    arch = _get(hw, "os.arch")
    justificativa.append(f"RAM de {fmt_gb(ram_mb)} (mínimo de 16 GB atendido)")
    justificativa.append(f"{fmt_gb(livre_gb * 1024)} livres no disco do projeto")

    if familia == "macos" and arch == "arm64":
        justificativa.append(f"Apple Silicon com {fmt_gb(ram_mb, 0)} de memória unificada (Metal/MPS)")
        if ram_mb >= APPLE_A_MB:
            return "A", justificativa, avisos
        return "B", justificativa, avisos

    if gpu is None:
        justificativa.append("nenhuma GPU utilizável detectada: tudo roda na CPU")
        return "C", justificativa, avisos

    vendor = gpu["vendor"]
    vram = gpu.get("dedicated_mb") or 0
    justificativa.append(f"GPU: {_descrever_gpu(gpu)}")

    if gpu["kind"] == "discrete":
        if vendor == "nvidia":
            if not _disponivel(hw, "cuda"):
                avisos.append(
                    "GPU NVIDIA detectada, mas CUDA não respondeu: verifique o driver (instalar ou "
                    "atualizar driver exige a sua autorização)"
                )
            if vram >= VRAM_A_MB:
                justificativa.append("NVIDIA com 12 GB ou mais de VRAM")
                return "A", justificativa, avisos
            if vram >= VRAM_B_MB:
                justificativa.append("NVIDIA com 8 a 12 GB de VRAM")
                return "B", justificativa, avisos
            avisos.append("GPU dedicada com menos de 8 GB de VRAM: começa como perfil C; o benchmark pode promover")
            justificativa.append("VRAM abaixo de 8 GB")
            return "C", justificativa, avisos
        if vendor in ("amd", "intel"):
            caminho_ok = _disponivel(hw, "vulkan") or _disponivel(hw, "rocm") or _disponivel(hw, "directml")
            if vram >= VRAM_B_MB and caminho_ok:
                justificativa.append(
                    f"{vendor.upper()} dedicada com 8 GB ou mais de VRAM e caminho de aceleração disponível"
                )
                if vram >= VRAM_A_MB * 4 // 3:
                    avisos.append("VRAM alta em GPU não NVIDIA: candidata ao perfil A, mas só o benchmark confirma")
                return "B", justificativa, avisos
            if vram >= VRAM_B_MB:
                justificativa.append("nenhum caminho de aceleração (Vulkan, ROCm ou DirectML) respondeu")
            else:
                justificativa.append("VRAM abaixo de 8 GB")
            return "C", justificativa, avisos

    # Integrada, NPU ou só CPU.
    justificativa.append("sem VRAM dedicada: modelos usam a CPU e a memória compartilhada")
    return "C", justificativa, avisos


# --- Caminho de aceleração sugerido ------------------------------------------------------
def _caminho_aceleracao(hw: dict[str, Any], gpu: dict[str, Any] | None) -> list[str]:
    cpu_txt = "CPU"
    if _get(hw, "cpu.features.avx512"):
        cpu_txt = "CPU com AVX-512"
    elif _get(hw, "cpu.features.avx2"):
        cpu_txt = "CPU com AVX2"

    if _get(hw, "os.family") == "macos" and _get(hw, "os.arch") == "arm64":
        return [
            "Metal/MPS: PyTorch com MPS, llama.cpp e stable-diffusion.cpp com Metal",
            f"{cpu_txt}: alternativa para modelos quantizados pequenos",
        ]
    if gpu is None:
        return [f"{cpu_txt}: llama.cpp e stable-diffusion.cpp com modelos quantizados (tempos informados)"]

    vendor = gpu["vendor"]
    if gpu["kind"] == "discrete" and vendor == "nvidia":
        return [
            "CUDA: PyTorch oficial, llama.cpp/Ollama e stable-diffusion.cpp com CUDA",
            "Vulkan: alternativa se o CUDA não responder",
        ]
    if gpu["kind"] == "discrete" and vendor == "amd":
        gfx = gpu.get("gfx_arch")
        nota = (
            f" (arquitetura {gfx}: conferir a lista oficial de suporte do ROCm; no Linux o caminho "
            "comunitário usual é HSA_OVERRIDE_GFX_VERSION, no Windows Vulkan e DirectML são os estáveis)"
            if gfx
            else ""
        )
        return [
            "Vulkan: llama.cpp/Ollama e stable-diffusion.cpp (caminho mais portátil)",
            f"ROCm/HIP: onde a arquitetura for suportada{nota}",
            "DirectML (Windows): ONNX Runtime para modelos ONNX",
        ]
    if vendor == "intel":
        return [
            f"{cpu_txt}: linha de base confiável para llama.cpp e stable-diffusion.cpp",
            "Vulkan na GPU integrada: medir, pode não ganhar da CPU (memória compartilhada)",
            "OpenVINO (CPU, GPU integrada, NPU): candidato para imagem e transcrição",
            "DirectML (Windows): ONNX Runtime para segmentação e TTS em ONNX",
        ]
    return [
        f"{cpu_txt}: linha de base",
        "Vulkan: llama.cpp/Ollama e stable-diffusion.cpp, quando o driver expõe",
        "DirectML (Windows): ONNX Runtime para modelos ONNX",
    ]


def _memoria_ia_mb(perfil: str, hw: dict[str, Any], gpu: dict[str, Any] | None) -> int:
    ram: int = _get(hw, "memory.ram_total_mb", 0)
    if gpu is not None and gpu["kind"] == "unified":
        return int(ram * 0.75)
    if perfil in ("A", "B") and gpu is not None and gpu.get("dedicated_mb"):
        return int(gpu["dedicated_mb"])
    return max(MEMORIA_IA_MIN_MB, ram - RAM_RESERVA_SO_MB)


# --- Avisos gerais -----------------------------------------------------------------------
def _avisos_gerais(hw: dict[str, Any], perfil: str, livre_gb: float, ram_mb: int) -> list[str]:
    avisos: list[str] = []
    if _get(hw, "system.is_laptop"):
        if _get(hw, "system.battery.on_ac") is False:
            avisos.append("Notebook na bateria: jobs pesados devem esperar a tomada (opção 'só na tomada')")
        plano = str(_get(hw, "system.power_plan") or "")
        if re.search(r"(economia|saver|low-power)", plano, re.IGNORECASE):
            avisos.append(f"Plano de energia '{plano}' reduz o desempenho: use Equilibrado ou Alto desempenho")
    if perfil != "D" and livre_gb < DISCO_CONFORTAVEL_GB:
        avisos.append(
            f"Espaço apertado ({fmt_gb(livre_gb * 1024)} livres): modelos e vídeos exportados enchem "
            "rápido; convém apontar a pasta de dados para outro disco"
        )
    if perfil == "C" and ram_mb < RAM_APERTADA_MB:
        avisos.append("Com menos de 24 GB de RAM, modelos maiores que ~8B ficam inviáveis")
    return avisos


def classificar(hw: dict[str, Any]) -> Classificacao:
    """Classifica a máquina em um perfil (A, B, C ou D), com justificativa."""
    erros = validar_hardware(hw)
    if erros:
        raise HardwareInvalido(erros)
    hw = normalizar_hardware(hw)

    ram_mb: int = hw["memory"]["ram_total_mb"]
    livre_gb = hw["disk"]["free_mb"] / 1024
    gpu = _gpu_principal(hw["gpus"])

    perfil, justificativa, avisos = _decidir(hw, gpu, ram_mb, livre_gb)
    avisos = [*avisos, *_avisos_gerais(hw, perfil, livre_gb, ram_mb)]

    if _get(hw, "system.is_laptop"):
        justificativa.append("Notebook: bateria e temperatura entram na gestão de jobs pesados")

    return Classificacao(
        perfil=perfil,
        nome=PERFIS[perfil],
        justificativa=tuple(justificativa),
        avisos=tuple(avisos),
        aceleracao=tuple(_caminho_aceleracao(hw, gpu)),
        gpu_principal=gpu["name"] if gpu else None,
        memoria_ia_mb=_memoria_ia_mb(perfil, hw, gpu),
    )


# --- Ferramentas pendentes -------------------------------------------------------------
def _versao_tupla(texto: str | None) -> tuple[int, ...]:
    if not texto:
        return ()
    numeros = re.findall(r"\d+", texto)[:3]
    return tuple(int(n) for n in numeros)


def python_do_projeto(raiz: Path) -> tuple[int, int] | None:
    """Versão do Python do ambiente virtual do projeto (`.venv`), se ele existe: é com esse que o app roda."""
    try:
        linhas = (raiz / ".venv" / "pyvenv.cfg").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for linha in linhas:
        chave, _, valor = linha.partition("=")
        if chave.strip() == "version":
            numeros = re.findall(r"\d+", valor)[:2]
            if len(numeros) == 2:
                return int(numeros[0]), int(numeros[1])
    return None


def ferramentas_pendentes(hw: dict[str, Any], python_do_app: tuple[int, int] | None = None) -> list[Pendencia]:
    """O que falta (ou merece atenção) no ambiente, sem instalar nada.

    ``python_do_app`` é a versão do Python em que o próprio app está rodando (quando quem pergunta é o app): se ela já
    é a recomendada, o Python padrão do sistema deixa de ser um problema. Sem ela (relatório feito só do JSON), vale o
    Python padrão registrado na coleta.
    """
    p: list[Pendencia] = []
    tools = hw.get("tools") or {}

    py = tools.get("python") or {}
    if python_do_app is not None and (3, 10) <= python_do_app < (3, 14):
        pass  # o app já roda no Python recomendado (o do ambiente virtual do projeto)
    elif not py.get("installed"):
        p.append(Pendencia("Python", "ausente", "Instalar Python 3.12 (é o runtime do backend)"))
    else:
        versao = _versao_tupla(py.get("version"))
        disponiveis = [v for v in (py.get("versions_available") or []) if str(v).startswith(("3.12", "3.13"))]
        if versao and versao < (3, 10):
            p.append(Pendencia("Python", f"{py.get('version')} (antigo)", "Usar Python 3.12 ou mais novo"))
        elif versao >= (3, 14) and disponiveis:
            p.append(
                Pendencia(
                    "Python",
                    f"padrão {py.get('version')}",
                    f"Criar o ambiente virtual do projeto com {disponiveis[0]} (mais compatível com pacotes de IA)",
                )
            )

    node = tools.get("node") or {}
    if not node.get("installed"):
        p.append(Pendencia("Node.js", "ausente", "Instalar Node.js LTS (só para compilar e testar a interface)"))
    elif _versao_tupla(node.get("version")) < (20,):
        p.append(Pendencia("Node.js", f"{node.get('version')} (antigo)", "Atualizar para Node.js 22 LTS"))

    if not (tools.get("git") or {}).get("installed"):
        p.append(Pendencia("git", "ausente", "Instalar git"))

    if not (tools.get("ffmpeg") or {}).get("installed"):
        p.append(
            Pendencia(
                "ffmpeg",
                "ausente",
                "Abra «Modelos» e instale o ffmpeg (fica dentro da pasta do projeto)",
            )
        )

    ollama = tools.get("ollama") or {}
    if not ollama.get("installed"):
        p.append(Pendencia("Ollama", "ausente", "Opcional: runtime de LLM local preferido"))
    else:
        if not ollama.get("server_active"):
            p.append(Pendencia("Ollama", "servidor parado", "O app sobe o servidor ao iniciar"))

    claude = tools.get("claude_code") or {}
    if not claude.get("installed"):
        p.append(Pendencia("Claude Code", "ausente", "Opcional: reforço de texto e visão (seção 15)"))
    elif claude.get("logged_in") is False:
        p.append(Pendencia("Claude Code", "sem login", "Fazer login pelo fluxo oficial (`claude auth login`)"))
    return p
