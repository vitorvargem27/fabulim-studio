"""Configuração (regras de segurança) e logs estruturados com máscara de segredos."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from app.__main__ import main
from app.config import PORTA_PADRAO, ConfiguracaoInvalida, carregar_configuracao, ler_dotenv
from app.logging_setup import FormatadorJson, MascaraSegredos, configurar_logging, ler_logs, mascarar

RAIZ = Path(__file__).resolve().parents[2]


class TestConfiguracao:
    def test_padroes(self) -> None:
        c = carregar_configuracao({}, root=RAIZ)
        assert c.host == "127.0.0.1"
        assert c.port == PORTA_PADRAO == 8765
        assert c.data_dir == RAIZ / "data"
        assert c.auto_diagnostico is True
        assert "http://127.0.0.1:8765" in c.cors_origins
        assert "http://localhost:4200" in c.cors_origins

    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.0.10", "meu-pc.local", "::"])
    def test_rejeita_host_fora_do_loopback(self, host: str) -> None:
        with pytest.raises(ConfiguracaoInvalida, match=r"127\.0\.0\.1"):
            carregar_configuracao({"FABULIM_HOST": host}, root=RAIZ)

    @pytest.mark.parametrize("porta", ["80", "abc", "70000", ""])
    def test_rejeita_porta_invalida(self, porta: str) -> None:
        with pytest.raises(ConfiguracaoInvalida):
            carregar_configuracao({"FABULIM_PORT": porta}, root=RAIZ)

    def test_rejeita_ollama_fora_da_maquina(self) -> None:
        with pytest.raises(ConfiguracaoInvalida, match="esta máquina"):
            carregar_configuracao({"FABULIM_OLLAMA_URL": "http://api.exemplo.com:11434"}, root=RAIZ)

    def test_aceita_ollama_em_outra_porta_local(self) -> None:
        c = carregar_configuracao({"FABULIM_OLLAMA_URL": "http://localhost:11435/"}, root=RAIZ)
        assert c.ollama_url == "http://localhost:11435"

    def test_pastas_configuraveis(self, tmp_path: Path) -> None:
        c = carregar_configuracao(
            {"FABULIM_DATA_DIR": str(tmp_path / "d"), "FABULIM_MODELS_DIR": str(tmp_path / "m")}, root=RAIZ
        )
        assert c.data_dir == (tmp_path / "d").resolve()
        assert c.db_path == c.data_dir / "fabulim.db"
        assert c.log_dir == c.data_dir / "logs"
        assert c.models_dir == (tmp_path / "m").resolve()

    def test_capacidades_ficam_ao_lado_do_hardware(self, tmp_path: Path) -> None:
        c = carregar_configuracao({"FABULIM_HARDWARE_JSON": str(tmp_path / "x" / "hw.json")}, root=RAIZ)
        assert c.capabilities_json == (tmp_path / "x" / "capabilities.json").resolve()

    def test_desligar_diagnostico_automatico(self) -> None:
        assert carregar_configuracao({"FABULIM_AUTO_DIAGNOSTICO": "0"}, root=RAIZ).auto_diagnostico is False


class TestDotenv:
    """O `.env.example` manda copiar para `.env`: o arquivo precisa valer de verdade (e só para chaves FABULIM_*)."""

    @pytest.fixture(autouse=True)
    def _ambiente_limpo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for chave in [k for k in os.environ if k.startswith("FABULIM_")]:
            monkeypatch.delenv(chave)

    def test_le_chaves_fabulim_com_aspas_comentarios_e_export(self, tmp_path: Path) -> None:
        arquivo = tmp_path / ".env"
        arquivo.write_text(
            "\ufeff# comentário\r\n"
            "FABULIM_PORT=9001\r\n"
            'export FABULIM_DATA_DIR="D:\\dados com espaço"\r\n'
            "FABULIM_OLLAMA_URL='http://localhost:11435'  # servidor da iGPU\r\n"
            "FABULIM_AUTO_DIAGNOSTICO=0 # sem diagnóstico\r\n"
            "\r\n"
            "linha sem igual\r\n",
            encoding="utf-8",
            newline="",  # mantém o CRLF do Windows exatamente como escrito
        )
        assert ler_dotenv(arquivo) == {
            "FABULIM_PORT": "9001",
            "FABULIM_DATA_DIR": "D:\\dados com espaço",
            "FABULIM_OLLAMA_URL": "http://localhost:11435",
            "FABULIM_AUTO_DIAGNOSTICO": "0",
        }

    def test_ignora_o_que_nao_e_do_fabulim(self, tmp_path: Path) -> None:
        arquivo = tmp_path / ".env"
        arquivo.write_text("PATH=/perigo\nPYTHONPATH=/x\nfabulim_port=1\nFABULIM_PORT=9001\n", encoding="utf-8")
        assert ler_dotenv(arquivo) == {"FABULIM_PORT": "9001"}

    def test_arquivo_ausente_ou_ilegivel_vale_como_vazio(self, tmp_path: Path) -> None:
        assert ler_dotenv(tmp_path / "nao-existe") == {}
        (tmp_path / ".env").write_bytes(b"\xff\xfe\x00 nao e utf-8 \xc3\x28")
        assert ler_dotenv(tmp_path / ".env") == {}

    def test_sem_env_explicito_o_arquivo_da_raiz_vale(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("FABULIM_PORT=9001\nFABULIM_AUTO_DIAGNOSTICO=0\n", encoding="utf-8")
        c = carregar_configuracao(root=tmp_path)
        assert c.port == 9001 and c.auto_diagnostico is False

    def test_variavel_de_ambiente_de_verdade_vence_o_arquivo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".env").write_text("FABULIM_PORT=9001\n", encoding="utf-8")
        monkeypatch.setenv("FABULIM_PORT", "9002")
        assert carregar_configuracao(root=tmp_path).port == 9002

    def test_o_arquivo_nao_burla_as_regras_de_seguranca(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("FABULIM_HOST=0.0.0.0\n", encoding="utf-8")
        with pytest.raises(ConfiguracaoInvalida, match=r"127\.0\.0\.1"):
            carregar_configuracao(root=tmp_path)
        (tmp_path / ".env").write_text("FABULIM_OLLAMA_URL=http://api.exemplo.com:11434\n", encoding="utf-8")
        with pytest.raises(ConfiguracaoInvalida, match="esta máquina"):
            carregar_configuracao(root=tmp_path)

    def test_com_env_explicito_o_arquivo_e_ignorado(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("FABULIM_PORT=9001\n", encoding="utf-8")
        assert carregar_configuracao({}, root=tmp_path).port == PORTA_PADRAO  # testes ficam isolados do `.env` real


class TestPortaDoIniciar:
    """`servidor.py --porta` diz onde o servidor vai escutar; o iniciar.bat e o iniciar.sh perguntam a ele."""

    @pytest.fixture(autouse=True)
    def _ambiente_limpo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for chave in [k for k in os.environ if k.startswith("FABULIM_")]:
            monkeypatch.delenv(chave)

    def test_imprime_a_porta_efetiva(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setenv("FABULIM_PORT", "9123")
        assert main(["--porta"]) == 0
        assert capsys.readouterr().out.strip() == "9123"

    def test_configuracao_invalida_vai_para_o_erro_padrao_e_o_codigo_2(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("FABULIM_HOST", "0.0.0.0")
        assert main(["--porta"]) == 2
        saida = capsys.readouterr()
        assert saida.out == "" and "127.0.0.1" in saida.err  # a saída padrão fica limpa para o script ler só a porta


class TestMascara:
    @pytest.mark.parametrize(
        "texto,segredo",
        [
            ("chave sk-ant-api03-ABCDEFGH1234567890 usada", "ABCDEFGH1234567890"),
            ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def", "eyJhbGciOiJIUzI1NiJ9"),
            ("ANTHROPIC_API_KEY=abcdef123456", "abcdef123456"),
            ('{"password": "minhaSenha123"}', "minhaSenha123"),
            ("token: xyz789secret", "xyz789secret"),
            ("uma chave sk-abcdefghijklmnopqrstuv qualquer", "abcdefghijklmnopqrstuv"),
        ],
    )
    def test_esconde_segredos(self, texto: str, segredo: str) -> None:
        assert segredo not in mascarar(texto)
        assert "***" in mascarar(texto)

    def test_texto_comum_fica_igual(self) -> None:
        assert mascarar("Job concluído em 3,2 s") == "Job concluído em 3,2 s"


class TestLogs:
    def _logger(self, log_dir: Path) -> logging.Logger:
        return configurar_logging(log_dir, console=False)

    def test_escreve_jsonl_com_servico_e_mascara(self, tmp_path: Path) -> None:
        log = self._logger(tmp_path)
        logging.getLogger("fabulim.ollama").warning("falhou com token=abc123secret")
        for h in log.handlers:
            h.flush()
        linhas = (tmp_path / "app.jsonl").read_text(encoding="utf-8").splitlines()
        entrada = json.loads(linhas[-1])
        assert entrada["service"] == "ollama"
        assert entrada["level"] == "WARNING"
        assert "abc123secret" not in entrada["msg"]
        assert entrada["ts"].endswith("+00:00")

    def test_formatador_inclui_job_e_excecao(self) -> None:
        registro = logging.LogRecord("fabulim.fila", logging.ERROR, __file__, 1, "erro %s", ("x",), None)
        registro.job_id = "a" * 32
        try:
            raise ValueError("Bearer segredo123456789")
        except ValueError:
            import sys

            registro.exc_info = sys.exc_info()
        saida = json.loads(FormatadorJson().format(registro))
        assert saida["job_id"] == "a" * 32
        assert "segredo123456789" not in saida["exc"]

    def test_filtro_mascara_argumentos(self) -> None:
        r = logging.LogRecord("x", logging.INFO, __file__, 1, "chave %s", ("sk-ant-abcdefghijk",), None)
        MascaraSegredos().filter(r)
        assert "sk-ant" not in r.getMessage()

    def test_ler_logs_filtra_por_servico_nivel_e_job(self, tmp_path: Path) -> None:
        self._logger(tmp_path)
        jid = "b" * 32
        logging.getLogger("fabulim.fila").info("iniciou", extra={"job_id": jid})
        logging.getLogger("fabulim.fila").error("quebrou")
        logging.getLogger("fabulim.app").info("pronto")
        assert [e["msg"] for e in ler_logs(tmp_path, servico="fila")] == ["iniciou", "quebrou"]
        assert [e["msg"] for e in ler_logs(tmp_path, nivel="error")] == ["quebrou"]
        assert [e["msg"] for e in ler_logs(tmp_path, job_id=jid)] == ["iniciou"]
        assert len(ler_logs(tmp_path, limite=2)) == 2

    def test_sem_arquivo_devolve_lista_vazia(self, tmp_path: Path) -> None:
        assert ler_logs(tmp_path / "nao-existe") == []

    def test_ignora_linhas_corrompidas(self, tmp_path: Path) -> None:
        (tmp_path / "app.jsonl").write_text(
            'lixo\n{"level":"INFO","service":"a","msg":"ok"}\n[1,2]\n', encoding="utf-8"
        )
        assert [e["msg"] for e in ler_logs(tmp_path)] == ["ok"]

    def test_le_so_o_fim_de_arquivos_grandes(self, tmp_path: Path) -> None:
        linhas = "\n".join(json.dumps({"level": "INFO", "service": "s", "msg": f"m{i}"}) for i in range(5000))
        (tmp_path / "app.jsonl").write_text(linhas + "\n", encoding="utf-8")
        saida = ler_logs(tmp_path, limite=3, max_bytes=2000)
        assert [e["msg"] for e in saida] == ["m4997", "m4998", "m4999"]
