"""LLM Gateway real via Anthropic (Milestone 6 desta construção).

`AnthropicLlmGateway` satisfaz o `LlmGateway` Protocol já existente
(`kernel/decision_engine.py`) — replica quase literalmente o padrão já em
produção em `radar-preditivo/src/radar/llm/client.py`: tool_use forçado
para structured output, resolução de `$defs`/`$ref`, prompt caching no
bloco `system`, retry via `tenacity` que exclui erro de limite de conta
(permanente), e circuit breaker de custo consultado ANTES de qualquer
chamada. Qualquer esgotamento (retry, orçamento, erro de conta, resposta
sem `tool_use`) levanta `LlmGatewayIndisponivel` — nunca retorna `None`
(o Protocol do batman-os já exige exceção, mais limpo que o padrão
`Optional` do radar).

Cliente Anthropic injetável (`client`) para testes 100% com fake — nenhum
teste deste módulo faz uma chamada de rede real."""

from __future__ import annotations

import copy
from typing import Any, Protocol

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from batman_os.kernel.decision_engine import LlmGatewayIndisponivel, RespostaLlmCandidata
from batman_os.kernel.planning_engine import DecisionPoint
from batman_os.llm.cost_tracker import CostTracker
from batman_os.llm.settings import Settings

_NOME_DA_TOOL = "resolver_decision_point"

_SYSTEM_PROMPT = (
    "Voce e o LLM Gateway do Batman OS, o ultimo recurso na hierarquia "
    "Knowledge First -> Human Last -> LLM Last (Vol.I Principio 6). Voce "
    "resolve um DecisionPoint apenas quando nem uma regra ativa nem um "
    "humano puderam resolve-lo a tempo. Escolha exatamente uma das opcoes "
    "fornecidas, nunca invente uma opcao nova, e retorne sua confianca "
    "real (0.0 a 1.0) e o raciocinio que te levou a escolha."
)


class _UsoAnthropicComoAssinatura(Protocol):
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int | None
    cache_read_input_tokens: int | None


class _BlocoDeConteudoComoAssinatura(Protocol):
    type: str
    input: dict[str, Any]


class _RespostaAnthropicComoAssinatura(Protocol):
    usage: _UsoAnthropicComoAssinatura | None
    content: list[_BlocoDeConteudoComoAssinatura]


class _MensagensAnthropicComoAssinatura(Protocol):
    def create(self, **kwargs: Any) -> _RespostaAnthropicComoAssinatura: ...


class _ClienteAnthropicComoAssinatura(Protocol):
    @property
    def messages(self) -> _MensagensAnthropicComoAssinatura: ...


def _e_erro_de_limite_de_conta(exc: BaseException) -> bool:
    """Vol.IX (Reference Implementation) — erro de limite MENSAL da conta
    Anthropic é permanente até a virada do ciclo de faturamento; retry
    nunca ajuda (mesmo padrão de `radar-preditivo`, LLM_LIMIT01)."""
    msg = str(exc).lower()
    return "usage limit" in msg or "regain access" in msg


def _e_transitorio(exc: BaseException) -> bool:
    return not _e_erro_de_limite_de_conta(exc)


def _flatten_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve `$ref` inline — Pydantic gera `$defs` para tipos aninhados
    (ex.: `DecisionOption` dentro de `RespostaLlmCandidata`); a Anthropic
    aceita `$defs`, mas resolver explicitamente evita edge cases (lógica
    genérica, sem acoplamento a domínio — adaptada quase literal do
    radar-preditivo)."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})
    if not defs:
        return schema

    def resolve(obj: Any) -> Any:
        if isinstance(obj, dict):
            if "$ref" in obj:
                nome_ref = obj["$ref"].rsplit("/", 1)[-1]
                return resolve(defs.get(nome_ref, obj))
            return {k: resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [resolve(i) for i in obj]
        return obj

    resolved: dict[str, Any] = resolve(schema)
    return resolved


def _mensagem_usuario(ponto: DecisionPoint) -> str:
    opcoes = "\n".join(f"- {opcao.id}: {opcao.descricao}" for opcao in ponto.opcoes)
    return (
        f"Pergunta: {ponto.pergunta}\n\n"
        f"Opcoes disponiveis:\n{opcoes}\n\n"
        f"Contexto adicional: {ponto.dados}"
    )


class AnthropicLlmGateway:
    """Vol.II Cap.8, secao 8.5 / Vol.III Cap.12 — satisfaz `LlmGateway`
    (`kernel/decision_engine.py`)."""

    def __init__(
        self,
        settings: Settings,
        cost_tracker: CostTracker,
        client: _ClienteAnthropicComoAssinatura,
        tentativas_max: int = 2,
        espera_minima: float = 2.0,
        espera_maxima: float = 10.0,
    ) -> None:
        self._settings = settings
        self._cost_tracker = cost_tracker
        self._client = client
        self._tentativas_max = tentativas_max
        self._espera_minima = espera_minima
        self._espera_maxima = espera_maxima
        # Circuit breaker (mesmo padrao de LLM_LIMIT01, radar-preditivo):
        # uma vez detectado o limite de conta NESTE processo/instancia, para
        # de tentar a API pelo resto da vida do objeto.
        self._limite_de_conta_atingido = False

    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
        if self._limite_de_conta_atingido:
            raise LlmGatewayIndisponivel(
                "Anthropic: limite de conta ja confirmado nesta instancia — "
                "chamada pulada sem round-trip"
            )
        if self._cost_tracker.orcamento_excedido():
            raise LlmGatewayIndisponivel(
                f"Teto diario de custo LLM atingido (${self._settings.max_daily_llm_cost_usd})"
            )

        schema = _flatten_refs(RespostaLlmCandidata.model_json_schema())

        def _chamar() -> _RespostaAnthropicComoAssinatura:
            return self._client.messages.create(
                model=self._settings.llm_model,
                max_tokens=self._settings.llm_max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": _mensagem_usuario(ponto)}],
                tools=[
                    {
                        "name": _NOME_DA_TOOL,
                        "description": "Retorna a resolucao estruturada do DecisionPoint.",
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": _NOME_DA_TOOL},
                timeout=self._settings.llm_timeout,
            )

        chamar_com_retry = retry(
            stop=stop_after_attempt(self._tentativas_max),
            wait=wait_exponential(multiplier=1, min=self._espera_minima, max=self._espera_maxima),
            retry=retry_if_exception(_e_transitorio),
            reraise=True,
        )(_chamar)

        try:
            resposta = chamar_com_retry()
        except Exception as exc:
            if _e_erro_de_limite_de_conta(exc):
                self._limite_de_conta_atingido = True
            raise LlmGatewayIndisponivel(f"Anthropic API error: {exc}") from exc

        if resposta.usage is not None:
            self._cost_tracker.registrar(
                model=self._settings.llm_model,
                input_tokens=resposta.usage.input_tokens,
                output_tokens=resposta.usage.output_tokens,
                cache_write_tokens=resposta.usage.cache_creation_input_tokens or 0,
                cache_read_tokens=resposta.usage.cache_read_input_tokens or 0,
            )

        for bloco in resposta.content:
            if bloco.type == "tool_use":
                return RespostaLlmCandidata.model_validate(bloco.input)

        raise LlmGatewayIndisponivel("Resposta Anthropic sem bloco tool_use")
