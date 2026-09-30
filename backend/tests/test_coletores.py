"""Coletores de hardware (scripts/diagnostico.ps1 e .sh).

Rápidos (rodam sempre): sintaxe, codificação e fim de linha.
Hardware real (marcador ``hw``, fora da execução normal; rode ``pytest -m hw`` ou ``testar --hw``): executam o coletor
nesta máquina, validam o JSON e o modo leve.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

from app.hardware import classificar, validar_hardware

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = RAIZ / "scripts"
PS1 = SCRIPTS / "diagnostico.ps1"
SH = SCRIPTS / "diagnostico.sh"
ES_WINDOWS = sys.platform == "win32"


def achar_bash() -> str | None:
    """bash utilizável: no Windows ignora o launcher do WSL (System32) e prefere o do Git."""
    if ES_WINDOWS:
        candidatos = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Git" / "bin" / "bash.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Git" / "bin" / "bash.exe",
        ]
        for c in candidatos:
            if c.exists():
                return str(c)
        return None
    return shutil.which("bash")


class TestSintaxeDosColetores(unittest.TestCase):
    @unittest.skipUnless(ES_WINDOWS, "o parser do PowerShell só é validado no Windows")
    def test_ps1_sintaxe_valida(self) -> None:
        comando = (
            "$e = $null; $t = $null; "
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{PS1}', [ref]$t, [ref]$e); "
            "if ($e.Count) { $e | ForEach-Object { 'linha ' + $_.Extent.StartLineNumber + ': ' + $_.Message }; exit 1 }"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", comando], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_ps1_tem_bom_utf8(self) -> None:
        # Sem BOM o Windows PowerShell 5.1 lê os acentos como ANSI e a saída sai corrompida.
        self.assertEqual(PS1.read_bytes()[:3], b"\xef\xbb\xbf")

    def test_ps1_nao_tem_caracteres_de_controle(self) -> None:
        # Uma barra invertida mal escapada num script gerador já virou \f e \b dentro de um caminho.
        ruins = sorted({b for b in PS1.read_bytes() if b < 32 and b not in (9, 10, 13)})
        self.assertEqual(ruins, [], "caractere de controle dentro de diagnostico.ps1")

    def test_coletores_procuram_o_ffmpeg_instalado_no_projeto(self) -> None:
        # O instalador da tela Modelos põe o ffmpeg em tools/ffmpeg/bin (fora do PATH): o coletor precisa achá-lo.
        self.assertIn(rb"tools\ffmpeg\bin\ffmpeg.exe", PS1.read_bytes())
        self.assertIn(b'"$RAIZ/tools/ffmpeg/bin/ffmpeg"', SH.read_bytes())

    def test_ps1_modo_leve_refaz_a_deteccao_do_ffmpeg(self) -> None:
        # No modo leve o app roda o coletor depois de instalar: reaproveitar o valor antigo esconderia o ffmpeg novo.
        self.assertNotIn(b"ffmpeg = $anterior.tools.ffmpeg", PS1.read_bytes())

    def test_sh_termina_linhas_com_lf(self) -> None:
        self.assertNotIn(b"\r", SH.read_bytes())

    def test_sh_tem_shebang(self) -> None:
        self.assertTrue(SH.read_bytes().startswith(b"#!/usr/bin/env bash\n"))

    def test_sh_sintaxe_valida(self) -> None:
        bash = achar_bash()
        if not bash:
            self.skipTest("bash não encontrado")
        r = subprocess.run([bash, "-n", "scripts/diagnostico.sh"], cwd=RAIZ, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_sh_ajuda_e_opcao_invalida(self) -> None:
        bash = achar_bash()
        if not bash:
            self.skipTest("bash não encontrado")
        ajuda = subprocess.run(
            [bash, "scripts/diagnostico.sh", "--ajuda"], cwd=RAIZ, capture_output=True, text=True, timeout=60
        )
        self.assertEqual(ajuda.returncode, 0)
        self.assertIn("Uso:", ajuda.stdout)
        ruim = subprocess.run(
            [bash, "scripts/diagnostico.sh", "--nao-existe"], cwd=RAIZ, capture_output=True, text=True, timeout=60
        )
        self.assertEqual(ruim.returncode, 2)


@pytest.mark.hw
class TestColetorNaMaquinaReal(unittest.TestCase):
    """Roda o coletor de verdade (o completo leva ~1 min no Windows por causa do dxdiag)."""

    def _comando(self, saida: Path, docs: Path, leve: bool) -> list[str]:
        if ES_WINDOWS:
            cmd = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1),
                "-Saida",
                str(saida),
                "-Docs",
                str(docs),
                "-Silencioso",
            ]
            return cmd + (["-Leve"] if leve else [])
        bash = achar_bash()
        if not bash:
            self.skipTest("bash não encontrado")
        cmd = [bash, str(SH), "--saida", str(saida), "--docs", str(docs), "--silencioso"]
        return cmd + (["--leve"] if leve else [])

    def test_coleta_completa_depois_leve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saida = Path(tmp) / "hardware.json"
            docs = Path(tmp) / "AMBIENTE.md"

            r = subprocess.run(self._comando(saida, docs, leve=False), capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            dados = json.loads(saida.read_text(encoding="utf-8-sig"))
            self.assertEqual(validar_hardware(dados), [], "hardware.json fora do contrato")
            self.assertEqual(dados["mode"], "full")
            self.assertGreater(dados["memory"]["ram_total_mb"], 1_000)
            self.assertGreaterEqual(dados["cpu"]["threads"], 1)
            self.assertGreater(dados["disk"]["free_mb"], 0)
            self.assertIn(classificar(dados).perfil, "ABCD")
            self.assertTrue(docs.exists(), "o perfil deveria ter gerado o AMBIENTE.md")
            self.assertIn("# Ambiente:", docs.read_text(encoding="utf-8"))

            r2 = subprocess.run(self._comando(saida, docs, leve=True), capture_output=True, text=True, timeout=300)
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            leve = json.loads(saida.read_text(encoding="utf-8-sig"))
            self.assertEqual(validar_hardware(leve), [])
            self.assertEqual(
                leve["fingerprint"], dados["fingerprint"], "a impressão digital não pode mudar entre coletas"
            )
            self.assertFalse(leve["changed_since_last_run"])

            # o ffmpeg que a tela Modelos instala em tools/ (fora do PATH) precisa aparecer nas duas coletas
            ffmpeg = RAIZ / "tools" / "ffmpeg" / "bin" / ("ffmpeg.exe" if ES_WINDOWS else "ffmpeg")
            if ffmpeg.exists():
                for coleta in (dados, leve):
                    self.assertTrue(coleta["tools"]["ffmpeg"]["installed"], coleta["mode"])
                    self.assertEqual(Path(coleta["tools"]["ffmpeg"]["path"]).resolve(), ffmpeg.resolve())


if __name__ == "__main__":
    unittest.main()
