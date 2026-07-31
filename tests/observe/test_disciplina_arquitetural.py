"""Disciplina arquitetural do subsistema `observe` (contrato de paridade,
secao "Restricoes arquiteturais"): o pacote importa `governance` +
`foundation` + stdlib/psutil e NUNCA importa `batman_os.kernel` — mesma
auditoria estatica de AT-27.3/AT-30.3 (coerente com ADR-0012)."""

from __future__ import annotations

import ast
import inspect
import pkgutil
from types import ModuleType

import batman_os.observe as observe_pkg
from batman_os.observe import (
    collectors,
    feature_manifest,
    functional_monitor,
    snapshot,
    watch_rules,
    watcher,
)


def _modulos_importados(modulo: ModuleType) -> list[str]:
    arvore = ast.parse(inspect.getsource(modulo))
    nomes: list[str] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.extend(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes.append(no.module)
    return nomes


class TestObserveNaoImportaKernel:
    def test_nenhum_modulo_do_pacote_importa_kernel(self) -> None:
        modulos = (
            snapshot,
            collectors,
            watch_rules,
            watcher,
            feature_manifest,
            functional_monitor,
            observe_pkg,
        )
        for modulo in modulos:
            violacoes = [m for m in _modulos_importados(modulo) if m.startswith("batman_os.kernel")]
            assert violacoes == [], f"{modulo.__name__} importa kernel: {violacoes}"

    def test_cobre_todos_os_submodulos_do_pacote(self) -> None:
        # garante que a auditoria acima nao esqueceu nenhum submodulo novo
        submodulos = {m.name for m in pkgutil.iter_modules(observe_pkg.__path__)}
        assert submodulos == {
            "collectors",
            "snapshot",
            "watch_rules",
            "watcher",
            "feature_manifest",
            "functional_monitor",
        }
