"""Relatório legível do ambiente (``docs/AMBIENTE.md``), gerado a partir de ``config/hardware.json``."""

from __future__ import annotations

import re
from typing import Any

from .perfil import Classificacao, ferramentas_pendentes, fmt_gb, normalizar_hardware, obter

_HOME_WINDOWS = re.compile(r"(?i)^[a-z]:\\users\\[^\\]+")
_HOME_UNIX = re.compile(r"^/(?:home|Users)/[^/]+")

_MODOS = {"full": "completo", "light": "leve"}

_ACELERACOES: tuple[tuple[str, str], ...] = (
    ("cuda", "CUDA (NVIDIA)"),
    ("rocm", "ROCm/HIP (AMD)"),
    ("directml", "DirectML (Windows)"),
    ("vulkan", "Vulkan"),
    ("metal", "Metal/MPS (Apple)"),
    ("openvino", "OpenVINO (Intel)"),
)


def _anonimizar(caminho: Any) -> str:
    """Troca a pasta pessoal por um marcador, para o relatório poder ir ao git."""
    if not caminho:
        return "-"
    texto = _HOME_WINDOWS.sub("%USERPROFILE%", str(caminho))
    return _HOME_UNIX.sub("~", texto)


def _celula(valor: Any) -> str:
    if valor is None or valor == "":
        return "-"
    return str(valor).replace("|", "\\|").replace("\n", " ")


def _sim_nao(valor: Any) -> str:
    return "sim" if valor else "não"


def _tabela(cabecalho: list[str], linhas: list[list[Any]]) -> list[str]:
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join(" --- " for _ in cabecalho) + "|"]
    saida += ["| " + " | ".join(_celula(c) for c in linha) + " |" for linha in linhas]
    return saida


def _nome_maquina(hw: dict[str, Any]) -> str:
    fabricante = obter(hw, "system.vendor") or ""
    comercial = obter(hw, "system.marketing_name")
    modelo = obter(hw, "system.model") or "máquina desconhecida"
    if comercial:
        return f"{fabricante} {comercial}".strip()
    return f"{fabricante} {modelo}".strip()


def _gpus_linhas(hw: dict[str, Any]) -> list[list[Any]]:
    tipos = {"integrated": "integrada", "discrete": "dedicada", "unified": "unificada"}
    linhas = []
    for g in hw.get("gpus", []):
        dedicada = g.get("dedicated_mb")
        compartilhada = g.get("shared_mb")
        linhas.append(
            [
                g.get("name"),
                tipos.get(g.get("kind"), g.get("kind")),
                f"{dedicada} MB" if dedicada is not None else "-",
                f"{compartilhada} MB" if compartilhada is not None else "-",
                g.get("driver"),
                g.get("gfx_arch"),
            ]
        )
    return linhas


def _aceleracao_linhas(hw: dict[str, Any]) -> list[list[Any]]:
    linhas = []
    for chave, rotulo in _ACELERACOES:
        info = obter(hw, f"acceleration.{chave}", {}) or {}
        if chave == "vulkan":
            dispositivos = ", ".join(d.get("name", "?") for d in info.get("devices", []))
            detalhe = f"API {info.get('api_version') or '?'}; {dispositivos}" if info.get("available") else None
        elif chave == "openvino":
            detalhe = (
                f"instalado ({info.get('version')})"
                if info.get("available")
                else ("candidato (GPU/CPU Intel presente), não instalado" if info.get("candidate") else None)
            )
        else:
            detalhe = info.get("detail") or info.get("version")
        linhas.append([rotulo, _sim_nao(info.get("available")), detalhe])
    return linhas


def _ferramentas_linhas(hw: dict[str, Any]) -> list[list[Any]]:
    tools = hw.get("tools") or {}
    nomes = (
        ("python", "Python"),
        ("node", "Node.js"),
        ("npm", "npm"),
        ("git", "git"),
        ("ffmpeg", "ffmpeg"),
        ("ollama", "Ollama"),
        ("claude_code", "Claude Code"),
    )
    linhas = []
    for chave, rotulo in nomes:
        t = tools.get(chave) or {}
        obs: str | None = None
        if chave == "python" and t.get("versions_available"):
            obs = "versões pelo launcher: " + ", ".join(str(v) for v in t["versions_available"])
        elif chave == "claude_code" and t.get("installed"):
            login = t.get("logged_in")
            if login is True:
                obs = f"logado ({t.get('auth_method') or '?'}, plano {t.get('subscription') or '?'})"
            elif login is False:
                obs = "sem login"
            else:
                obs = "login não verificado"
            if t.get("source") == "app":
                obs += "; embutido no app Claude, fora do PATH"
        elif chave == "ollama" and t.get("installed"):
            obs = "servidor ativo" if t.get("server_active") else "servidor parado"
        linhas.append(
            [
                rotulo,
                "instalado" if t.get("installed") else "ausente",
                t.get("version"),
                obs or _anonimizar(t.get("path")),
            ]
        )
    return linhas


