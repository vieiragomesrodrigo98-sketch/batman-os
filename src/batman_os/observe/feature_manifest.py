"""Manifesto de funcionalidades do monitor funcional / sintetico.

Fonte da verdade: `docs/observe/MONITOR_FUNCIONAL.md`. O `FeatureManifest` e a
declaracao versionada, por tenant, do que o site ENTREGA ao usuario; cada
`FeatureCheck` exercita uma jornada (metodo + caminho + asercao de conteudo) e
falha quando a funcionalidade nao e entregue — mesmo com CPU baixo e HTTP 200.

Disciplina (contrato de paridade do subsistema `observe`): este modulo importa
`governance` (`SeveridadeAlerta`) + `foundation` + stdlib/pydantic e NUNCA
importa `batman_os.kernel` (ADR-0012).

## Formato de `espera_conteudo` (avaliador de asercao)

`espera_conteudo` e uma string declarativa — a asercao que PROVA que a feature
entrega (nao so responde). Uma ou mais clausulas unidas por ` && ` (AND). Cada
clausula e uma de:

- `contains:<texto>`   — o corpo bruto da resposta contem `<texto>` (substring;
                         usado para HTML, ex.: `contains:Radar Preditivo`).
- `<caminho> exists`   — o caminho JSON existe e nao e null.
- `<caminho> == <lit>` — igualdade com um literal JSON.
- `<caminho> != <lit>` — desigualdade.
- `<caminho> is array` — o valor e uma lista.
- `<caminho> is string`— o valor e uma string.
- `<caminho> is number`— o valor e int/float (bool NAO conta).
- `<caminho> is nonempty` — string/lista/dict nao-vazios.
- `<caminho> in [<lit>, ...]` — o valor pertence ao conjunto de literais.

`<caminho>` e uma sequencia de segmentos: `.chave`, `[<indice>]`, `[*]` (todos
os elementos) — ex.: `.status`, `[0].name`, `[*].asset_ticker`. Um `.` sozinho
refere-se a raiz do corpo (ex.: `. is array`). O coringa `[*]` aplica o
operador a CADA elemento (lista vazia => verdadeiro vacuo — assim "array; se
nao-vazio cada item tem X" fica `. is array && [*].X exists`, sem alarme falso
quando o usuario simplesmente nao tem itens). Literais: `"..."`/`'...'` (str),
numeros, `true`/`false`/`null`. `&&`, `,` e aspas sao reservados.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from batman_os.foundation.types import TenantId
from batman_os.governance.governance_engine import SeveridadeAlerta

MetodoHttp = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
TipoAuth = Literal["none", "sessao", "sessao-prime"]

_DIR_MANIFESTOS = Path(__file__).resolve().parent / "manifests"


class AsercaoInvalida(Exception):
    """`espera_conteudo` com sintaxe invalida — pego no carregamento do
    manifesto (fail-fast), nunca em `run_once` (que confia no manifesto)."""


# ---------------------------------------------------------------------------
# Avaliador de asercao — caminho JSON + operadores (documentado no modulo)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Chave:
    nome: str


@dataclass(frozen=True)
class _Indice:
    i: int


@dataclass(frozen=True)
class _Coringa:
    """Segmento `[*]` — fan-out sobre todos os elementos de uma lista."""


_CORINGA = _Coringa()
Segmento = _Chave | _Indice | _Coringa


@dataclass(frozen=True)
class _ClausulaContains:
    texto: str


@dataclass(frozen=True)
class _ClausulaJson:
    caminho: tuple[Segmento, ...]
    caminho_str: str
    operador: str
    literais: tuple[Any, ...] = ()


Clausula = _ClausulaContains | _ClausulaJson


@dataclass(frozen=True)
class ResultadoConteudo:
    """Saida do avaliador: `ok` + `detalhe` (esperado-vs-obtido em falha)."""

    ok: bool
    detalhe: str


_OPERADORES_SIMPLES = {
    "exists": "exists",
    "is array": "array",
    "is string": "string",
    "is number": "number",
    "is nonempty": "nonempty",
}


def _segmentar(caminho: str) -> tuple[Segmento, ...]:
    if caminho == ".":
        return ()
    segs: list[Segmento] = []
    pos = 0
    n = len(caminho)
    while pos < n:
        c = caminho[pos]
        if c == ".":
            fim = pos + 1
            while fim < n and (caminho[fim].isalnum() or caminho[fim] in "_-"):
                fim += 1
            if fim == pos + 1:
                raise AsercaoInvalida(f"caminho invalido (chave vazia): {caminho!r}")
            segs.append(_Chave(caminho[pos + 1 : fim]))
            pos = fim
        elif c == "[":
            fim = caminho.find("]", pos)
            if fim == -1:
                raise AsercaoInvalida(f"caminho invalido (']' ausente): {caminho!r}")
            interno = caminho[pos + 1 : fim]
            if interno == "*":
                segs.append(_CORINGA)
            elif interno.isdigit():
                segs.append(_Indice(int(interno)))
            else:
                raise AsercaoInvalida(f"indice invalido {interno!r} em {caminho!r}")
            pos = fim + 1
        else:
            raise AsercaoInvalida(f"caminho invalido em {caminho!r} (posicao {pos})")
    if not segs:
        raise AsercaoInvalida(f"caminho vazio: {caminho!r}")
    return tuple(segs)


def _parse_literal(texto: str) -> Any:
    t = texto.strip()
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        return t[1:-1]
    if t == "true":
        return True
    if t == "false":
        return False
    if t == "null":
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError as exc:
        raise AsercaoInvalida(f"literal invalido: {texto!r}") from exc


def _parse_lista(texto: str) -> tuple[Any, ...]:
    t = texto.strip()
    if not (t.startswith("[") and t.endswith("]")):
        raise AsercaoInvalida(f"lista invalida (esperava [..]): {texto!r}")
    interno = t[1:-1].strip()
    if not interno:
        return ()
    return tuple(_parse_literal(p) for p in interno.split(","))


def _compilar_clausula(bruta: str) -> Clausula:
    texto = bruta.strip()
    if not texto:
        raise AsercaoInvalida("clausula vazia")
    if texto.startswith("contains:"):
        alvo = texto[len("contains:") :].strip()
        if not alvo:
            raise AsercaoInvalida("clausula 'contains:' sem texto")
        return _ClausulaContains(texto=alvo)
    partes = texto.split(None, 1)
    caminho_str = partes[0]
    resto = partes[1].strip() if len(partes) > 1 else ""
    caminho = _segmentar(caminho_str)
    if resto in _OPERADORES_SIMPLES:
        return _ClausulaJson(caminho, caminho_str, _OPERADORES_SIMPLES[resto])
    if resto.startswith("== "):
        return _ClausulaJson(caminho, caminho_str, "eq", (_parse_literal(resto[3:]),))
    if resto.startswith("!= "):
        return _ClausulaJson(caminho, caminho_str, "neq", (_parse_literal(resto[3:]),))
    if resto.startswith("in "):
        return _ClausulaJson(caminho, caminho_str, "in", _parse_lista(resto[3:]))
    raise AsercaoInvalida(f"operador desconhecido na clausula: {bruta!r}")


def _compilar(esperado: str) -> list[Clausula]:
    clausulas = [_compilar_clausula(parte) for parte in esperado.split("&&")]
    if not clausulas:
        raise AsercaoInvalida("asercao vazia")
    return clausulas


def resolver_caminho(caminho: str, dados: Any) -> list[tuple[bool, Any]]:
    """Resolve um caminho JSON (`.a[0].b`, `[*].c`, `.`) sobre `dados`.

    Retorna um ramo `(encontrado, valor)` por resolucao — `[*]` produz um
    ramo por elemento (lista vazia => nenhum ramo => verdadeiro vacuo)."""
    ramos: list[tuple[bool, Any]] = [(True, dados)]
    for seg in _segmentar(caminho) if caminho else ():
        ramos = _avancar(seg, ramos)
    return ramos


def _avancar(seg: Segmento, ramos: list[tuple[bool, Any]]) -> list[tuple[bool, Any]]:
    prox: list[tuple[bool, Any]] = []
    for encontrado, valor in ramos:
        if not encontrado:
            prox.append((False, None))
        elif isinstance(seg, _Coringa):
            if isinstance(valor, list):
                prox.extend((True, item) for item in valor)
            else:
                prox.append((False, None))
        elif isinstance(seg, _Indice):
            if isinstance(valor, list) and 0 <= seg.i < len(valor):
                prox.append((True, valor[seg.i]))
            else:
                prox.append((False, None))
        else:
            if isinstance(valor, dict) and seg.nome in valor:
                prox.append((True, valor[seg.nome]))
            else:
                prox.append((False, None))
    return prox


def _nonempty(valor: Any) -> bool:
    if isinstance(valor, str | list | dict):
        return len(valor) > 0
    return bool(valor)


def _checar_operador(cl: _ClausulaJson, encontrado: bool, valor: Any) -> bool:
    op = cl.operador
    if op == "exists":
        return encontrado and valor is not None
    if not encontrado:
        return False
    if op == "array":
        return isinstance(valor, list)
    if op == "string":
        return isinstance(valor, str)
    if op == "number":
        return isinstance(valor, int | float) and not isinstance(valor, bool)
    if op == "nonempty":
        return _nonempty(valor)
    if op == "eq":
        return bool(valor == cl.literais[0])
    if op == "neq":
        return bool(valor != cl.literais[0])
    if op == "in":
        return valor in cl.literais
    return False


_SEM_JSON = object()


def _json_ou_sentinela(corpo: str) -> Any:
    try:
        return json.loads(corpo)
    except (json.JSONDecodeError, ValueError):
        return _SEM_JSON


def _descrever(cl: _ClausulaJson, encontrado: bool, valor: Any) -> str:
    if cl.operador == "exists":
        return "ausente" if not encontrado else "e null"
    if not encontrado:
        return "caminho ausente"
    alvo = f" {cl.literais[0]!r}" if cl.literais else ""
    return f"esperava {cl.operador}{alvo}, obtido {valor!r}"


def avaliar_conteudo(esperado: str | None, corpo: str) -> ResultadoConteudo:
    """Avalia a asercao `esperado` (ver formato no docstring do modulo) contra
    o corpo bruto `corpo`. `esperado=None` => sempre passa (feature sem asercao
    de conteudo). A primeira clausula que falha determina o `detalhe`."""
    if esperado is None:
        return ResultadoConteudo(ok=True, detalhe="")
    clausulas = _compilar(esperado)
    dados = _json_ou_sentinela(corpo)
    for cl in clausulas:
        if isinstance(cl, _ClausulaContains):
            if cl.texto not in corpo:
                return ResultadoConteudo(ok=False, detalhe=f"substring ausente: {cl.texto!r}")
            continue
        if dados is _SEM_JSON:
            return ResultadoConteudo(
                ok=False, detalhe=f"corpo nao e JSON (esperava {cl.caminho_str} {cl.operador})"
            )
        ramos = resolver_caminho(cl.caminho_str, dados)
        for encontrado, valor in ramos:
            if not _checar_operador(cl, encontrado, valor):
                return ResultadoConteudo(
                    ok=False, detalhe=f"{cl.caminho_str}: {_descrever(cl, encontrado, valor)}"
                )
    return ResultadoConteudo(ok=True, detalhe="")


# ---------------------------------------------------------------------------
# Modelos do manifesto (tipados, carregados de arquivo por tenant)
# ---------------------------------------------------------------------------
class FeatureCheck(BaseModel):
    """Uma jornada de usuario exercitada pelo monitor (sec.1 do design)."""

    id: str
    descricao: str
    metodo: MetodoHttp = "GET"
    caminho: str
    espera_status: int = 200
    espera_conteudo: str | None = None
    auth: TipoAuth = "none"
    severidade_se_cair: SeveridadeAlerta
    timeout_s: float
    habilitado: bool = True
    # Corpo da requisicao (POST). Placeholders substituidos em runtime:
    # `<uuid4>` -> uuid gerado; `<cpf>`/`<senha>` -> credencial sintetica de env.
    corpo: dict[str, Any] | None = None
    # Status que NAO sao outage para esta feature (do seed): carteira 403/503
    # (nao-Prime / sem chave), chat 429 (quota diaria por plano). Um destes =>
    # feature considerada entregue (nao alarma, e conta como recuperacao).
    status_tolerados: list[int] = Field(default_factory=list)
    obs: str | None = None


class AuthConfig(BaseModel):
    """Login sintetico do monitor (sec.4 do design). As CREDENCIAIS nunca
    ficam no manifesto — o manifesto carrega apenas os NOMES das variaveis de
    ambiente de onde o valor vem (cofre/env, fora do repo)."""

    tipo: str = "login-cpf"
    endpoint: str
    campo_credencial: str = "cpf"
    campo_senha: str = "password"
    token_em: str = "access_token"  # caminho JSON do token no corpo do login
    env_credencial: str
    env_senha: str
    # Conta Prime dedicada (auth=sessao-prime, ex.: cobrir carteira). Ausente =>
    # checks sessao-prime nao rodam (config, nao outage).
    env_credencial_prime: str | None = None
    env_senha_prime: str | None = None
    timeout_s: float = 8.0


class DriftConfig(BaseModel):
    """Salvaguarda de drift (sec.3 do design)."""

    # 404/410 consistente por N ciclos => rota removida (MANIFEST_DRIFT), nao outage.
    ciclos_para_confirmar_removida: int = 3
    # Regex de rotas de borda/bloqueadas ignoradas no cross-check "rota nova sem
    # cobertura" (do seed: admin/metrics nao sao jornada de usuario).
    rotas_ignoradas: list[str] = Field(default_factory=list)


class FeatureManifest(BaseModel):
    """Manifesto declarativo, versionado, por tenant (sec.1 do design)."""

    tenant_id: TenantId
    base_url: str
    revisado_em: str
    site_version: str | None = None
    auth: AuthConfig
    features: list[FeatureCheck]
    drift: DriftConfig = Field(default_factory=DriftConfig)

    @field_validator("base_url")
    @classmethod
    def _sem_barra_final(cls, valor: str) -> str:
        return valor.rstrip("/")

    @model_validator(mode="after")
    def _asercoes_compilam(self) -> FeatureManifest:
        for feature in self.features:
            if feature.espera_conteudo is not None:
                _compilar(feature.espera_conteudo)  # fail-fast: sintaxe invalida
        return self


def carregar_manifesto(path: str | Path) -> FeatureManifest:
    """Carrega e valida um `FeatureManifest` de um arquivo JSON. Chaves extra
    (ex.: `_nota`) sao ignoradas; asercoes de conteudo sao compiladas aqui
    (sintaxe invalida => `AsercaoInvalida` no carregamento, nao em runtime)."""
    dados = json.loads(Path(path).read_text(encoding="utf-8"))
    return FeatureManifest.model_validate(dados)


def caminho_manifesto(tenant_id: str) -> Path:
    """Caminho canonico do manifesto de um tenant: `manifests/<tenant>.json`
    ao lado deste modulo."""
    return _DIR_MANIFESTOS / f"{tenant_id}.json"
