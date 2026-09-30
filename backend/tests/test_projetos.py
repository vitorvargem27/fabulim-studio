"""Projetos: repositório (com versões de cena), dados da cena e regras de invalidação, e o roteiro (IA e modo simples)."""

from __future__ import annotations

from typing import Any

import pytest

from app.container import Servicos
from app.erros import ErroParaOUsuario
from app.personagens.repositorio import Personagem
from app.projetos.cenas import DadosDaCena, aplicar_edicao, cena_valida
from app.projetos.repositorio import ETAPAS, RepositorioProjetos, proporcao_do_formato
from app.projetos.roteiro import (
    ESQUEMA_DO_ROTEIRO,
    SISTEMA_DO_ROTEIRO,
    _agrupar,
    achar_personagem,
    normalizar_roteiro,
    numero_de_cenas,
    personagens_citados,
    quebrar_frases,
    roteiro_por_ia,
    roteiro_simples,
)
from app.prompts.formatos import FichaEnredo

from .fakes_motores import ContextoDeTeste, TextoFalso


@pytest.fixture
def repo(servicos: Servicos) -> RepositorioProjetos:
    return servicos.projetos


def _projeto(repo: RepositorioProjetos, **campos: Any) -> Any:
    dados: dict[str, Any] = {
        "titulo": "A chuva",
        "formato": "short",
        "idioma": "pt-BR",
        "estilo": "2D",
        "duracao_alvo_s": 60,
        "enredo": {"story": "Lila brinca."},
        "personagens": ["p1"],
    }
    dados.update(campos)
    return repo.criar(**dados)


class TestProjetos:
    def test_criar_obter_e_listar(self, repo: RepositorioProjetos) -> None:
        p = _projeto(repo, musica={"style": "alegre"}, configuracoes={"fps": 24})
        assert p.etapa == "enredo" and p.aprovacoes == {} and p.proporcao == "9:16" and p.origem_id is None
        assert repo.obter(p.id) == p and repo.obter("0" * 32) is None
        api = p.para_api()
        assert api["title"] == "A chuva" and api["aspect"] == "9:16" and api["stage"] == "enredo"
        assert api["music"] == {"style": "alegre"} and api["settings"] == {"fps": 24} and api["character_ids"] == ["p1"]
        assert [x.id for x in repo.listar()] == [p.id]

    def test_formato_e_proporcao(self) -> None:
        assert proporcao_do_formato("short") == "9:16" and proporcao_do_formato("longo") == "16:9"
        assert ETAPAS == ("enredo", "roteiro", "storyboard", "animacao", "audio", "montagem", "revisao")

    def test_atualizar_so_o_que_foi_pedido(self, repo: RepositorioProjetos) -> None:
        p = _projeto(repo)
        novo = repo.atualizar(p.id, titulo="Novo", aprovacoes={"enredo": True}, etapa="roteiro", duracao_alvo_s=90)
        assert novo is not None and novo.titulo == "Novo" and novo.aprovacoes == {"enredo": True}
        assert novo.etapa == "roteiro" and novo.duracao_alvo_s == 90 and novo.formato == "short"
        assert novo.atualizado_em >= p.atualizado_em
        assert repo.atualizar(p.id) is not None and repo.atualizar("0" * 32, titulo="x") is None

    def test_campos_e_etapas_invalidos(self, repo: RepositorioProjetos) -> None:
        p = _projeto(repo)
        with pytest.raises(ValueError, match="desconhecido"):
            repo.atualizar(p.id, id="outro")
        with pytest.raises(ValueError, match="etapa desconhecida"):
            repo.atualizar(p.id, etapa="voando")

    def test_apagar_leva_as_cenas_e_as_versoes(self, repo: RepositorioProjetos, servicos: Servicos) -> None:
        p = _projeto(repo)
        cena = repo.criar_cena(p.id, {"title": "a"})
        repo.atualizar_cena(cena.id, {"title": "b"}, "editada")
        assert repo.remover(p.id) is True and repo.remover(p.id) is False
        assert repo.cena(cena.id) is None
        with servicos.db.transaction() as c:
            assert c.execute("SELECT COUNT(*) FROM cena_versoes").fetchone()[0] == 0

    def test_quem_usa_o_personagem_e_as_variantes(self, repo: RepositorioProjetos) -> None:
        a = _projeto(repo, personagens=["p1", "p2"])
        b = _projeto(repo, personagens=["p2"], origem_id=a.id, titulo="English")
        assert {p.id for p in repo.usam_o_personagem("p2")} == {a.id, b.id}
        assert [p.id for p in repo.usam_o_personagem("p1")] == [a.id]
        assert [p.id for p in repo.variantes_de(a.id)] == [b.id]


