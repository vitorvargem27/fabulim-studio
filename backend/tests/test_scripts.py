"""O script `scripts/testar.py` (o comando único de qualidade): pasta temporária própria e resumo do pytest."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

from .conftest import RAIZ


@pytest.fixture(scope="module")
def testar() -> ModuleType:
    spec = importlib.util.spec_from_file_location("testar_script", RAIZ / "scripts" / "testar.py")
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


class TestPastaTemporaria:
    """Regressão: o hook do git rodado pelo Git Bash trocava o TEMP por /tmp e o pytest perdia a pasta temporária."""

    def test_usa_uma_pasta_propria_dentro_do_projeto(self, testar: ModuleType) -> None:
        ambiente = testar._ambiente_temporario()
        pasta = Path(ambiente["TMP"])
        try:
            assert pasta.is_dir() and RAIZ in pasta.parents
            assert ambiente["TEMP"] == ambiente["TMPDIR"] == ambiente["TMP"]
        finally:
            shutil.rmtree(pasta, ignore_errors=True)

    def test_a_pasta_e_ignorada_pelo_git(self) -> None:
        linhas = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert "tmp/" in linhas


class TestResumoDoPytest:
    def test_conta_testes_e_cobertura(self, testar: ModuleType) -> None:
        texto = "TOTAL   1200   30   400   20   97%\n294 passed, 1 deselected in 85.10s"
        assert testar.resumo_pytest(texto) == "294 testes; cobertura 97% (mínimo 80%)"

    def test_lista_os_pulados_com_o_motivo(self, testar: ModuleType) -> None:
        texto = (
            "SKIPPED [1] backend\\tests\\test_seguranca.py:219: sem privilégio para links simbólicos\n"
            "SKIPPED [2] backend\\tests\\test_x.py:10: sem privilégio para links simbólicos\n"
            "293 passed, 3 skipped in 80.00s"
        )
        detalhe = testar.resumo_pytest(texto, cobertura_medida=False)
        assert detalhe.startswith("293 testes; cobertura não medida")
        assert detalhe.count("sem privilégio para links simbólicos") == 1  # o mesmo motivo aparece uma vez só
        assert "pulado(s) neste ambiente" in detalhe

    def test_sem_resumo(self, testar: ModuleType) -> None:
        assert testar.resumo_pytest("nada útil") == "sem resumo"


class TestSaidaDosPassosQueFalharam:
    """Regressão: a tabela de cobertura ocupava o fim da saída e o teste que falhou não aparecia."""

    def test_a_tabela_de_cobertura_nao_esconde_a_falha(self, testar: ModuleType) -> None:
        saida = (
            "FAILED backend/tests/test_x.py::test_a - assert 1 == 2\n"
            "---------- coverage: platform win32, python 3.12 ----------\n"
            "Name              Stmts   Miss\nbackend\\app\\x.py     10      1\nTOTAL   10   1   90%\n"
            "1 failed, 5 passed in 3.0s"
        )
        trecho = testar.trecho_da_saida(saida)
        assert "FAILED backend/tests/test_x.py::test_a" in trecho
        assert "Stmts" not in trecho and "omitida" in trecho
        assert trecho.endswith("1 failed, 5 passed in 3.0s")

    def test_sem_tabela_mostra_o_fim_da_saida(self, testar: ModuleType) -> None:
        texto = "a" * 500 + "FIM"
        assert testar.trecho_da_saida(texto, limite=100) == texto[-100:]

    def test_guarda_a_saida_completa_de_cada_passo(
        self, testar: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(testar, "PASTA_DAS_SAIDAS", tmp_path / "saidas")
        falhas = [
            testar.Resultado("Python: testes e cobertura (pytest)", "FALHOU", saida="linha 1\nlinha 2"),
            testar.Resultado("Ponta a ponta", "FALHOU", saida="outra"),
        ]
        pasta = testar.guardar_saidas(falhas)
        assert (pasta / "01-python-testes-e-cobertura-pytest.txt").read_text(encoding="utf-8") == "linha 1\nlinha 2"
        assert (pasta / "02-ponta-a-ponta.txt").read_text(encoding="utf-8") == "outra"
