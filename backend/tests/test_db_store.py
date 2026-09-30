"""Banco (migrações, transações) e persistência da fila."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db import Database
from app.db.migrations import MIGRACOES
from app.jobs.models import ATIVOS, JobStatus
from app.jobs.store import JobStore


@pytest.fixture
def db(tmp_path: Path) -> Database:
    banco = Database(tmp_path / "t.db")
    banco.migrar()
    return banco


@pytest.fixture
def store(db: Database) -> JobStore:
    return JobStore(db)


class TestDatabase:
    def test_migracao_cria_tabelas_e_e_idempotente(self, tmp_path: Path) -> None:
        banco = Database(tmp_path / "novo" / "t.db")
        ultima = MIGRACOES[-1][0]
        assert banco.migrar() == ultima
        assert banco.migrar() == ultima
        with banco.transaction() as c:
            tabelas = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            versoes = c.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert {"jobs", "job_logs", "benchmarks", "schema_migrations"} <= tabelas
        assert {"midias", "personagens", "projetos", "cenas", "cena_versoes", "historico_prompts"} <= tabelas
        assert versoes == len(MIGRACOES)

    def test_as_versoes_das_migracoes_sao_sequenciais(self) -> None:
        assert [v for v, _ in MIGRACOES] == list(range(1, len(MIGRACOES) + 1))

    def test_atualiza_um_banco_que_so_tinha_a_primeira_migracao(self, tmp_path: Path) -> None:
        caminho = tmp_path / "antigo.db"
        conexao = sqlite3.connect(caminho)
        conexao.executescript(MIGRACOES[0][1])
        conexao.executescript(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
            "INSERT INTO schema_migrations VALUES (1, 'antes');"
        )
        conexao.commit()
        conexao.close()
        banco = Database(caminho)
        assert banco.migrar() == MIGRACOES[-1][0]
        with banco.transaction() as c:
            assert c.execute("SELECT COUNT(*) FROM midias").fetchone()[0] == 0

    def test_nome_de_personagem_e_unico_por_estilo(self, db: Database) -> None:
        def inserir(id_: str, nome: str, estilo: str) -> None:
            with db.transaction() as c:
                c.execute(
                    "INSERT INTO personagens (id, nome, estilo, estado, criado_em, atualizado_em)"
                    " VALUES (?, ?, ?, 'rascunho', 't', 't')",
                    (id_, nome, estilo),
                )

        inserir("a", "Lila", "2D")
        inserir("b", "Lila", "3D")  # o mesmo nome no outro estilo é a versão 3D
        with pytest.raises(sqlite3.IntegrityError):
            inserir("c", "LILA", "2D")

    def test_apagar_projeto_apaga_cenas_e_versoes(self, db: Database) -> None:
        with db.transaction() as c:
            c.execute(
                "INSERT INTO projetos (id, titulo, formato, idioma, estilo, duracao_alvo_s, etapa, criado_em, atualizado_em)"
                " VALUES ('p', 'T', 'short', 'pt-BR', '2D', 60, 'enredo', 't', 't')"
            )
            c.execute(
                "INSERT INTO cenas (id, projeto_id, ordem, status, criado_em, atualizado_em) VALUES ('c', 'p', 1, 'pendente', 't', 't')"
            )
            c.execute(
                "INSERT INTO cena_versoes (cena_id, versao, dados, motivo, criado_em) VALUES ('c', 1, '{}', 'nova', 't')"
            )
            c.execute("DELETE FROM projetos WHERE id = 'p'")
            assert c.execute("SELECT COUNT(*) FROM cenas").fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM cena_versoes").fetchone()[0] == 0

    def test_usa_wal(self, db: Database) -> None:
        with db.transaction() as c:
            assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_rollback_em_erro(self, db: Database) -> None:
        with pytest.raises(RuntimeError), db.transaction() as c:
            c.execute("INSERT INTO benchmarks (task, status, measured_at) VALUES ('x', 'ok', 'agora')")
            raise RuntimeError("falha no meio")
        with db.transaction() as c:
            assert c.execute("SELECT COUNT(*) FROM benchmarks").fetchone()[0] == 0

    def test_chaves_estrangeiras_ligadas(self, db: Database) -> None:
        with pytest.raises(sqlite3.IntegrityError), db.transaction() as c:
            c.execute("INSERT INTO job_logs (job_id, ts, level, message) VALUES ('nao-existe', 't', 'INFO', 'm')")

    def test_tamanho(self, db: Database, tmp_path: Path) -> None:
        assert db.tamanho_bytes() > 0
        assert Database(tmp_path / "inexistente.db").tamanho_bytes() == 0


class TestJobStore:
    def test_criar_e_obter(self, store: JobStore) -> None:
        job = store.criar("demo.sleep", "Teste", {"seconds": 1})
        assert job.status == JobStatus.QUEUED
        assert job.params == {"seconds": 1}
        assert len(job.id) == 32
        assert store.obter(job.id) == job
        assert store.obter("0" * 32) is None

    def test_ordem_fifo_prioridade_e_reservar(self, store: JobStore) -> None:
        a = store.criar("k", "A")
        b = store.criar("k", "B")
        c = store.criar("k", "C", priority=5)
        ordem = [store.reservar_proximo() for _ in range(3)]
        assert [j.id for j in ordem if j] == [c.id, a.id, b.id]
        assert store.reservar_proximo() is None

    def test_reservar_marca_executando_e_conta_tentativas(self, store: JobStore) -> None:
        criado = store.criar("k", "A")
        job = store.reservar_proximo()
        assert job is not None
        assert job.id == criado.id and job.status == JobStatus.RUNNING
        assert job.attempts == 1 and job.started_at is not None

    def test_progresso_so_vale_para_job_ativo(self, store: JobStore) -> None:
        job = store.criar("k", "A")
        assert store.atualizar_progresso(job.id, 0.5, "meio", 3.0).progress == 0  # type: ignore[union-attr]  # ainda na fila
        store.reservar_proximo()
        atualizado = store.atualizar_progresso(job.id, 1.7, "quase", 3.0)
        assert atualizado is not None and atualizado.progress == 1.0 and atualizado.message == "quase"
        assert atualizado.eta_seconds == 3.0

    def test_finalizar_done_failed_e_mascara_do_erro(self, store: JobStore) -> None:
        a = store.criar("k", "A")
        store.reservar_proximo()
        feito = store.finalizar(a.id, JobStatus.DONE, resultado={"x": 1}, mensagem="Concluído")
        assert feito is not None and feito.status == JobStatus.DONE and feito.progress == 1.0
        assert feito.result == {"x": 1} and feito.finished_at is not None
        b = store.criar("k", "B")
        store.reservar_proximo()
        falhou = store.finalizar(b.id, JobStatus.FAILED, erro="deu ruim com sk-ant-abcdefghijk123")
        assert falhou is not None and "sk-ant" not in (falhou.error or "")

    def test_cancelar_na_fila_e_em_execucao(self, store: JobStore) -> None:
        na_fila = store.criar("k", "fila")
        cancelado = store.cancelar(na_fila.id)
        assert cancelado is not None and cancelado.status == JobStatus.CANCELED
        rodando = store.criar("k", "rodando")
        store.reservar_proximo()
        pedido = store.cancelar(rodando.id)
        assert pedido is not None and pedido.status == JobStatus.RUNNING and pedido.cancel_requested is True

    def test_cancelar_job_finalizado_nao_muda_nada(self, store: JobStore) -> None:
        j = store.criar("k", "A")
        store.cancelar(j.id)
        assert store.cancelar(j.id).status == JobStatus.CANCELED  # type: ignore[union-attr]

    def test_pausar_e_retomar_na_fila(self, store: JobStore) -> None:
        j = store.criar("k", "A")
        pausado = store.pausar(j.id)
        assert pausado is not None and pausado.status == JobStatus.PAUSED and not pausado.retido_pelo_worker
        assert store.reservar_proximo() is None  # pausado não é pego pelo worker
        retomado = store.retomar(j.id)
        assert retomado is not None and retomado.status == JobStatus.QUEUED

    def test_pausar_em_execucao_so_pede(self, store: JobStore) -> None:
        j = store.criar("k", "A")
        store.reservar_proximo()
        pedido = store.pausar(j.id)
        assert pedido is not None and pedido.status == JobStatus.RUNNING and pedido.pause_requested
        assert store.marcar_pausado(j.id).retido_pelo_worker  # type: ignore[union-attr]
        assert store.retomar(j.id).pause_requested is False  # type: ignore[union-attr]
        assert store.marcar_executando(j.id).status == JobStatus.RUNNING  # type: ignore[union-attr]

    def test_cancelar_job_segurado_pelo_worker_so_pede(self, store: JobStore) -> None:
        j = store.criar("k", "A")
        store.reservar_proximo()
        store.pausar(j.id)
        store.marcar_pausado(j.id)
        assert store.cancelar(j.id).cancel_requested is True  # type: ignore[union-attr]

    def test_reordenar_so_mexe_no_que_esta_na_fila(self, store: JobStore) -> None:
        a, b, c = (store.criar("k", n) for n in "ABC")
        rodando = store.reservar_proximo()  # A vira executando
        assert rodando is not None and rodando.id == a.id
        ordem = store.reordenar([c.id, a.id, b.id, "0" * 32])
        assert [j.id for j in ordem] == [a.id, c.id, b.id]  # executando primeiro, depois a nova ordem
        assert store.reservar_proximo().id == c.id  # type: ignore[union-attr]

    def test_listar_ativos_primeiro_e_finalizados_do_mais_novo(self, store: JobStore) -> None:
        velho = store.criar("k", "velho")
        store.reservar_proximo()
        store.finalizar(velho.id, JobStatus.DONE)
        novo = store.criar("k", "novo")
        store.reservar_proximo()
        store.finalizar(novo.id, JobStatus.FAILED, erro="x")
        fila = store.criar("k", "fila")
        ids = [j.id for j in store.listar()]
        assert ids == [fila.id, novo.id, velho.id]
        assert [j.id for j in store.listar(ATIVOS)] == [fila.id]
        assert store.contagens() == {"queued": 1, "failed": 1, "done": 1}

    def test_limpar_finalizados(self, store: JobStore) -> None:
        a = store.criar("k", "A")
        store.reservar_proximo()
        store.finalizar(a.id, JobStatus.DONE)
        vivo = store.criar("k", "B")
        assert store.limpar_finalizados() == 1
        assert [j.id for j in store.listar()] == [vivo.id]

    def test_recuperar_apos_reinicio(self, store: JobStore) -> None:
        rodando = store.criar("k", "rodando")
        store.reservar_proximo()
        store.atualizar_progresso(rodando.id, 0.6, "no meio", 10.0)
        pausado = store.criar("k", "pausado")
        store.pausar(pausado.id)
        assert store.recuperar_interrompidos() == 1
        voltou = store.obter(rodando.id)
        assert voltou is not None and voltou.status == JobStatus.QUEUED and voltou.progress == 0
        assert "reinício" in voltou.message
        assert store.obter(pausado.id).status == JobStatus.PAUSED  # type: ignore[union-attr]

    def test_logs_do_job_com_mascara_e_limite(self, store: JobStore) -> None:
        j = store.criar("k", "A")
        for i in range(5):
            store.registrar_log(j.id, "info", f"linha {i}")
        store.registrar_log(j.id, "warning", "chave sk-ant-abcdefghijk")
        logs = store.logs(j.id, limite=3)
        assert [entrada.message for entrada in logs] == ["linha 3", "linha 4", "chave ***"]  # as 3 últimas, em ordem
        assert logs[-1].level == "WARNING"

    def test_sobrevive_a_um_novo_store_no_mesmo_banco(self, db: Database) -> None:
        j = JobStore(db).criar("k", "persistente", {"a": 1})
        assert JobStore(db).obter(j.id) == j
