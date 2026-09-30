"""Relatório docs/AMBIENTE.md: conteúdo, tabelas e privacidade."""

from __future__ import annotations

import unittest

from app.hardware import classificar, renderizar_ambiente

from .builders import aceleracao, carregar_thinkpad, ferramentas, gpu, hw


class TestRelatorio(unittest.TestCase):
    def setUp(self) -> None:
        self.dados = carregar_thinkpad()
        self.md = renderizar_ambiente(self.dados, classificar(self.dados))

    def test_estrutura_principal(self) -> None:
        for trecho in (
            "# Ambiente: LENOVO ThinkPad T14 Gen 2i",
            "**C: Notebook ou GPU integrada**",
            "## Por quê",
            "## Avisos",
            "## Aceleração disponível",
            "## Ferramentas",
            "## Pendências",
            "## Como atualizar",
        ):
            if trecho == "## Por quê":
                trecho = "Por quê:"
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, self.md)

    def test_dados_da_maquina_aparecem(self) -> None:
        for trecho in ("i7-1185G7", "AVX-512", "Iris(R) Xe Graphics", "16237 MB", "31,7 GB", "Vulkan", "DirectML"):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, self.md)

    def test_modo_traduzido(self) -> None:
        self.assertIn("(modo leve)", self.md)  # a fixture veio de uma coleta leve
        completo = dict(self.dados, mode="full")
        self.assertIn("(modo completo)", renderizar_ambiente(completo, classificar(completo)))

    def test_ollama_e_gpu_integrada_descartada(self) -> None:
        self.assertIn("descartada por ser integrada", self.md)
        self.assertIn("CPU: sempre disponível", self.md)

    def test_terminacao_e_sem_espacos_a_direita_nas_linhas_de_tabela(self) -> None:
        self.assertTrue(self.md.endswith("\n"))
        for linha in self.md.splitlines():
            if linha.startswith("|"):
                self.assertEqual(linha, linha.rstrip())

    def test_pasta_pessoal_e_anonimizada(self) -> None:
        tools = ferramentas(
            node={"installed": True, "version": "22.0.0", "path": r"C:\Users\fulano\AppData\Local\node\node.exe"}
        )
        dados = hw(tools=tools)
        md = renderizar_ambiente(dados, classificar(dados))
        self.assertNotIn("fulano", md)
        self.assertIn("%USERPROFILE%", md)

    def test_pasta_pessoal_unix_e_anonimizada(self) -> None:
        tools = ferramentas(node={"installed": True, "version": "22.0.0", "path": "/home/beltrano/.nvm/bin/node"})
        dados = hw(familia="linux", tools=tools)
        md = renderizar_ambiente(dados, classificar(dados))
        self.assertNotIn("beltrano", md)
        self.assertIn("~/.nvm/bin/node", md)

    def test_barra_vertical_nao_quebra_a_tabela(self) -> None:
        dados = hw(gpus=[gpu("unknown", "Placa | com barra", dedicated_mb=128)], accel=aceleracao())
        md = renderizar_ambiente(dados, classificar(dados))
        self.assertIn(r"Placa \| com barra", md)

    def test_sem_gpu(self) -> None:
        dados = hw(gpus=[])
        md = renderizar_ambiente(dados, classificar(dados))
        self.assertIn("Nenhuma GPU detectada.", md)
        self.assertIn("| GPU principal | nenhuma |", md)

    def test_relatorio_para_amd_mostra_arquitetura_estimada(self) -> None:
        dados = hw(gpus=[gpu("amd", "AMD Radeon RX 6750 XT", dedicated_mb=12_288)], accel=aceleracao(vulkan=True))
        md = renderizar_ambiente(dados, classificar(dados))
        self.assertIn("gfx1031", md)

    def test_relatorio_nao_altera_a_entrada(self) -> None:
        antes = repr(self.dados)
        renderizar_ambiente(self.dados, classificar(self.dados))
        self.assertEqual(repr(self.dados), antes)


if __name__ == "__main__":
    unittest.main()