class TestCenas:
    def test_a_ordem_e_automatica_e_da_para_inserir_no_meio(self, repo: RepositorioProjetos) -> None:
        p = _projeto(repo)
        a, b = repo.criar_cena(p.id, {"title": "a"}), repo.criar_cena(p.id, {"title": "b"})
        meio = repo.criar_cena(p.id, {"title": "meio"}, ordem=2)
        assert [c.dados["title"] for c in repo.cenas(p.id)] == ["a", "meio", "b"]
        assert [c.ordem for c in repo.cenas(p.id)] == [1, 2, 3] and (a.ordem, b.ordem, meio.ordem) == (1, 2, 2)

    def test_editar_guarda_versao_nova_e_a_antiga_continua(self, repo: RepositorioProjetos) -> None:
        p = _projeto(repo)
        cena = repo.criar_cena(p.id, {"title": "v1"})
        assert cena.versao == 1 and cena.status == "pendente"
        editada = repo.atualizar_cena(cena.id, {"title": "v2"}, "editada pelo usuário")
        assert editada is not None and editada.versao == 2 and editada.dados == {"title": "v2"}
        versoes = repo.versoes_da_cena(cena.id)
        assert [(v["version"], v["data"]["title"], v["reason"]) for v in versoes] == [
            (2, "v2", "editada pelo usuário"),
            (1, "v1", "criada"),
        ]
        assert repo.atualizar_cena("0" * 32, {}, "x") is None

    def test_andamento_nao_vira_versao(self, repo: RepositorioProjetos) -> None:
        p = _projeto(repo)
        cena = repo.criar_cena(p.id, {"title": "v1"})
        atualizada = repo.atualizar_cena_sem_versao(cena.id, {"title": "v1", "clip": "pronto"})
        assert atualizada is not None and atualizada.versao == 1 and atualizada.dados["clip"] == "pronto"
        assert len(repo.versoes_da_cena(cena.id)) == 1 and repo.atualizar_cena_sem_versao("0" * 32, {}) is None

    def test_voltar_versao_cria_uma_versao_nova_sem_perder_nada(self, repo: RepositorioProjetos) -> None:
        p = _projeto(repo)
        cena = repo.criar_cena(p.id, {"title": "v1"})
        repo.atualizar_cena(cena.id, {"title": "v2"}, "editada")
        repo.atualizar_cena(cena.id, {"title": "v3"}, "editada")
        voltou = repo.restaurar_versao(cena.id, 1)
        assert voltou is not None and voltou.dados == {"title": "v1"} and voltou.versao == 4
        assert [v["version"] for v in repo.versoes_da_cena(cena.id)] == [4, 3, 2, 1]
        assert repo.versoes_da_cena(cena.id)[0]["reason"] == "voltou para a versão 1"
        assert repo.restaurar_versao(cena.id, 99) is None

    def test_reordenar_exige_exatamente_as_cenas_do_projeto(self, repo: RepositorioProjetos) -> None:
        p = _projeto(repo)
        a, b, c = (repo.criar_cena(p.id, {"title": t}) for t in "abc")
        repo.reordenar_cenas(p.id, [c.id, a.id, b.id])
        assert [x.dados["title"] for x in repo.cenas(p.id)] == ["c", "a", "b"]
        with pytest.raises(ValueError, match="exatamente"):
            repo.reordenar_cenas(p.id, [a.id, b.id])
        with pytest.raises(ValueError, match="exatamente"):
            repo.reordenar_cenas(p.id, [a.id, b.id, c.id, "0" * 32])

    def test_remover_uma_cena_fecha_o_buraco_na_ordem(self, repo: RepositorioProjetos) -> None:
        p = _projeto(repo)
        a, b, c = (repo.criar_cena(p.id, {"title": t}) for t in "abc")
        assert repo.remover_cena(b.id) is True and repo.remover_cena(b.id) is False
        assert [(x.dados["title"], x.ordem) for x in repo.cenas(p.id)] == [("a", 1), ("c", 2)]
        assert repo.apagar_todas_as_cenas(p.id) == 2 and repo.cenas(p.id) == []
        assert a.projeto_id == c.projeto_id == p.id

    def test_para_api(self, repo: RepositorioProjetos) -> None:
        p = _projeto(repo)
        api = repo.criar_cena(p.id, {"title": "a"}).para_api()
        assert api["project_id"] == p.id and api["order"] == 1 and api["version"] == 1 and api["data"] == {"title": "a"}


