"""LLM Gateway local (Qwen fine-tunado, GGUF via llama-cpp-python).

`LocalLlmGateway` satisfaz o mesmo `LlmGateway` Protocol
(`kernel/decision_engine.py`) que o `AnthropicLlmGateway` — o Decision
Engine não percebe qual provedor respondeu. Porta o padrão de serving já
em produção no radar-preditivo (`local_llm_classifier.py`): llama.cpp em
CPU, gramática GBNF derivada do JSON Schema (JSON 100% válido por
construção), geração com timeout via thread e breaker de instância.

Decisões de projeto herdadas do radar:
- O breaker desarma a instância após UM timeout: llama.cpp não cancela uma
  geração em andamento e o modelo não é thread-safe para gerações
  concorrentes — insistir só empilharia threads presas.
- A gramática restringe `opcao.id` por enum às opções do DecisionPoint
  (`schema_resposta_para_ponto`), mas a pós-validação repete o invariante
  mesmo assim: fail-safe caso o motor injetado não honre a gramática.
- Confiança abaixo de `llm_local_min_confidence` vira
  `LlmGatewayIndisponivel` — é o gatilho que faz o `FallbackLlmGateway`
  escalar para a Anthropic ("saber quando não sabe" é comportamento
  treinado, não acidente).

`llama-cpp-python` é dependência OPCIONAL (extra `local-llm`): o import é
lazy, e sem ela instalada o gateway degrada em `LlmGatewayIndisponivel` —
nunca em `ImportError` na composição."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from batman_os.kernel.decision_engine import LlmGatewayIndisponivel, RespostaLlmCandidata
from batman_os.kernel.planning_engine import DecisionPoint
from batman_os.llm.cost_tracker import CostTracker
from batman_os.llm.prompts import SYSTEM_PROMPT, mensagem_usuario
from batman_os.llm.schema_utils import schema_resposta_para_ponto
from batman_os.llm.settings import Settings

MODELO_LOCAL = "local-qwen2.5-3b-batman"


class ResultadoMotorLocal(BaseModel):
    """Saída crua de uma geração local: o texto (JSON, se a gramática foi
    honrada) e a contagem de tokens para o ledger de custo (preço zero,
    mas volume e latência continuam observáveis)."""

    texto: str
    tokens_entrada: int = 0
    tokens_saida: int = 0


class MotorLlmLocalComoAssinatura(Protocol):
    """Forma mínima que o gateway precisa de um motor de inferência local —
    injetável para testes 100% sem GGUF/GPU (espelho do
    `_ClienteAnthropicComoAssinatura` do gateway Anthropic)."""

    def gerar(
        self, system: str, usuario: str, schema: dict[str, Any], timeout: float
    ) -> ResultadoMotorLocal: ...


class _MotorLlamaCpp:
    """Motor real: um `llama_cpp.Llama` carregado uma única vez, gramática
    GBNF compilada por schema (cache — pontos do mesmo tipo repetem as
    mesmas opções) e geração em thread única com timeout."""

    def __init__(self, llm: Any, max_tokens: int) -> None:
        self._llm = llm
        self._max_tokens = max_tokens
        self._gramaticas: dict[str, Any] = {}
        self._executor = ThreadPoolExecutor(max_workers=1)

    def gerar(
        self, system: str, usuario: str, schema: dict[str, Any], timeout: float
    ) -> ResultadoMotorLocal:
        from llama_cpp import LlamaGrammar

        chave = json.dumps(schema, sort_keys=True)
        gramatica = self._gramaticas.get(chave)
        if gramatica is None:
            gramatica = LlamaGrammar.from_json_schema(json.dumps(schema))
            self._gramaticas[chave] = gramatica

        futuro = self._executor.submit(self._completar, system, usuario, gramatica)
        return futuro.result(timeout=timeout)

    def _completar(self, system: str, usuario: str, gramatica: Any) -> ResultadoMotorLocal:
        completion = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": usuario},
            ],
            temperature=0.0,
            max_tokens=self._max_tokens,
            grammar=gramatica,
        )
        uso = completion.get("usage", {})
        return ResultadoMotorLocal(
            texto=completion["choices"][0]["message"]["content"] or "",
            tokens_entrada=uso.get("prompt_tokens", 0),
            tokens_saida=uso.get("completion_tokens", 0),
        )


def _criar_motor_llama_cpp(settings: Settings) -> MotorLlmLocalComoAssinatura:
    caminho = settings.llm_local_gguf_path
    if not caminho:
        raise LlmGatewayIndisponivel("LLM local: LLM_LOCAL_GGUF_PATH nao configurado")
    if not Path(caminho).exists():
        raise LlmGatewayIndisponivel(f"LLM local: GGUF nao encontrado em {caminho}")
    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise LlmGatewayIndisponivel(
            "LLM local: llama-cpp-python nao instalado — pip install 'batman-os[local-llm]'"
        ) from exc
    llm = Llama(
        model_path=caminho,
        n_ctx=2048,
        n_threads=settings.llm_local_n_threads,
        n_gpu_layers=0,
        verbose=False,
    )
    return _MotorLlamaCpp(llm, max_tokens=settings.llm_max_tokens)


class LocalLlmGateway:
    """Satisfaz `LlmGateway` (`kernel/decision_engine.py`). Toda falha —
    motor ausente, timeout, JSON fora do contrato, opção inexistente,
    confiança insuficiente — vira `LlmGatewayIndisponivel`, o que na
    composição local-first significa: a Anthropic assume."""

    def __init__(
        self,
        settings: Settings,
        cost_tracker: CostTracker,
        motor: MotorLlmLocalComoAssinatura | None = None,
    ) -> None:
        self._settings = settings
        self._cost_tracker = cost_tracker
        self._motor = motor
        self._lock = threading.Lock()
        self._desarmado = False

    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
        if self._desarmado:
            raise LlmGatewayIndisponivel(
                "LLM local: desarmado nesta instancia apos timeout — chamada pulada"
            )

        motor = self._obter_motor()
        schema = schema_resposta_para_ponto(ponto)
        try:
            resultado = motor.gerar(
                system=SYSTEM_PROMPT,
                usuario=mensagem_usuario(ponto),
                schema=schema,
                timeout=self._settings.llm_local_timeout,
            )
        except TimeoutError as exc:
            self._desarmado = True
            raise LlmGatewayIndisponivel(
                f"LLM local: geracao excedeu {self._settings.llm_local_timeout}s — "
                "instancia desarmada (llama.cpp nao cancela geracao em andamento)"
            ) from exc
        except LlmGatewayIndisponivel:
            raise
        except Exception as exc:
            raise LlmGatewayIndisponivel(f"LLM local: erro do motor: {exc}") from exc

        try:
            resposta = RespostaLlmCandidata.model_validate_json(resultado.texto)
        except ValidationError as exc:
            raise LlmGatewayIndisponivel(f"LLM local: resposta fora do contrato: {exc}") from exc

        ids_validos = {opcao.id for opcao in ponto.opcoes}
        if resposta.opcao.id not in ids_validos:
            raise LlmGatewayIndisponivel(
                f"LLM local: opcao '{resposta.opcao.id}' nao esta entre as opcoes do DecisionPoint"
            )
        if resposta.confidence < self._settings.llm_local_min_confidence:
            raise LlmGatewayIndisponivel(
                f"LLM local: confianca {resposta.confidence:.2f} abaixo do minimo "
                f"{self._settings.llm_local_min_confidence:.2f}"
            )

        self._cost_tracker.registrar(
            model=MODELO_LOCAL,
            input_tokens=resultado.tokens_entrada,
            output_tokens=resultado.tokens_saida,
        )
        return resposta

    def _obter_motor(self) -> MotorLlmLocalComoAssinatura:
        with self._lock:
            motor = self._motor
            if motor is None:
                motor = _criar_motor_llama_cpp(self._settings)
                self._motor = motor
            return motor
