"""Testes do handler bespoke PERF-004 "arquivo carregado completamente
em memória" (`perf004_arquivo_sem_streaming.py`)."""

from __future__ import annotations

from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.perf004_arquivo_sem_streaming import avaliar_perf004
from batman_os.foundation.types import MissionId, StepId, TenantId, agora


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _regra() -> dict[str, object]:
    return {
        "codigo": "PERF-004",
        "agente": "performance-engineer",
        "severidade": "medium",
        "categoria": "memoria",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
    }


class TestArquivoSemStreaming:
    def test_dispara_para_file_read_completo(self) -> None:
        entrada = {
            "caminho": "api/routers/upload.py",
            "conteudo": "conteudo = file.read()\n",
            "regra": _regra(),
        }
        saida = avaliar_perf004(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_dispara_para_read_csv_sem_chunksize(self) -> None:
        entrada = {
            "caminho": "api/routers/upload.py",
            "conteudo": "df = pd.read_csv(f)\n",
            "regra": _regra(),
        }
        saida = avaliar_perf004(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_read_csv_com_chunksize(self) -> None:
        entrada = {
            "caminho": "api/routers/upload.py",
            "conteudo": "df = pd.read_csv(f, chunksize=1000)\n",
            "regra": _regra(),
        }
        saida = avaliar_perf004(entrada, _contexto())
        assert saida["achados"] == []

    def test_file_read_suprime_a_checagem_de_read_csv(self) -> None:
        # legado tem `continue` apos o 1o achado -- so 1 achado mesmo com
        # AMBOS os padroes presentes no mesmo arquivo, e a mensagem e a
        # do file.read(), nao a do pd.read_csv
        entrada = {
            "caminho": "api/routers/upload.py",
            "conteudo": "a = file.read()\ndf = pd.read_csv(f)\n",
            "regra": _regra(),
        }
        saida = avaliar_perf004(entrada, _contexto())
        assert len(saida["achados"]) == 1
        assert "via pd.read_csv" not in saida["achados"][0]["descricao"]

    def test_nao_dispara_sem_nenhum_padrao(self) -> None:
        entrada = {
            "caminho": "api/routers/x.py",
            "conteudo": "def listar(): pass\n",
            "regra": _regra(),
        }
        saida = avaliar_perf004(entrada, _contexto())
        assert saida["achados"] == []