def renderizar_ambiente(hw: dict[str, Any], c: Classificacao, python_do_app: tuple[int, int] | None = None) -> str:
    """Monta o Markdown de ``docs/AMBIENTE.md``."""
    hw = normalizar_hardware(hw)
    cpu = hw["cpu"]
    recursos = [
        nome
        for nome, chave in (("AVX", "avx"), ("AVX2", "avx2"), ("AVX-512", "avx512"))
        if obter(hw, f"cpu.features.{chave}")
    ]
    npu = obter(hw, "cpu.npu.name") if obter(hw, "cpu.npu.present") else None
    bateria = obter(hw, "system.battery", {}) or {}
    disco = hw["disk"]

    linhas: list[str] = [
        f"# Ambiente: {_nome_maquina(hw)}",
        "",
        f"> Gerado por `scripts/diagnostico` em {hw.get('collected_at', '?')} "
        f"(modo {_MODOS.get(str(hw.get('mode')), hw.get('mode', '?'))}). Não edite à mão: rode o diagnóstico de novo.",
        "",
        "## Resumo",
        "",
    ]
    linhas += _tabela(
        ["Item", "Valor"],
        [
            ["Perfil", f"**{c.perfil}: {c.nome}**"],
            [
                "Máquina",
                f"{_nome_maquina(hw)} ({obter(hw, 'system.model') or '?'})"
                + (", notebook" if obter(hw, "system.is_laptop") else ", desktop"),
            ],
            ["Sistema", f"{obter(hw, 'os.name')} {obter(hw, 'os.version')} ({obter(hw, 'os.arch')})"],
            [
                "CPU",
                f"{cpu.get('model')}: {cpu.get('cores')} núcleos, {cpu.get('threads')} threads"
                + (f"; {', '.join(recursos)}" if recursos else ""),
            ],
            ["NPU", npu or "nenhuma"],
            [
                "RAM",
                f"{fmt_gb(hw['memory']['ram_total_mb'])} total; {fmt_gb(obter(hw, 'memory.ram_free_mb') or 0)} livres na coleta",
            ],
            ["GPU principal", c.gpu_principal or "nenhuma"],
            [
                "Disco do projeto",
                f"{fmt_gb(disco['free_mb'])} livres de {fmt_gb(disco.get('total_mb') or 0)} em {disco.get('drive') or '?'} ({disco.get('kind') or 'tipo desconhecido'})",
            ],
            [
                "Energia",
                (
                    f"bateria {bateria.get('percent')}% ({'na tomada' if bateria.get('on_ac') else 'na bateria'}); "
                    if bateria.get("present")
                    else "sem bateria; "
                )
                + f"plano {obter(hw, 'system.power_plan') or '?'}",
            ],
        ],
    )

    linhas += ["", f"## Perfil {c.perfil}: {c.nome}", "", "Por quê:", ""]
    linhas += [f"- {j}" for j in c.justificativa]
    linhas += [
        "",
        f"Orçamento de memória para modelos (estimado): **{fmt_gb(c.memoria_ia_mb)}**. "
        "É o teto para escolher o tamanho dos modelos; o benchmark de calibração (seção 2.4 do briefing) "
        "confirma ou corrige o perfil.",
        "",
        "## Avisos",
        "",
    ]
    linhas += [f"- {a}" for a in c.avisos] or ["Nenhum."]

    linhas += ["", "## GPU", ""]
    linhas += (
        _tabela(["GPU", "Tipo", "Dedicada", "Compartilhada", "Driver", "Arquitetura AMD"], _gpus_linhas(hw))
        if hw.get("gpus")
        else ["Nenhuma GPU detectada."]
    )

    linhas += ["", "## Aceleração disponível", ""]
    linhas += _tabela(["Caminho", "Disponível", "Detalhe"], _aceleracao_linhas(hw))
    linhas += ["", "Caminho recomendado, em ordem de tentativa:", ""]
    linhas += [f"{i}. {a}" for i, a in enumerate(c.aceleracao, start=1)]

    linhas += ["", "## Ferramentas", ""]
    linhas += _tabela(["Ferramenta", "Estado", "Versão", "Observação"], _ferramentas_linhas(hw))

    ollama = obter(hw, "tools.ollama", {}) or {}
    if ollama.get("installed"):
        linhas += ["", "### Ollama e GPU", ""]
        modelos = ollama.get("models") or []
        if modelos:
            linhas += [
                "Modelos instalados: "
                + ", ".join(f"`{m.get('name')}` ({fmt_gb(m.get('size_mb', 0))})" for m in modelos),
                "",
            ]
        for d in ollama.get("gpu_discovery") or []:
            if str(d.get("library")).lower() == "cpu":
                linhas.append("- CPU: sempre disponível (usada quando nenhuma GPU é aceita)")
                continue
            estado = "descartada por ser integrada" if d.get("dropped_integrated") else "em uso"
            linhas.append(f"- {d.get('library')}: {d.get('name')}: {estado}")
        for m in ollama.get("loaded") or []:
            processador = "GPU" if (m.get("size_vram_mb") or 0) > 0 else "CPU"
            linhas.append(f"- Carregado agora: `{m.get('name')}` na {processador}")

    linhas += ["", "## Pendências", ""]
    pendencias = ferramentas_pendentes(hw, python_do_app)
    if pendencias:
        linhas += _tabela(["Item", "Estado", "O que fazer"], [[p.item, p.estado, p.acao] for p in pendencias])
    else:
        linhas.append("Nenhuma.")

    linhas += [
        "",
        "## Como atualizar",
        "",
        "```powershell",
        "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\diagnostico.ps1",
        "```",
        "",
        "No Linux e no macOS: `bash scripts/diagnostico.sh`. O modo leve (`-Leve` ou `--leve`) roda a cada "
        "inicialização e avisa se a máquina mudou.",
        "",
    ]
    return "\n".join(linhas)
