"""Migrações do esquema, em ordem. Nunca edite uma migração já publicada: acrescente uma nova."""

from __future__ import annotations

MIGRACOES: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            params TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            position REAL NOT NULL,
            progress REAL NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',
            eta_seconds REAL,
            result TEXT,
            error TEXT,
            heavy INTEGER NOT NULL DEFAULT 1,
            attempts INTEGER NOT NULL DEFAULT 0,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            pause_requested INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_jobs_fila ON jobs (status, priority DESC, position);

        CREATE TABLE job_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
            ts TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL
        );
        CREATE INDEX idx_job_logs_job ON job_logs (job_id, id);

        CREATE TABLE benchmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            status TEXT NOT NULL,
            model TEXT,
            seconds REAL,
            metrics TEXT NOT NULL DEFAULT '{}',
            detail TEXT,
            fingerprint TEXT,
            measured_at TEXT NOT NULL
        );
        CREATE INDEX idx_benchmarks_task ON benchmarks (task, id DESC);
        """,
    ),
    (
        2,
        """
        -- Tudo o que o estúdio gera ou recebe (imagens, recortes, áudios, vídeos, legendas) vira uma mídia.
        CREATE TABLE midias (
            id TEXT PRIMARY KEY,
            tipo TEXT NOT NULL,
            papel TEXT NOT NULL,
            caminho TEXT NOT NULL,
            miniatura TEXT,
            formato TEXT,
            largura INTEGER,
            altura INTEGER,
            duracao_s REAL,
            tamanho_bytes INTEGER NOT NULL DEFAULT 0,
            dono_tipo TEXT,
            dono_id TEXT,
            pai_id TEXT REFERENCES midias (id) ON DELETE SET NULL,
            prompt TEXT,
            prompt_tecnico TEXT,
            negativo TEXT,
            estilo TEXT,
            seed INTEGER,
            modelo TEXT,
            metadados TEXT NOT NULL DEFAULT '{}',
            job_id TEXT,
            criado_em TEXT NOT NULL
        );
        CREATE INDEX idx_midias_dono ON midias (dono_tipo, dono_id, papel);
        CREATE INDEX idx_midias_tipo ON midias (tipo, criado_em DESC);

        CREATE TABLE personagens (
            id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            estilo TEXT NOT NULL,
            ficha TEXT NOT NULL DEFAULT '{}',
            prompt_original TEXT NOT NULL DEFAULT '',
            prompt_tecnico TEXT NOT NULL DEFAULT '',
            voz TEXT NOT NULL DEFAULT '{}',
            estado TEXT NOT NULL,
            imagem_principal_id TEXT REFERENCES midias (id) ON DELETE SET NULL,
            versao INTEGER NOT NULL DEFAULT 1,
            origem TEXT NOT NULL DEFAULT 'prompt',
            origem_id TEXT,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        );
        CREATE UNIQUE INDEX idx_personagens_nome ON personagens (lower(nome), estilo);

        CREATE TABLE projetos (
            id TEXT PRIMARY KEY,
            titulo TEXT NOT NULL,
            formato TEXT NOT NULL,
            idioma TEXT NOT NULL,
            estilo TEXT NOT NULL,
            duracao_alvo_s INTEGER NOT NULL,
            enredo TEXT NOT NULL DEFAULT '{}',
            personagens TEXT NOT NULL DEFAULT '[]',
            etapa TEXT NOT NULL,
            aprovacoes TEXT NOT NULL DEFAULT '{}',
            musica TEXT NOT NULL DEFAULT '{}',
            configuracoes TEXT NOT NULL DEFAULT '{}',
            origem_id TEXT,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        );

        CREATE TABLE cenas (
            id TEXT PRIMARY KEY,
            projeto_id TEXT NOT NULL REFERENCES projetos (id) ON DELETE CASCADE,
            ordem INTEGER NOT NULL,
            dados TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL,
            versao INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        );
        CREATE INDEX idx_cenas_projeto ON cenas (projeto_id, ordem);

        CREATE TABLE cena_versoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cena_id TEXT NOT NULL REFERENCES cenas (id) ON DELETE CASCADE,
            versao INTEGER NOT NULL,
            dados TEXT NOT NULL,
            motivo TEXT NOT NULL,
            criado_em TEXT NOT NULL
        );
        CREATE INDEX idx_cena_versoes ON cena_versoes (cena_id, versao);

        CREATE TABLE historico_prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            texto TEXT NOT NULL,
            criado_em TEXT NOT NULL
        );
        CREATE INDEX idx_historico_prompts ON historico_prompts (tipo, id DESC);
        """,
    ),
)
