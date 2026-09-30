"""Classificação de perfil (briefing, seção 2.2) com hardware simulado: A, B, C, D em Windows, Linux e macOS."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from app.hardware import (
    HardwareInvalido,
    classificar,
    estimar_gfx_amd,
    ferramentas_pendentes,
    inferir_tipo_gpu,
    normalizar_hardware,
    python_do_projeto,
    validar_hardware,
)

from .builders import aceleracao, carregar_thinkpad, ferramentas, gpu, hw


class TestPerfilA(unittest.TestCase):
    def test_nvidia_12gb_windows(self) -> None:
        for vram in (12_288, 11_900):  # 12 GB nominais aparecem entre 11,9 e 12,3 GB
            with self.subTest(vram_mb=vram):
                dados = hw(
                    gpus=[gpu("nvidia", "NVIDIA GeForce RTX 3060", dedicated_mb=vram)], accel=aceleracao(cuda=True)
                )
                c = classificar(dados)
                self.assertEqual(c.perfil, "A")
                self.assertTrue(c.aceleracao[0].startswith("CUDA"))
                self.assertEqual(c.memoria_ia_mb, vram)

    def test_nvidia_24gb_linux(self) -> None:
        dados = hw(
            familia="linux",
            gpus=[gpu("nvidia", "NVIDIA GeForce RTX 4090", dedicated_mb=24_564)],
            accel=aceleracao(cuda=True),
        )
        self.assertEqual(classificar(dados).perfil, "A")

    def test_apple_silicon_32gb(self) -> None:
        dados = hw(
            familia="macos",
            arch="arm64",
            ram_mb=32_768,
            gpus=[gpu("apple", "Apple M2 Max", kind="unified")],
            accel=aceleracao(metal=True),
        )
        c = classificar(dados)
        self.assertEqual(c.perfil, "A")
        self.assertTrue(c.aceleracao[0].startswith("Metal"))
        self.assertEqual(c.memoria_ia_mb, int(32_768 * 0.75))

    def test_nvidia_sem_cuda_continua_a_mas_avisa_do_driver(self) -> None:
        dados = hw(gpus=[gpu("nvidia", "NVIDIA GeForce RTX 3090", dedicated_mb=24_576)], accel=aceleracao(cuda=False))
        c = classificar(dados)
        self.assertEqual(c.perfil, "A")
        self.assertTrue(any("driver" in a for a in c.avisos))


class TestPerfilB(unittest.TestCase):
    def test_amd_rx_6750_xt_com_vulkan(self) -> None:
        dados = hw(
            gpus=[gpu("amd", "AMD Radeon RX 6750 XT", dedicated_mb=12_288)],
            accel=aceleracao(vulkan=True, directml=True),
        )
        c = classificar(dados)
        self.assertEqual(c.perfil, "B")
        self.assertTrue(c.aceleracao[0].startswith("Vulkan"))
        self.assertTrue(any("gfx1031" in linha for linha in c.aceleracao))

    def test_nvidia_8gb_linux(self) -> None:
        dados = hw(
            familia="linux",
            gpus=[gpu("nvidia", "NVIDIA GeForce RTX 4060", dedicated_mb=8_188)],
            accel=aceleracao(cuda=True),
        )
        self.assertEqual(classificar(dados).perfil, "B")

    def test_apple_silicon_16gb(self) -> None:
        dados = hw(
            familia="macos",
            arch="arm64",
            ram_mb=16_384,
            gpus=[gpu("apple", "Apple M1", kind="unified")],
            accel=aceleracao(metal=True),
        )
        self.assertEqual(classificar(dados).perfil, "B")

    def test_intel_arc_a770_dedicada(self) -> None:
        dados = hw(
            gpus=[gpu("intel", "Intel(R) Arc(TM) A770 Graphics", dedicated_mb=16_128)], accel=aceleracao(vulkan=True)
        )
        self.assertEqual(classificar(dados).perfil, "B")

    def test_amd_com_muita_vram_e_candidata_a_a(self) -> None:
        dados = hw(gpus=[gpu("amd", "AMD Radeon RX 7900 XTX", dedicated_mb=24_576)], accel=aceleracao(vulkan=True))
        c = classificar(dados)
        self.assertEqual(c.perfil, "B")
        self.assertTrue(any("candidata ao perfil A" in a for a in c.avisos))

    def test_varias_gpus_usa_a_dedicada(self) -> None:
        dados = hw(
            laptop=True,
            gpus=[
                gpu("intel", "Intel(R) UHD Graphics", dedicated_mb=128, shared_mb=8_000),
                gpu("nvidia", "NVIDIA GeForce RTX 4060 Laptop GPU", dedicated_mb=8_188),
            ],
            accel=aceleracao(cuda=True),
        )
        c = classificar(dados)
        self.assertEqual(c.perfil, "B")
        self.assertEqual(c.gpu_principal, "NVIDIA GeForce RTX 4060 Laptop GPU")


class TestPerfilC(unittest.TestCase):
    def test_thinkpad_t14_gen2i_maquina_de_referencia(self) -> None:
        dados = carregar_thinkpad()
        self.assertEqual(validar_hardware(dados), [])
        c = classificar(dados)
        self.assertEqual(c.perfil, "C")
        self.assertEqual(c.gpu_principal, "Intel(R) Iris(R) Xe Graphics")
        self.assertIn("AVX-512", c.aceleracao[0])
        self.assertTrue(any("sem VRAM dedicada" in j for j in c.justificativa))
        self.assertTrue(any("Espaço apertado" in a for a in c.avisos))  # ~61 GB livres
        self.assertGreater(c.memoria_ia_mb, 20_000)

    def test_sem_gpu_so_cpu(self) -> None:
        c = classificar(hw(gpus=[], cpu_modelo="CPU sem GPU"))
        self.assertEqual(c.perfil, "C")
        self.assertIsNone(c.gpu_principal)
        self.assertIn("CPU", c.aceleracao[0])

    def test_igpu_amd_linux(self) -> None:
        dados = hw(
            familia="linux",
            ram_mb=31_000,
            gpus=[gpu("amd", "AMD Radeon 780M Graphics", dedicated_mb=512, shared_mb=15_000)],
            accel=aceleracao(vulkan=True),
        )
        c = classificar(dados)
        self.assertEqual(c.perfil, "C")
        self.assertIn("integrada", c.justificativa[2])

    def test_windows_arm64_com_npu(self) -> None:
        dados = hw(
            arch="arm64",
            laptop=True,
            ram_mb=16_000,
            npu="Snapdragon X NPU",
            gpus=[gpu("unknown", "Qualcomm Adreno GPU", dedicated_mb=128)],
        )
        c = classificar(dados)
        self.assertEqual(c.perfil, "C")

    def test_nvidia_com_menos_de_8gb_comeca_em_c(self) -> None:
        dados = hw(gpus=[gpu("nvidia", "NVIDIA GeForce RTX 3050", dedicated_mb=6_144)], accel=aceleracao(cuda=True))
        c = classificar(dados)
        self.assertEqual(c.perfil, "C")
        self.assertTrue(any("menos de 8 GB" in a for a in c.avisos))

    def test_amd_dedicada_sem_caminho_de_aceleracao(self) -> None:
        dados = hw(gpus=[gpu("amd", "AMD Radeon RX 6800", dedicated_mb=16_384)], accel=aceleracao())
        c = classificar(dados)
        self.assertEqual(c.perfil, "C")
        self.assertTrue(any("nenhum caminho de aceleração" in j for j in c.justificativa))

    def test_ram_16gb_nominal_passa_do_minimo(self) -> None:
        self.assertEqual(classificar(hw(ram_mb=15_900)).perfil, "C")

    def test_menos_de_24gb_de_ram_avisa_limite_de_modelo(self) -> None:
        c = classificar(hw(ram_mb=16_000))
        self.assertTrue(any("24 GB" in a for a in c.avisos))


class TestPerfilD(unittest.TestCase):
    def test_ram_abaixo_de_16gb_mesmo_com_gpu_forte(self) -> None:
        dados = hw(
            ram_mb=8_000,
            gpus=[gpu("nvidia", "NVIDIA GeForce RTX 4090", dedicated_mb=24_564)],
            accel=aceleracao(cuda=True),
        )
        c = classificar(dados)
        self.assertEqual(c.perfil, "D")
        self.assertTrue(any("RAM" in j for j in c.justificativa))

    def test_pouco_disco(self) -> None:
        dados = hw(
            livre_gb=10,
            gpus=[gpu("nvidia", "NVIDIA GeForce RTX 4090", dedicated_mb=24_564)],
            accel=aceleracao(cuda=True),
        )
        c = classificar(dados)
        self.assertEqual(c.perfil, "D")
        self.assertTrue(any("disco" in j for j in c.justificativa))

    def test_os_dois_motivos_aparecem(self) -> None:
        c = classificar(hw(ram_mb=8_000, livre_gb=5))
        self.assertEqual(c.perfil, "D")
        self.assertGreaterEqual(sum(("RAM" in j) or ("disco" in j) for j in c.justificativa), 2)


class TestAvisosGerais(unittest.TestCase):
    def test_notebook_na_bateria(self) -> None:
        c = classificar(hw(laptop=True, na_tomada=False))
        self.assertTrue(any("bateria" in a for a in c.avisos))

    def test_notebook_na_tomada_nao_avisa_de_bateria(self) -> None:
        c = classificar(hw(laptop=True, na_tomada=True))
        self.assertFalse(any("bateria" in a for a in c.avisos))

    def test_plano_de_energia_economia(self) -> None:
        for plano in ("Economia de energia", "power-saver", "low-power"):
            with self.subTest(plano=plano):
                c = classificar(hw(laptop=True, plano=plano))
                self.assertTrue(any("Plano de energia" in a for a in c.avisos))

    def test_plano_equilibrado_nao_avisa(self) -> None:
        c = classificar(hw(laptop=True, plano="Equilibrado"))
        self.assertFalse(any("Plano de energia" in a for a in c.avisos))

    def test_classificar_nao_modifica_a_entrada(self) -> None:
        dados = hw(gpus=[gpu("amd", "AMD Radeon RX 6750 XT", dedicated_mb=12_288)], accel=aceleracao(vulkan=True))
        copia = copy.deepcopy(dados)
        classificar(dados)
        self.assertEqual(dados, copia)


class TestValidacao(unittest.TestCase):
    def test_hardware_valido(self) -> None:
        self.assertEqual(validar_hardware(hw()), [])

    def test_nao_e_objeto(self) -> None:
        self.assertTrue(validar_hardware([]))

    def test_versao_de_schema_errada(self) -> None:
        dados = hw()
        dados["schema_version"] = 99
        self.assertTrue(any("schema_version" in e for e in validar_hardware(dados)))

    def test_familia_de_so_invalida(self) -> None:
        dados = hw()
        dados["os"]["family"] = "beos"
        self.assertTrue(any("os.family" in e for e in validar_hardware(dados)))

    def test_ram_invalida(self) -> None:
        for ruim in (0, -1, "32", None, True):
            with self.subTest(ram=ruim):
                dados = hw()
                dados["memory"]["ram_total_mb"] = ruim
                self.assertTrue(any("ram_total_mb" in e for e in validar_hardware(dados)))

    def test_gpu_sem_nome(self) -> None:
        dados = hw(gpus=[gpu("intel", "x")])
        del dados["gpus"][0]["name"]
        self.assertTrue(any("gpus[0]" in e for e in validar_hardware(dados)))

    def test_gpu_com_tipo_invalido_e_tipo_nulo_permitido(self) -> None:
        self.assertEqual(validar_hardware(hw(gpus=[gpu("intel", "x", kind=None)])), [])
        ruim = hw(gpus=[gpu("intel", "x", kind="quantica")])
        self.assertTrue(any("kind" in e for e in validar_hardware(ruim)))

    def test_classificar_levanta_com_dados_invalidos(self) -> None:
        dados = hw()
        del dados["cpu"]
        with self.assertRaises(HardwareInvalido) as ctx:
            classificar(dados)
        self.assertTrue(ctx.exception.erros)

    def test_gpus_aninhadas_por_engano_sao_rejeitadas(self) -> None:
        # Regressão: o coletor do Windows chegou a gerar gpus como lista de listas ([[{...}]]).
        dados = hw()
        dados["gpus"] = [[gpu("intel", "x")]]
        self.assertTrue(any("gpus[0]" in e for e in validar_hardware(dados)))


class TestNormalizacao(unittest.TestCase):
    def test_inferir_tipo_de_gpu(self) -> None:
        casos = [
            ("intel", "Intel(R) Iris(R) Xe Graphics", None, "integrated"),
            ("intel", "Intel(R) UHD Graphics 770", None, "integrated"),
            ("intel", "Intel(R) Arc(TM) Graphics", None, "integrated"),  # iGPU do Core Ultra
            ("intel", "Intel(R) Arc(TM) 140V GPU", None, "integrated"),
            ("intel", "Intel(R) Arc(TM) A770 Graphics", None, "discrete"),
            ("intel", "Intel(R) Arc(TM) B580 Graphics", None, "discrete"),
            ("amd", "AMD Radeon(TM) Graphics", 512, "integrated"),
            ("amd", "AMD Radeon(TM) 780M Graphics", 4096, "integrated"),
            ("amd", "AMD Radeon RX Vega 11 Graphics", None, "integrated"),
            ("amd", "AMD Radeon RX 6750 XT", 12_288, "discrete"),
            ("amd", "AMD Radeon PRO W7800", 32_768, "discrete"),
            ("nvidia", "NVIDIA GeForce RTX 4060 Laptop GPU", 8_188, "discrete"),
            ("apple", "Apple M2 Max", None, "unified"),
            ("unknown", "Placa desconhecida", 4096, "discrete"),
            ("unknown", "Placa desconhecida", 128, "integrated"),
        ]
        for vendor, nome, dedicada, esperado in casos:
            with self.subTest(nome=nome):
                self.assertEqual(inferir_tipo_gpu(vendor, nome, dedicada), esperado)

    def test_estimar_gfx_amd(self) -> None:
        casos = {
            "AMD Radeon RX 6750 XT": "gfx1031",
            "AMD Radeon RX 6700 XT": "gfx1031",
            "AMD Radeon RX 6650 XT": "gfx1032",
            "AMD Radeon RX 6600": "gfx1032",
            "AMD Radeon RX 6800 XT": "gfx1030",
            "AMD Radeon RX 6500 XT": "gfx1034",
            "AMD Radeon RX 7900 XTX": "gfx1100",
            "AMD Radeon RX 7800 XT": "gfx1101",
            "AMD Radeon RX 7600": "gfx1102",
            "AMD Radeon RX 9070 XT": "gfx1201",
            "AMD Radeon RX 580": "gfx803",
            "AMD Radeon(TM) 780M Graphics": "gfx1103",
            "AMD Radeon(TM) 680M": "gfx1035",
            "NVIDIA GeForce RTX 4090": None,
            "Intel(R) Iris(R) Xe Graphics": None,
        }
        for nome, esperado in casos.items():
            with self.subTest(nome=nome):
                self.assertEqual(estimar_gfx_amd(nome), esperado)

    def test_normalizar_preenche_sem_alterar_o_original(self) -> None:
        original = hw(gpus=[gpu("amd", "AMD Radeon RX 6750 XT", dedicated_mb=12_288)])
        copia = copy.deepcopy(original)
        n = normalizar_hardware(original)
        self.assertEqual(original, copia)
        self.assertEqual(n["gpus"][0]["kind"], "discrete")
        self.assertEqual(n["gpus"][0]["gfx_arch"], "gfx1031")
        self.assertIn("estimado", n["gpus"][0]["gfx_arch_source"])

    def test_normalizar_respeita_valores_do_coletor(self) -> None:
        n = normalizar_hardware(hw(gpus=[gpu("amd", "AMD Radeon RX 6750 XT", kind="integrated", gfx_arch="gfx9999")]))
        self.assertEqual(n["gpus"][0]["kind"], "integrated")
        self.assertEqual(n["gpus"][0]["gfx_arch"], "gfx9999")


class TestFerramentasPendentes(unittest.TestCase):
    def _itens(self, dados: dict) -> dict[str, str]:
        return {p.item: p.estado for p in ferramentas_pendentes(dados)}

    def test_ambiente_completo_nao_tem_pendencias(self) -> None:
        self.assertEqual(ferramentas_pendentes(hw()), [])

    def test_ffmpeg_ausente(self) -> None:
        dados = hw(tools=ferramentas(ffmpeg={"installed": False, "version": None, "path": None, "encoders": []}))
        self.assertEqual(self._itens(dados).get("ffmpeg"), "ausente")

    def test_python_314_com_312_disponivel_sugere_312(self) -> None:
        py = {"installed": True, "version": "3.14.3", "path": "x", "versions_available": ["3.14", "3.12"]}
        pendencia = [p for p in ferramentas_pendentes(hw(tools=ferramentas(python=py))) if p.item == "Python"]
        self.assertEqual(len(pendencia), 1)
        self.assertIn("3.12", pendencia[0].acao)

    def test_python_antigo(self) -> None:
        py = {"installed": True, "version": "3.8.10", "path": "x", "versions_available": []}
        self.assertIn("antigo", self._itens(hw(tools=ferramentas(python=py)))["Python"])

    def test_node_antigo(self) -> None:
        node = {"installed": True, "version": "18.0.0", "path": "x"}
        self.assertIn("antigo", self._itens(hw(tools=ferramentas(node=node)))["Node.js"])

    def test_python_do_sistema_nao_incomoda_quando_o_app_ja_roda_no_recomendado(self) -> None:
        py = {"installed": True, "version": "3.14.3", "path": "x", "versions_available": ["3.14", "3.12"]}
        dados = hw(tools=ferramentas(python=py))
        self.assertEqual([p for p in ferramentas_pendentes(dados, (3, 12)) if p.item == "Python"], [])
        self.assertEqual([p for p in ferramentas_pendentes(dados, (3, 13)) if p.item == "Python"], [])
        # se o app roda numa versão nova demais ou antiga demais, a sugestão volta
        self.assertEqual(len([p for p in ferramentas_pendentes(dados, (3, 14)) if p.item == "Python"]), 1)
        self.assertEqual(len([p for p in ferramentas_pendentes(dados, (3, 9)) if p.item == "Python"]), 1)

    def test_le_a_versao_do_ambiente_virtual_do_projeto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self.assertIsNone(python_do_projeto(raiz))  # sem .venv
            (raiz / ".venv").mkdir()
            self.assertIsNone(python_do_projeto(raiz))  # .venv sem pyvenv.cfg
            cfg = raiz / ".venv" / "pyvenv.cfg"
            cfg.write_text(
                "home = C:\\Python\ninclude-system-site-packages = false\nversion = 3.12.4\n", encoding="utf-8"
            )
            self.assertEqual(python_do_projeto(raiz), (3, 12))
            cfg.write_text("version = 3.13\n", encoding="utf-8")
            self.assertEqual(python_do_projeto(raiz), (3, 13))
            cfg.write_text("home = x\nversion = abc\n", encoding="utf-8")
            self.assertIsNone(python_do_projeto(raiz))

    def test_o_aviso_da_gpu_integrada_do_ollama_nao_e_pendencia(self) -> None:
        # não pede nenhuma ação do usuário: fica só no perfil (caminho de aceleração) e nos documentos
        ollama = ferramentas()["ollama"]
        ollama["igpu_dropped"] = True
        self.assertNotIn("Ollama", self._itens(hw(tools=ferramentas(ollama=ollama))))

    def test_o_texto_do_ffmpeg_manda_para_modelos(self) -> None:
        dados = hw(tools=ferramentas(ffmpeg={"installed": False, "version": None, "path": None, "encoders": []}))
        acao = next(p.acao for p in ferramentas_pendentes(dados) if p.item == "ffmpeg")
        self.assertIn("Modelos", acao)

    def test_claude_sem_login(self) -> None:
        claude = ferramentas()["claude_code"]
        claude["logged_in"] = False
        self.assertEqual(self._itens(hw(tools=ferramentas(claude_code=claude)))["Claude Code"], "sem login")

    def test_login_desconhecido_nao_gera_pendencia(self) -> None:
        claude = ferramentas()["claude_code"]
        claude["logged_in"] = None
        self.assertNotIn("Claude Code", self._itens(hw(tools=ferramentas(claude_code=claude))))


if __name__ == "__main__":
    unittest.main()
