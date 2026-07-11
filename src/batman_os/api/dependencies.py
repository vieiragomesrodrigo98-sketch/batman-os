"""Providers de injeção de dependência do app FastAPI (Fase 6 do roadmap
de plataforma, `.claude/plans/peaceful-wondering-hearth.md`, Estágio
6.2) — leem os colaboradores compartilhados de `app.state` (construídos
uma vez no `lifespan`, `api/app.py`), nunca reconstroem nada por
requisição."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from batman_os.api.state import ColaboradoresCompartilhados


def obter_colaboradores(request: Request) -> ColaboradoresCompartilhados:
    colaboradores: ColaboradoresCompartilhados = request.app.state.colaboradores
    return colaboradores


ColaboradoresDep = Annotated[ColaboradoresCompartilhados, Depends(obter_colaboradores)]