class TestDadosDaCena:
    def test_padroes_seguros(self) -> None:
        cena = cena_valida({})
        assert (cena.duration_s, cena.framing, cena.emotion, cena.camera) == (6.0, "medio", "neutro", "parada")
        assert cena.characters == [] and cena.dialogue == [] and cena.background is None and cena.approved == {}

    @pytest.mark.parametrize(
        ("dados", "campo"),
        [
            ({"duration_s": 1}, "duration_s"),
            ({"duration_s": 99}, "duration_s"),
            ({"framing": "colossal"}, "framing"),
            ({"emotion": "furioso"}, "emotion"),
            ({"narration": "x" * 601}, "narration"),
            ({"camera": "de-ponta-cabeca"}, "câmera"),
            ({"dialogue": [{"text": "x" * 401}]}, "dialogue"),
            ({"sfx": ["a"] * 7}, "sfx"),
        ],
    )
    def test_recusa_valores_invalidos_dizendo_o_campo(self, dados: dict[str, Any], campo: str) -> None:
        with pytest.raises(ValueError, match=campo):
            cena_valida(dados)

    def test_falas_narracao_primeiro_e_depois_os_dialogos(self) -> None:
        cena = cena_valida(
            {
                "narration": "Era uma vez.",
                "dialogue": [{"character_id": "p1", "text": "Oi!"}, {"character_id": "p2", "text": "  "}],
            }
        )
        assert [(f.character_id, f.text) for f in cena.falas()] == [(None, "Era uma vez."), ("p1", "Oi!")]
        assert cena_valida({"dialogue": [{"character_id": "p1", "text": "Oi"}]}).falas()[0].character_id == "p1"
        assert cena_valida({}).falas() == []

    def test_editar_a_narracao_pede_nova_aprovacao_do_roteiro_e_da_animacao_mas_nao_do_cenario(self) -> None:
        atual = cena_valida({"approved": {"roteiro": True, "storyboard": True, "animacao": True}}).model_dump()
        novos, mudou = aplicar_edicao(atual, {"narration": "Outra frase."})
        assert mudou == {"narration"} and novos["approved"] == {"roteiro": False, "storyboard": True, "animacao": False}

    def test_editar_o_cenario_refaz_tudo_dali_para_a_frente(self) -> None:
        atual = cena_valida({"approved": {"roteiro": True, "storyboard": True, "animacao": True}}).model_dump()
        for campo, valor in (
            ("visual", "uma praia"),
            ("characters", ["p1"]),
            ("framing", "proximo"),
            ("emotion", "feliz"),
        ):
            _, mudou = aplicar_edicao(atual, {campo: valor})
            novos, _ = aplicar_edicao(atual, {campo: valor})
            assert mudou == {campo} and novos["approved"] == {"roteiro": False, "storyboard": False, "animacao": False}

    def test_editar_para_o_mesmo_valor_nao_invalida_nada(self) -> None:
        atual = cena_valida({"narration": "Oi", "approved": {"roteiro": True, "animacao": True}}).model_dump()
        novos, mudou = aplicar_edicao(atual, {"narration": "Oi"})
        assert mudou == set() and novos["approved"] == {"roteiro": True, "animacao": True}

    def test_nao_deixa_editar_os_campos_de_controle_nem_inventar_campos(self) -> None:
        atual = cena_valida({}).model_dump()
        for campo in ("background", "clip", "approved", "keyframe_media_id", "candidates", "nao_existe"):
            with pytest.raises(ValueError, match="desconhecido"):
                aplicar_edicao(atual, {campo: 1})

    def test_edicao_invalida_e_recusada_com_mensagem(self) -> None:
        with pytest.raises(ValueError, match="duration_s"):
            aplicar_edicao(cena_valida({}).model_dump(), {"duration_s": 100})

    def test_dados_de_controle_sobrevivem_a_uma_edicao(self) -> None:
        atual = cena_valida({"background": {"media_id": "m1", "seed": 3}, "candidates": ["m1"]}).model_dump()
        novos, _ = aplicar_edicao(atual, {"title": "Novo"})
        assert novos["background"]["media_id"] == "m1" and novos["candidates"] == ["m1"]


