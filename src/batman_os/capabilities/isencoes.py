"""Isenções pré-registradas (allowlist) de achados do `batman scan` — Onda 1
do Plano Cobertura Total (`docs/PLANO_COBERTURA_TOTAL.md`, recalibração de
regras, S162).

Mecanismo NOVO: antes desta construção não existia forma de isentar um par
(código, arquivo) ANTES do achado nascer. O único mecanismo de "aceite"
existente é o inbox (`governance/inbox.py::InboxStore.defer`), que age
DEPOIS da detecção — exige rodar o scan com `--db`, o achado já ter sido
ingerido, e um humano rodar `batman inbox defer <id> --nota ...` (doutrina
"zero débito: só o humano defere"). Este módulo é o complemento simétrico
PRÉ-registrado: uma lista versionada no git, com motivo e validade
(expiração — nunca permanente), que impede um achado conhecido, revisado e
justificado de nascer a cada scan.

Doutrina preservada: cada entrada é uma decisão AUDITÁVEL e revisável em
code review (dado versionado, nunca um mecanismo silencioso de um agente
sozinho) — nunca substitui `batman inbox defer` para achados novos/não
revisados; serve só para casos pré-registrados e documentados no próprio
código-alvo (ex.: um módulo de pesquisa pura que já cita seu pré-registro
estatístico na docstring). Uma entrada com `validade` no passado deixa de
suprimir — o achado volta a nascer normalmente até alguém renovar ou
remover a entrada explicitamente (força revisão periódica, não é "para
sempre" por omissão).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel

_CAMINHO_PADRAO = Path(__file__).parent / "isencoes_pre_registradas.json"


class IsencaoPreRegistrada(BaseModel):
    codigo: str
    caminho: str  # relativo à raiz do repo-alvo, separador '/', como reportado no achado
    motivo: str
    validade: date  # AAAA-MM-DD -- expirada = deixa de suprimir


class AchadoComoAssinatura(Protocol):
    """Qualquer achado com `codigo`/`arquivo` — `AchadoScan`
    (`cli/scan_command.py`) satisfaz por duck typing; nenhum import
    cruzado necessário (evita `capabilities/` importar de `cli/`)."""

    codigo: str
    arquivo: str


_TAchado = TypeVar("_TAchado", bound=AchadoComoAssinatura)


def carregar_isencoes(caminho: Path | None = None) -> list[IsencaoPreRegistrada]:
    """Lê o arquivo de isenções (default: `isencoes_pre_registradas.json`
    ao lado deste módulo). Arquivo ausente = lista vazia (nenhuma isenção
    — comportamento seguro por padrão, nunca falha o scan)."""
    alvo = caminho if caminho is not None else _CAMINHO_PADRAO
    if not alvo.exists():
        return []
    bruto = json.loads(alvo.read_text(encoding="utf-8"))
    return [IsencaoPreRegistrada.model_validate(item) for item in bruto.get("isencoes", [])]


def _normalizar_caminho(caminho: str) -> str:
    return caminho.replace("\\", "/")


def esta_isento(
    codigo: str,
    caminho: str,
    isencoes: list[IsencaoPreRegistrada],
    *,
    hoje: date | None = None,
) -> bool:
    hoje_ = hoje if hoje is not None else date.today()
    alvo = _normalizar_caminho(caminho)
    return any(
        isencao.codigo == codigo
        and _normalizar_caminho(isencao.caminho) == alvo
        and isencao.validade >= hoje_
        for isencao in isencoes
    )


def filtrar_achados_isentos(
    achados: list[_TAchado],
    isencoes: list[IsencaoPreRegistrada],
    *,
    hoje: date | None = None,
) -> list[_TAchado]:
    """Remove de `achados` qualquer um cujo (código, arquivo) tenha uma
    isenção pré-registrada VÁLIDA (validade >= hoje). Acionado sempre no
    fim de `executar_scan` — uma isenção expirada silenciosamente volta a
    valer (o achado reaparece), sem precisar de nenhuma ação extra."""
    if not isencoes:
        return achados
    return [a for a in achados if not esta_isento(a.codigo, a.arquivo, isencoes, hoje=hoje)]
