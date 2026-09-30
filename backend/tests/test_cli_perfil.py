"""CLI scripts/perfil.py: códigos de saída, arquivos gerados e mensagens de erro."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

from .builders import carregar_thinkpad, hw

RAIZ = Path(__file__).resolve().parents[2]


def _carregar_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fabulim_perfil_cli", RAIZ / "scripts" / "perfil.py")
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TestCliPerfil(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cli = _carregar_cli()

    def _rodar(self, *args: str) -> tuple[int, str, str]:
        saida, erro = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = self.cli.main(list(args))
        return codigo, saida.getvalue(), erro.getvalue()

    def test_gera_relatorio_e_imprime_o_perfil(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entrada = Path(tmp) / "hardware.json"
            docs = Path(tmp) / "docs" / "AMBIENTE.md"
            entrada.write_text(json.dumps(carregar_thinkpad()), encoding="utf-8")
            codigo, saida, _ = self._rodar("--hardware", str(entrada), "--docs", str(docs))
            self.assertEqual(codigo, 0)
            self.assertIn("Perfil C: Notebook ou GPU integrada", saida)
            self.assertIn("Pendências do ambiente", saida)
            texto = docs.read_text(encoding="utf-8")
            self.assertTrue(texto.startswith("# Ambiente: LENOVO ThinkPad T14 Gen 2i"))
            self.assertNotIn("\r", texto)  # LF, mesmo no Windows

    def test_aceita_json_com_bom(self) -> None:
        # O PowerShell 5.1 pode gravar UTF-8 com BOM; o classificador precisa aceitar.
        with tempfile.TemporaryDirectory() as tmp:
            entrada = Path(tmp) / "hardware.json"
            entrada.write_bytes(b"\xef\xbb\xbf" + json.dumps(carregar_thinkpad()).encode("utf-8"))
            codigo, _, _ = self._rodar("--hardware", str(entrada), "--sem-docs")
            self.assertEqual(codigo, 0)

    def test_sem_docs_nao_escreve_arquivo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entrada = Path(tmp) / "hardware.json"
            docs = Path(tmp) / "AMBIENTE.md"
            entrada.write_text(json.dumps(carregar_thinkpad()), encoding="utf-8")
            codigo, _, _ = self._rodar("--hardware", str(entrada), "--docs", str(docs), "--sem-docs")
            self.assertEqual(codigo, 0)
            self.assertFalse(docs.exists())

    def test_saida_em_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entrada = Path(tmp) / "hardware.json"
            entrada.write_text(json.dumps(carregar_thinkpad()), encoding="utf-8")
            codigo, saida, _ = self._rodar("--hardware", str(entrada), "--json")
            self.assertEqual(codigo, 0)
            dados = json.loads(saida)
            self.assertEqual(dados["perfil"], "C")
            self.assertIn("justificativa", dados)

    def test_arquivo_inexistente(self) -> None:
        codigo, _, erro = self._rodar("--hardware", str(RAIZ / "nao-existe.json"))
        self.assertEqual(codigo, 2)
        self.assertIn("Rode scripts/diagnostico", erro)

    def test_json_quebrado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entrada = Path(tmp) / "hardware.json"
            entrada.write_text("{ isto não é json", encoding="utf-8")
            codigo, _, erro = self._rodar("--hardware", str(entrada))
            self.assertEqual(codigo, 2)
            self.assertIn("não é um JSON válido", erro)

    def test_hardware_invalido_lista_os_problemas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entrada = Path(tmp) / "hardware.json"
            dados = hw()
            dados["gpus"] = [[{"vendor": "intel", "name": "x", "kind": None}]]
            entrada.write_text(json.dumps(dados), encoding="utf-8")
            codigo, _, erro = self._rodar("--hardware", str(entrada))
            self.assertEqual(codigo, 2)
            self.assertIn("gpus[0]", erro)


if __name__ == "__main__":
    unittest.main()