def _personagem(id_: str, nome: str, **ficha: str) -> Personagem:
    return Personagem(id=id_, nome=nome, estilo="2D", ficha=ficha)


LILA = _personagem("id-lila", "Lila", species="coelha", personality="curiosa")
BENTO = _personagem("id-bento", "Bento", species="urso", personality="calmo")
BIBLIOTECA = [LILA, BENTO]


class TestNomes:
    def test_numero_de_cenas(self) -> None:
        assert (numero_de_cenas(60), numero_de_cenas(5), numero_de_cenas(180), numero_de_cenas(9999)) == (10, 1, 30, 40)

    @pytest.mark.parametrize(
        ("nome", "esperado"),
        [
            ("Lila", "id-lila"),
            ("  lila ", "id-lila"),
            ("BENTO", "id-bento"),
            ("Lila, a coelha", "id-lila"),
            ("bênto", "id-bento"),
            ("", None),
            ("Sol", None),
        ],
    )
    def test_achar_personagem(self, nome: str, esperado: str | None) -> None:
        achado = achar_personagem(nome, BIBLIOTECA)
        assert (achado.id if achado else None) == esperado

    def test_citados_no_texto(self) -> None:
        assert [p.nome for p in personagens_citados("Bento vê a lila no jardim.", BIBLIOTECA)] == ["Lila", "Bento"]
        assert personagens_citados("Ninguém aqui.", BIBLIOTECA) == []
        assert personagens_citados("A Lilás voa.", BIBLIOTECA) == []  # palavra inteira


BRUTO: dict[str, Any] = {
    "title": "A chuva do jardim",
    "scenes": [
        {
            "title": "O jardim",
            "duration_s": 5,
            "visual": "um jardim florido de manhã",
            "action": "Lila brinca",
            "setting": "jardim",
            "framing": "medio",
            "emotion": "feliz",
            "characters": ["Lila", "Sol"],
            "narration": "Era uma vez uma coelha chamada Lila.",
            "dialogue": [
                {"character": "Lila", "text": "Que dia lindo!"},
                {"character": "Bento", "text": "Vamos brincar?"},
            ],
            "lyrics": "",
            "sfx": ["pulo", "apito de trem"],
            "is_suggestion": False,
        },
        {
            "title": "A chuva",
            "duration_s": 20,
            "visual": "um céu nublado",
            "action": "as gotas caem",
            "characters": ["Bento"],
            "narration": "Começou a chover.",
            "dialogue": [{"character": "Narrador", "text": "Plim, plim!"}, {"character": "Fantasma", "text": "Buuu"}],
            "emotion": "furioso",
            "framing": "colossal",
            "is_suggestion": True,
        },
    ],
}


