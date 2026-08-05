"""Regressão da recalibração de FUI-011, QA-011 e SD-010 (resíduo da triagem
`GOV_BATMANOS_TRIAGEM_19_HIGH01` do radar-preditivo, 2026-08-05).

As três regras produziam 11 dos 17 HIGH que mantinham o portão do radar
vermelho, e a triagem provou achado a achado que eram falso positivo. Cada
teste aqui existe em par: um caso que a regra **ainda tem de pegar** e um que
ela **precisa deixar passar** — recalibrar só com o caso negativo é cegar a
regra e chamar de conserto.

O padrão comum às três: o regex mirava a **grafia** (a palavra 'watchlist', um
identificador de preço, um domínio de e-mail) em vez do **fenômeno** (o status
de um sinal, a ausência de guarda que o compilador não cubra, PII de pessoa
real). Regra que persegue grafia encontra ruído com probabilidade 1.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.regex_sobre_conteudo import RegraSpec, avaliar_regra_regex
from batman_os.cli.descoberta_arquivos import entradas_para_regra
from batman_os.foundation.types import MissionId, StepId, TenantId, agora

_SPECS = Path(__file__).resolve().parents[3] / "src/batman_os/capabilities/rules/specs/lote_02"


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _spec(codigo: str) -> dict[str, Any]:
    dados: dict[str, Any] = json.loads((_SPECS / f"{codigo}.json").read_text(encoding="utf-8"))
    return dados


def _rodar(codigo: str, root: Path) -> list[str]:
    """Roda a regra real (spec versionado, não uma cópia) e devolve os arquivos com achado."""
    spec = _spec(codigo)
    regra = RegraSpec(**spec["regra"])
    achados: list[str] = []
    for entrada in entradas_para_regra(root, regra, spec["descoberta"]):
        for achado in avaliar_regra_regex(entrada, _contexto())["achados"]:
            achados.append(achado["arquivo"])
    return achados


def _componente_sem_guarda_visivel(root: Path) -> None:
    """Escreve um .tsx que o regex de FUI-011 considera desprotegido."""
    componente = root / "frontend/src/components/Preco.tsx"
    componente.parent.mkdir(parents=True, exist_ok=True)
    componente.write_text(
        "export function Preco({ s }: { s: Sinal }) {\n"
        "  return <span>{s.entry_price.toFixed(2)}</span>;\n"
        "}\n",
        encoding="utf-8",
    )


class TestFui011SilenciaSobStrict:
    """O compilador é uma checagem MAIS FORTE que o regex: com `strict` ligado,
    `strictNullChecks` reprova `.toFixed()` sobre valor possivelmente nulo, e
    `tsc --noEmit` já roda no portão. Perseguir as formas de guarda com regex é
    corrida perdida — o radar usava quatro (`!= null ?`, `!== null &&` em JSX,
    `?? 0` fora da janela de 80 chars, early return) e sempre haverá uma quinta.
    """

    def test_dispara_quando_o_projeto_nao_liga_strict(self, tmp_path: Path) -> None:
        _componente_sem_guarda_visivel(tmp_path)
        (tmp_path / "frontend/tsconfig.app.json").write_text(
            '{"compilerOptions": {"strict": false}}', encoding="utf-8"
        )
        (tmp_path / "frontend/tsconfig.json").write_text('{"files": []}', encoding="utf-8")

        assert _rodar("FUI-011", tmp_path) == ["frontend/src/components/Preco.tsx"]

    def test_dispara_quando_nao_ha_tsconfig_nenhum(self, tmp_path: Path) -> None:
        """Ausência de tsconfig conta como ausência de proteção, nunca como
        'nada a avaliar' — é o contrato de `vazio_se_ausente`."""
        _componente_sem_guarda_visivel(tmp_path)

        assert _rodar("FUI-011", tmp_path) == ["frontend/src/components/Preco.tsx"]

    def test_silencia_com_strict_no_tsconfig_app(self, tmp_path: Path) -> None:
        _componente_sem_guarda_visivel(tmp_path)
        (tmp_path / "frontend/tsconfig.app.json").write_text(
            '{"compilerOptions": {"strict": true}}', encoding="utf-8"
        )

        assert _rodar("FUI-011", tmp_path) == []

    def test_silencia_com_strict_no_tsconfig_da_raiz(self, tmp_path: Path) -> None:
        """Projeto que não usa o split app/node do Vite declara na raiz."""
        _componente_sem_guarda_visivel(tmp_path)
        (tmp_path / "frontend/tsconfig.json").write_text(
            '{"compilerOptions": {"strict": true}}', encoding="utf-8"
        )

        assert _rodar("FUI-011", tmp_path) == []

    def test_silencia_com_strictnullchecks_sem_strict_geral(self, tmp_path: Path) -> None:
        """`strictNullChecks` sozinho já entrega o invariante que importa aqui."""
        _componente_sem_guarda_visivel(tmp_path)
        (tmp_path / "frontend/tsconfig.app.json").write_text(
            '{"compilerOptions": {"strictNullChecks": true}}', encoding="utf-8"
        )

        assert _rodar("FUI-011", tmp_path) == []


class TestQa011DistingueSinteticoDeReal:
    """A regra procura PII **real** em fixture. CPF com dígitos todos iguais
    reprova no dígito verificador (é sintético por construção) e e-mail com
    prefixo de fixture não é dado de pessoa — nenhum dos dois é PII.
    """

    def _fixture(self, root: Path, conteudo: str) -> None:
        arq = root / "tests/test_x.py"
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(conteudo, encoding="utf-8")

    def test_dispara_em_cpf_valido_de_pessoa(self, tmp_path: Path) -> None:
        self._fixture(tmp_path, 'CPF = "529.982.247-25"\n')

        assert _rodar("QA-011", tmp_path) == ["tests/test_x.py"]

    def test_silencia_em_cpf_com_digitos_todos_iguais(self, tmp_path: Path) -> None:
        self._fixture(tmp_path, 'CPF = "999.999.999-99"\nOUTRO = "111.111.111-11"\n')

        assert _rodar("QA-011", tmp_path) == []

    def test_dispara_em_email_de_pessoa_com_provedor_real(self, tmp_path: Path) -> None:
        self._fixture(tmp_path, 'EMAIL = "joao.silva@gmail.com"\n')

        assert _rodar("QA-011", tmp_path) == ["tests/test_x.py"]

    def test_silencia_em_email_com_prefixo_de_fixture(self, tmp_path: Path) -> None:
        """`teste50@gmail.com` era 1 dos 19 HIGH — e é a própria lista de
        isenção de plano que o teste do radar existe para exercitar."""
        self._fixture(
            tmp_path,
            'A = "teste50@gmail.com"\nB = "testeyeud@gmail.com"\nC = "example.user@gmail.com"\n',
        )

        assert _rodar("QA-011", tmp_path) == []

    def test_continua_pegando_cartao_de_credito(self, tmp_path: Path) -> None:
        """A recalibração mexeu em CPF e e-mail; o ramo de PAN segue intacto."""
        self._fixture(tmp_path, 'CARD = "4111 1111 1111 1111"\n')

        assert _rodar("QA-011", tmp_path) == ["tests/test_x.py"]


class TestSd010OlhaOStatusNaoAPalavra:
    """A regra mira o STATUS `WATCHLIST` de um sinal renderizado sem badge. O
    pattern era a palavra solta 'watchlist' com ignore_case, e os 3 HIGH que
    produziu no radar eram todos ruído: um comentário, a página da watchlist do
    usuário e a watchlist forward do admin — três conceitos que só dividem o
    nome com o status. `ignore_case` fica DESLIGADO de propósito: é a caixa que
    separa o enum da palavra comum.
    """

    def _pagina(self, root: Path, conteudo: str) -> None:
        arq = root / "frontend/src/pages/Tela.tsx"
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(conteudo, encoding="utf-8")

    def test_dispara_em_status_watchlist_sem_badge(self, tmp_path: Path) -> None:
        self._pagina(tmp_path, "if (sinal.status === 'WATCHLIST') return <Card preco={p} />\n")

        assert _rodar("SD-010", tmp_path) == ["frontend/src/pages/Tela.tsx"]

    def test_silencia_quando_ha_badge_de_espera(self, tmp_path: Path) -> None:
        """A mitigação continua valendo — não foi a parte quebrada da regra."""
        self._pagina(
            tmp_path,
            "if (s.status === 'WATCHLIST') return <Badge>Aguarda abertura</Badge>\n",
        )

        assert _rodar("SD-010", tmp_path) == []

    def test_silencia_na_pagina_da_feature_watchlist_do_usuario(self, tmp_path: Path) -> None:
        """`Watchlist.tsx` do radar: a lista de ativos que o usuário acompanha
        não tem relação com o status de um sinal."""
        self._pagina(
            tmp_path,
            "import { watchlistApi, WatchlistItem } from '../api/watchlist'\n"
            "export default function WatchlistPage() {\n"
            "  const [items, setItems] = useState<WatchlistItem[]>([])\n"
            "  return <div>{items.map(i => <Row key={i.id} />)}</div>\n"
            "}\n",
        )

        assert _rodar("SD-010", tmp_path) == []

    def test_silencia_em_comentario_que_so_cita_o_nome(self, tmp_path: Path) -> None:
        """O caso de `MercadoB3.tsx:15` — uma lista de páginas consumidoras
        dentro de um comentário disparava HIGH."""
        self._pagina(
            tmp_path,
            "// nenhum consumidor existente (MercadoHoje, Watchlist, Home, Radar)\n"
            "// precisou mudar.\nexport default function MercadoB3() { return null }\n",
        )

        assert _rodar("SD-010", tmp_path) == []