class TestNormalizarRoteiro:
    def test_nomes_viram_ids_e_o_roteiro_fica_valido(self) -> None:
        r = normalizar_roteiro(BRUTO, BIBLIOTECA, 10)
        assert r.origem == "ia" and r.titulo == "A chuva do jardim" and len(r.cenas) == 2
        a = r.cenas[0]
        assert a.characters == ["id-lila", "id-bento"]  # Bento entrou porque fala na cena; «Sol» não existe
        assert [(f.character_id, f.text) for f in a.dialogue] == [
            ("id-lila", "Que dia lindo!"),
            ("id-bento", "Vamos brincar?"),
        ]
        assert (a.title, a.setting, a.emotion, a.framing) == ("O jardim", "jardim", "feliz", "medio")
        assert any("Sol" in aviso and "não é um personagem" in aviso for aviso in r.avisos)

    def test_fala_de_narrador_ou_de_quem_nao_existe_vai_para_o_narrador(self) -> None:
        r = normalizar_roteiro(BRUTO, BIBLIOTECA, 10)
        b = r.cenas[1]
        assert [(f.character_id, f.text) for f in b.dialogue] == [(None, "Plim, plim!"), (None, "Buuu")]
        assert any("Fantasma" in aviso for aviso in r.avisos) and not any("Narrador" in a for a in r.avisos)

    def test_valores_invalidos_caem_no_padrao_e_sugestao_fica_marcada(self) -> None:
        b = normalizar_roteiro(BRUTO, BIBLIOTECA, 10).cenas[1]
        assert (b.emotion, b.framing) == ("neutro", "medio")
        assert b.suggestion is True and "não está na sua história" in b.suggestion_notes
        assert normalizar_roteiro(BRUTO, BIBLIOTECA, 10).cenas[0].suggestion is False

    def test_duracoes_ficam_entre_3_e_8_segundos(self) -> None:
        bruto = {"scenes": [{"duration_s": d, "narration": "x"} for d in (0.5, 2, 20, "abc", None)]}
        assert [c.duration_s for c in normalizar_roteiro(bruto, BIBLIOTECA, 27).cenas] == [3.0, 3.0, 8.0, 6.0, 6.0]

    def test_quando_a_soma_foge_da_meta_as_duracoes_se_aproximam_dela(self) -> None:
        bruto = {"scenes": [{"duration_s": 8, "narration": "x"} for _ in range(6)]}  # 48 s para uma meta de 24 s
        duracoes = [c.duration_s for c in normalizar_roteiro(bruto, BIBLIOTECA, 24).cenas]
        assert all(3.0 <= d <= 8.0 for d in duracoes) and sum(duracoes) == pytest.approx(24 * 1.0, abs=6)
        perto = [
            c.duration_s
            for c in normalizar_roteiro({"scenes": [{"duration_s": 6, "narration": "x"}] * 3}, BIBLIOTECA, 20).cenas
        ]
        assert perto == [6.0, 6.0, 6.0]  # já está perto da meta: não mexe

    def test_efeitos_sonoros_desconhecidos_saem(self) -> None:
        assert normalizar_roteiro(BRUTO, BIBLIOTECA, 10).cenas[0].sfx == ["boing"]

    def test_cameras_se_alternam(self) -> None:
        bruto = {"scenes": [{"narration": "x"} for _ in range(5)]}
        assert [c.camera for c in normalizar_roteiro(bruto, BIBLIOTECA, 30).cenas] == [
            "zoom_in",
            "panoramica_dir",
            "zoom_out",
            "panoramica_esq",
            "zoom_in",
        ]

    def test_o_filtro_de_conteudo_tira_o_trecho_e_avisa(self) -> None:
        bruto = {
            "scenes": [
                {
                    "narration": "Um monstro assustador apareceu.",
                    "visual": "uma floresta escura",
                    "dialogue": [
                        {"character": "Lila", "text": "Vou pegar a faca!"},
                        {"character": "Lila", "text": "Oi!"},
                    ],
                    "title": "Sangue no jardim",
                }
            ]
        }
        cena = normalizar_roteiro(bruto, BIBLIOTECA, 6)
        c = cena.cenas[0]
        assert c.narration == "" and c.title == "Cena 1" and [f.text for f in c.dialogue] == ["Oi!"]
        assert c.visual == "uma floresta escura" and len(cena.avisos) == 3
        assert all("Cena 1" in aviso and "removido" in aviso for aviso in cena.avisos)

    def test_titulo_igual_ao_do_video_ou_de_outra_cena_vira_o_comeco_da_narracao(self) -> None:
        # o modelo local costuma dar o título do vídeo a todas as cenas: cada cena precisa do seu
        bruto = {
            "title": "A Lila e a estrelinha",
            "scenes": [
                {
                    "title": "A Lila e a estrelinha",
                    "narration": "Lila encontra uma estrelinha pequenina chorando no jardim.",
                },
                {"title": "a lila e a ESTRELINHA", "action": "Lila pega a estrelinha no colo e as duas caminham."},
                {"title": "O bosque", "narration": "Elas caminham pelo bosque."},
                {"title": "O bosque", "narration": "Ao entardecer, o céu se abre."},
            ],
        }
        titulos = [c.title for c in normalizar_roteiro(bruto, BIBLIOTECA, 24, "Título do vídeo").cenas]
        assert titulos == [
            "Lila encontra uma estrelinha pequenina",
            "Lila pega a estrelinha",  # o corte em cinco palavras não termina em «no»
            "O bosque",
            "Ao entardecer, o céu",
        ]

    def test_titulo_do_video_passado_a_parte_tambem_conta(self) -> None:
        bruto = {"scenes": [{"title": "Meu vídeo", "narration": "Bento chega com o guarda-chuva."}]}
        assert normalizar_roteiro(bruto, BIBLIOTECA, 6, "meu video").cenas[0].title == "Bento chega com o guarda-chuva"

    def test_titulo_repetido_sem_texto_para_resumir_fica_como_cena_n(self) -> None:
        bruto = {"title": "Igual", "scenes": [{"title": "Igual"}, {"title": ""}]}
        assert [c.title for c in normalizar_roteiro(bruto, BIBLIOTECA, 12).cenas] == ["Cena 1", "Cena 2"]

    def test_resumo_igual_ao_de_outra_cena_leva_o_numero(self) -> None:
        bruto = {"scenes": [{"narration": "Lila pula."}, {"narration": "Lila pula. Bento ri."}]}
        assert [c.title for c in normalizar_roteiro(bruto, BIBLIOTECA, 12).cenas] == ["Lila pula", "Cena 2: Lila pula"]

    def test_lixo_nao_derruba(self) -> None:
        assert normalizar_roteiro({}, BIBLIOTECA, 60).cenas == []
        assert normalizar_roteiro({"scenes": "texto"}, BIBLIOTECA, 60).cenas == []
        assert (
            normalizar_roteiro({"scenes": [1, "a", None, {"narration": "ok"}]}, BIBLIOTECA, 6).cenas[0].narration
            == "ok"
        )
        assert (
            normalizar_roteiro({"scenes": [{"characters": "Lila", "dialogue": "oi", "sfx": "x"}]}, BIBLIOTECA, 6)
            .cenas[0]
            .characters
            == []
        )

    def test_o_resultado_e_um_dado_de_cena_completo(self) -> None:
        cena = normalizar_roteiro(BRUTO, BIBLIOTECA, 10).cenas[0]
        assert isinstance(cena, DadosDaCena) and cena_valida(cena.model_dump()).title == "O jardim"


class TestRoteiroPorIA:
    def _ficha(self, **campos: Any) -> FichaEnredo:
        base: dict[str, Any] = {
            "title": "A chuva",
            "story": "Lila brinca no jardim. Começa a chover. Bento chega com um guarda-chuva.",
            "characters": ["Lila", "Bento"],
            "theme": "dividir é bom",
            "settings": "jardim",
            "music": "cantiga da chuva",
        }
        return FichaEnredo.model_validate({**base, **campos})

    def test_pede_o_json_ao_modelo_com_a_historia_como_dado_e_as_regras_a_parte(self) -> None:
        motor = TextoFalso(respostas=[BRUTO])
        r = roteiro_por_ia(ContextoDeTeste(), motor, self._ficha(), BIBLIOTECA, 60, faixa=(0.1, 0.9))
        chamada = motor.chamadas[0]
        assert chamada["sistema"] == SISTEMA_DO_ROTEIRO and chamada["esquema"] == ESQUEMA_DO_ROTEIRO
        assert "Lila brinca no jardim" in chamada["dados"] and "Lila brinca" not in chamada["sistema"]
        assert "Título: A chuva" in chamada["dados"] and "Tema ou lição: dividir é bom" in chamada["dados"]
        instrucao = chamada["instrucao"]
        assert "60 segundos" in instrucao and "10 cenas" in instrucao and "português do Brasil" in instrucao
        assert "Lila (coelha, curiosa)" in instrucao and "Bento (urso, calmo)" in instrucao and "2D" in instrucao
        assert r.origem == "ia" and len(r.cenas) == 2

    def test_em_ingles(self) -> None:
        motor = TextoFalso(respostas=[BRUTO])
        roteiro_por_ia(ContextoDeTeste(), motor, self._ficha(language="en"), BIBLIOTECA, 30, faixa=(0, 1))
        assert "inglês" in motor.chamadas[0]["instrucao"]

    def test_a_regra_de_seguranca_esta_no_sistema(self) -> None:
        assert "ignore-as" in SISTEMA_DO_ROTEIRO and "is_suggestion=true" in SISTEMA_DO_ROTEIRO
        assert "2 a 5 anos" in SISTEMA_DO_ROTEIRO and "3 a 8 segundos" in SISTEMA_DO_ROTEIRO


class TestQuebrarFrases:
    def test_frases_paragrafos_e_pontuacao(self) -> None:
        texto = "Lila brinca. Que dia lindo!\n\nSera que vai chover? Vai…  Bento ri."
        assert quebrar_frases(texto) == ["Lila brinca.", "Que dia lindo!", "Sera que vai chover?", "Vai…", "Bento ri."]
        assert quebrar_frases("") == [] and quebrar_frases("  \n ") == []
        assert quebrar_frases("sem ponto final") == ["sem ponto final"]

    def test_agrupar_mantem_a_ordem_e_reparte_por_tamanho(self) -> None:
        frases = [f"Frase numero {i} com algum texto." for i in range(10)]
        blocos = _agrupar(frases, 4)
        assert [f for b in blocos for f in b] == frases and 2 <= len(blocos) <= 4
        assert max(len(b) for b in blocos) - min(len(b) for b in blocos) <= 2
        assert _agrupar(frases[:2], 9) == [[frases[0]], [frases[1]]] or len(_agrupar(frases[:2], 9)) <= 2
        assert _agrupar(["um"], 5) == [["um"]]


class TestRoteiroSimples:
    HISTORIA = (
        "Lila brinca no jardim. Ela pula na poça d'água. Começa a chover e Lila fica triste. "
        "Bento chega com um guarda-chuva. Os dois cantam juntos. Fim!"
    )

    def _ficha(self, **campos: Any) -> FichaEnredo:
        return FichaEnredo.model_validate(
            {"title": "A chuva", "story": self.HISTORIA, "settings": "jardim, casa", **campos}
        )

    def test_cada_trecho_vira_uma_cena_com_a_narracao_do_proprio_texto(self) -> None:
        r = roteiro_simples(self._ficha(), BIBLIOTECA, 18)
        assert r.origem == "simples" and r.titulo == "A chuva" and len(r.cenas) == 3
        assert " ".join(c.narration for c in r.cenas) == self.HISTORIA
        assert all(3.0 <= c.duration_s <= 8.0 for c in r.cenas) and "Roteiro simples" in r.avisos[0]
        assert [c.title for c in r.cenas] == ["Cena 1", "Cena 2", "Cena 3"]
        assert all(c.dialogue == [] for c in r.cenas)

    def test_personagens_citados_ou_todos(self) -> None:
        r = roteiro_simples(self._ficha(), BIBLIOTECA, 18)
        assert r.cenas[0].characters == ["id-lila"] or "id-lila" in r.cenas[0].characters
        sem_nomes = roteiro_simples(self._ficha(story="O dia estava lindo. Todos brincaram."), BIBLIOTECA, 12)
        assert all(c.characters == ["id-lila", "id-bento"] for c in sem_nomes.cenas)

    def test_cenarios_se_alternam_e_camera_varia(self) -> None:
        cenas = roteiro_simples(self._ficha(), BIBLIOTECA, 24).cenas
        assert [c.setting for c in cenas[:3]] == ["jardim", "casa", "jardim"]
        assert cenas[0].visual == "cenário de jardim" and cenas[0].camera != cenas[1].camera
        sem = roteiro_simples(self._ficha(settings=""), BIBLIOTECA, 12).cenas[0]
        assert sem.setting == "" and "alegre" in sem.visual

    def test_emocao_e_efeito_do_texto(self) -> None:
        cenas = roteiro_simples(
            self._ficha(story="Lila pula alto. Lila fica triste. Nossa, que surpresa! Bento dorme."), BIBLIOTECA, 24
        ).cenas
        assert [c.emotion for c in cenas] == ["feliz", "triste", "surpreso", "sono"]
        assert cenas[0].sfx == ["boing"] and cenas[1].sfx == []

    def test_historia_vazia_e_um_erro_claro(self) -> None:
        with pytest.raises(ErroParaOUsuario, match="história está vazia"):
            roteiro_simples(self._ficha(story="  "), BIBLIOTECA, 30)

    def test_no_maximo_uma_cena_por_frase(self) -> None:
        assert len(roteiro_simples(self._ficha(story="Só uma frase."), BIBLIOTECA, 60).cenas) == 1
