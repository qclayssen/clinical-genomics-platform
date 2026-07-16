"""LLM backend abstraction for the variant interpretation agent.

Provides a unified interface for multiple LLM providers (Ollama, OpenAI,
Anthropic) with automatic fallback and a deterministic backend for CI.

Environment variables:
  AGENT_LLM_BACKEND: ollama|openai|anthropic|deterministic (default: deterministic)
  OPENAI_API_KEY: Required for OpenAI backend
  ANTHROPIC_API_KEY: Required for Anthropic backend
  OLLAMA_URL: Ollama server URL (default: http://localhost:11434)
  OLLAMA_MODEL: Ollama model name (default: llama3.2:3b)
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ═══ Data Types ═══════════════════════════════════════════════════════════════


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""

    name: str
    arguments: dict
    id: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "arguments": self.arguments, "id": self.id}


@dataclass
class LLMResponse:
    """Response from an LLM backend.

    Attributes
    ----------
    content : str
        Text content of the response (may be empty if tool_calls present).
    tool_calls : list[ToolCall]
        Tool calls requested by the model.
    stop_reason : str
        Why the model stopped: 'tool_use', 'end_turn', 'max_tokens', 'error'.
    model : str
        Model identifier that produced this response.
    usage : dict
        Token usage info (input_tokens, output_tokens).
    raw : Any
        Raw response from the provider (for debugging).
    """

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    model: str = ""
    usage: dict = field(default_factory=dict)
    raw: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "stop_reason": self.stop_reason,
            "model": self.model,
            "usage": self.usage,
        }


@dataclass
class Message:
    """A message in the conversation history."""

    role: str  # 'system', 'user', 'assistant', 'tool'
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


# ═══ Abstract Backend ═════════════════════════════════════════════════════════


class LLMBackend(ABC):
    """Abstract base class for LLM backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier."""
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Model identifier string."""
        ...

    @abstractmethod
    def generate(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Parameters
        ----------
        messages : list[Message]
            Conversation history.
        tools : list[dict], optional
            Tool definitions in OpenAI function-calling format.
        temperature : float
            Sampling temperature (0.0 = deterministic).
        max_tokens : int
            Maximum tokens to generate.

        Returns
        -------
        LLMResponse
            The model's response with optional tool calls.
        """
        ...

    def is_available(self) -> bool:
        """Check if this backend is currently available."""
        return True


# ═══ Deterministic Backend (CI/Testing) ═══════════════════════════════════════


class DeterministicBackend(LLMBackend):
    """Pre-scripted backend for CI and testing — no real LLM inference.

    Returns tool calls based on heuristic analysis of the conversation.
    Simulates the agent's expected reasoning path without any network calls.
    """

    @property
    def name(self) -> str:
        return "deterministic"

    @property
    def model_id(self) -> str:
        return "deterministic-v1"

    def generate(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate a deterministic response based on conversation state.

        Follows a fixed strategy:
        1. First call: query_clinvar for the variant
        2. Second call: query_gnomad for the variant
        3. Third call: query_gene_info for the gene
        4. Fourth call: classify_acmg with gathered evidence
        5. Fifth call: final_answer with the classification
        """
        # Count previous tool results to determine step
        tool_results = [m for m in messages if m.role == "tool"]
        step = len(tool_results)

        # Extract variant info from the conversation
        variant_info = self._extract_variant_info(messages)
        chrom = variant_info.get("chrom", "chr20")
        pos = variant_info.get("pos", 0)
        ref = variant_info.get("ref", "N")
        alt = variant_info.get("alt", "N")
        gene = variant_info.get("gene", "")

        if step == 0:
            # Step 1: Query ClinVar
            return LLMResponse(
                content="I'll look up this variant in ClinVar first.",
                tool_calls=[ToolCall(
                    name="query_clinvar",
                    arguments={"chrom": chrom, "pos": pos, "ref": ref, "alt": alt},
                    id="call_clinvar_1",
                )],
                stop_reason="tool_use",
                model=self.model_id,
                usage={"input_tokens": 0, "output_tokens": 0},
            )

        elif step == 1:
            # Step 2: Query gnomAD
            return LLMResponse(
                content="Now checking population frequency in gnomAD.",
                tool_calls=[ToolCall(
                    name="query_gnomad",
                    arguments={"chrom": chrom, "pos": pos, "ref": ref, "alt": alt},
                    id="call_gnomad_1",
                )],
                stop_reason="tool_use",
                model=self.model_id,
                usage={"input_tokens": 0, "output_tokens": 0},
            )

        elif step == 2:
            # Step 3: Query gene info
            gene_symbol = gene or self._extract_gene_from_results(messages)
            return LLMResponse(
                content=f"Looking up gene information for {gene_symbol}.",
                tool_calls=[ToolCall(
                    name="query_gene_info",
                    arguments={"gene_symbol": gene_symbol or "UNKNOWN"},
                    id="call_gene_1",
                )],
                stop_reason="tool_use",
                model=self.model_id,
                usage={"input_tokens": 0, "output_tokens": 0},
            )

        elif step == 3:
            # Step 4: Classify with gathered evidence
            evidence = self._gather_evidence_codes(messages)
            return LLMResponse(
                content="Applying ACMG combining rules to the evidence.",
                tool_calls=[ToolCall(
                    name="classify_acmg",
                    arguments={"evidence_codes": evidence},
                    id="call_acmg_1",
                )],
                stop_reason="tool_use",
                model=self.model_id,
                usage={"input_tokens": 0, "output_tokens": 0},
            )

        else:
            # Step 5: Final answer
            classification_info = self._extract_classification(messages)
            return LLMResponse(
                content="Submitting final classification.",
                tool_calls=[ToolCall(
                    name="final_answer",
                    arguments={
                        "classification": classification_info["classification"],
                        "evidence": classification_info["evidence"],
                        "summary": classification_info["summary"],
                        "variant": f"{chrom}:{pos} {ref}>{alt}",
                        "confidence": classification_info["confidence"],
                    },
                    id="call_final_1",
                )],
                stop_reason="tool_use",
                model=self.model_id,
                usage={"input_tokens": 0, "output_tokens": 0},
            )

    def _extract_variant_info(self, messages: list[Message]) -> dict:
        """Extract variant coordinates from conversation messages."""
        import re
        for msg in messages:
            if msg.role == "user":
                content = msg.content
                # Try to parse the entire content as JSON
                try:
                    data = json.loads(content)
                    if isinstance(data, dict) and "chrom" in data:
                        return data
                    if isinstance(data, dict) and "variants" in data:
                        v = data["variants"][0] if data["variants"] else {}
                        return v
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
                # Try to find JSON embedded in text (e.g., at end of message)
                json_match = re.search(r'\{[^{}]*"chrom"[^{}]*\}', content)
                if json_match:
                    try:
                        data = json.loads(json_match.group())
                        if "chrom" in data and "pos" in data:
                            return data
                    except json.JSONDecodeError:
                        pass
                # Try to find variant pattern: chr20:4699605 G>A
                match = re.search(
                    r"(chr\w+):(\d+)\s+(\w+)>(\w+)", content
                )
                if match:
                    return {
                        "chrom": match.group(1),
                        "pos": int(match.group(2)),
                        "ref": match.group(3),
                        "alt": match.group(4),
                    }
                # Try structured text format: Position: 4699605
                chrom_match = re.search(r"Chromosome:\s*(chr\w+)", content)
                pos_match = re.search(r"Position:\s*(\d+)", content)
                ref_match = re.search(r"Reference allele:\s*(\w+)", content)
                alt_match = re.search(r"Alternate allele:\s*(\w+)", content)
                if chrom_match and pos_match and ref_match and alt_match:
                    result = {
                        "chrom": chrom_match.group(1),
                        "pos": int(pos_match.group(1)),
                        "ref": ref_match.group(1),
                        "alt": alt_match.group(1),
                    }
                    gene_match = re.search(r"Gene:\s*(\w+)", content)
                    if gene_match:
                        result["gene"] = gene_match.group(1)
                    return result
        return {}

    def _extract_gene_from_results(self, messages: list[Message]) -> str:
        """Extract gene symbol from previous tool results."""
        for msg in reversed(messages):
            if msg.role == "tool":
                try:
                    data = json.loads(msg.content)
                    if "records" in data and data["records"]:
                        return data["records"][0].get("gene", "")
                    if "gene" in data:
                        return data["gene"]
                except (json.JSONDecodeError, KeyError):
                    pass
        return "UNKNOWN"

    def _gather_evidence_codes(self, messages: list[Message]) -> list[str]:
        """Gather ACMG evidence codes from tool results."""
        codes: list[str] = []
        for msg in messages:
            if msg.role != "tool":
                continue
            try:
                data = json.loads(msg.content)
                # From gnomAD result
                if "acmg_frequency_codes" in data:
                    codes.extend(data["acmg_frequency_codes"])
                # From ClinVar — infer PS1/PP5 if pathogenic
                if "records" in data:
                    for rec in data["records"]:
                        sig = rec.get("clinical_significance", "")
                        stars = rec.get("review_stars", 0)
                        if sig == "Pathogenic" and stars >= 2:
                            codes.append("PS1")
                            codes.append("PP5")
                        elif sig == "Likely Pathogenic" and stars >= 2:
                            codes.append("PP5")
            except (json.JSONDecodeError, KeyError):
                pass
        return codes if codes else ["PM2"]

    def _extract_classification(self, messages: list[Message]) -> dict:
        """Extract the ACMG classification from the classify_acmg result."""
        for msg in reversed(messages):
            if msg.role == "tool":
                try:
                    data = json.loads(msg.content)
                    if "classification" in data and "matched_rule" in data:
                        return {
                            "classification": data["classification"],
                            "evidence": data.get("evidence_codes", []),
                            "summary": (
                                f"Classification based on ACMG combining rules: "
                                f"{data['matched_rule']}. "
                                f"Confidence: {data.get('confidence', 'moderate')}."
                            ),
                            "confidence": data.get("confidence", "moderate"),
                        }
                except (json.JSONDecodeError, KeyError):
                    pass
        return {
            "classification": "Uncertain Significance",
            "evidence": ["PM2"],
            "summary": "Insufficient evidence for definitive classification.",
            "confidence": "low",
        }


# ═══ Ollama Backend ═══════════════════════════════════════════════════════════


class OllamaBackend(LLMBackend):
    """Ollama local LLM backend.

    Uses the Ollama API with function-calling support for models that
    support it (llama3.2, phi3, etc.).
    """

    def __init__(
        self,
        url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 120,
    ) -> None:
        self._url = url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self._model = model or os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model_id(self) -> str:
        return f"ollama/{self._model}"

    def is_available(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate using Ollama chat API with tool support."""
        import urllib.error
        import urllib.request

        # Convert messages to Ollama format
        ollama_messages = []
        for msg in messages:
            m: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                m["tool_calls"] = [
                    {"function": {"name": tc.name, "arguments": tc.arguments}}
                    for tc in msg.tool_calls
                ]
            ollama_messages.append(m)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        # Add tools if provided
        if tools:
            ollama_tools = []
            for tool in tools:
                if "function" in tool:
                    ollama_tools.append({
                        "type": "function",
                        "function": tool["function"],
                    })
            if ollama_tools:
                payload["tools"] = ollama_tools

        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{self._url}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode())

            message = result.get("message", {})
            content = message.get("content", "")
            tool_calls_raw = message.get("tool_calls", [])

            tool_calls = []
            for i, tc in enumerate(tool_calls_raw):
                func = tc.get("function", {})
                tool_calls.append(ToolCall(
                    name=func.get("name", ""),
                    arguments=func.get("arguments", {}),
                    id=f"call_{i}",
                ))

            stop_reason = "tool_use" if tool_calls else "end_turn"

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                stop_reason=stop_reason,
                model=self.model_id,
                usage={
                    "input_tokens": result.get("prompt_eval_count", 0),
                    "output_tokens": result.get("eval_count", 0),
                },
                raw=result,
            )

        except (urllib.error.URLError, TimeoutError, OSError) as e:
            logger.warning(f"Ollama request failed: {e}")
            raise ConnectionError(f"Ollama unavailable: {e}") from e
        except json.JSONDecodeError as e:
            logger.warning(f"Ollama returned invalid JSON: {e}")
            raise ValueError(f"Ollama response parse error: {e}") from e


# ═══ OpenAI Backend ═══════════════════════════════════════════════════════════


class OpenAIBackend(LLMBackend):
    """OpenAI API backend using the function-calling protocol."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model_id(self) -> str:
        return f"openai/{self._model}"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate using OpenAI Chat Completions API."""
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package required for OpenAI backend. "
                "Install with: pip install openai"
            )

        if not self._api_key:
            raise ValueError("OPENAI_API_KEY not set")

        client = openai.OpenAI(api_key=self._api_key)

        # Convert messages to OpenAI format
        oai_messages = []
        for msg in messages:
            if msg.role == "tool":
                oai_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id or "call_0",
                })
            elif msg.role == "assistant" and msg.tool_calls:
                oai_messages.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id or f"call_{i}",
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for i, tc in enumerate(msg.tool_calls)
                    ],
                })
            else:
                oai_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": oai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            message = choice.message

            tool_calls = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append(ToolCall(
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                        id=tc.id,
                    ))

            stop_reason = "tool_use" if tool_calls else "end_turn"
            if choice.finish_reason == "length":
                stop_reason = "max_tokens"

            return LLMResponse(
                content=message.content or "",
                tool_calls=tool_calls,
                stop_reason=stop_reason,
                model=self.model_id,
                usage={
                    "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                },
                raw=response,
            )

        except openai.APIConnectionError as e:
            raise ConnectionError(f"OpenAI connection failed: {e}") from e
        except openai.AuthenticationError as e:
            raise ValueError(f"OpenAI authentication failed: {e}") from e
        except openai.APIError as e:
            raise RuntimeError(f"OpenAI API error: {e}") from e


# ═══ Anthropic Backend ════════════════════════════════════════════════════════


class AnthropicBackend(LLMBackend):
    """Anthropic API backend using the tool-use protocol."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-haiku-20241022",
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model_id(self) -> str:
        return f"anthropic/{self._model}"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate using Anthropic Messages API with tool use."""
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package required for Anthropic backend. "
                "Install with: pip install anthropic"
            )

        if not self._api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        client = anthropic.Anthropic(api_key=self._api_key)

        # Convert messages: separate system from conversation
        system_prompt = ""
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_prompt += msg.content + "\n"
            elif msg.role == "assistant":
                content_blocks: list[dict] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id or "toolu_01",
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                api_messages.append({"role": "assistant", "content": content_blocks})
            elif msg.role == "tool":
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id or "toolu_01",
                        "content": msg.content,
                    }],
                })
            else:
                api_messages.append({"role": msg.role, "content": msg.content})

        # Convert tools to Anthropic format
        anthropic_tools = []
        if tools:
            for tool in tools:
                func = tool.get("function", tool)
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                })

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt.strip():
            kwargs["system"] = system_prompt.strip()
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        try:
            response = client.messages.create(**kwargs)

            content = ""
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        name=block.name,
                        arguments=block.input,
                        id=block.id,
                    ))

            stop_reason = "tool_use" if tool_calls else "end_turn"
            if response.stop_reason == "max_tokens":
                stop_reason = "max_tokens"

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                stop_reason=stop_reason,
                model=self.model_id,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                raw=response,
            )

        except anthropic.APIConnectionError as e:
            raise ConnectionError(f"Anthropic connection failed: {e}") from e
        except anthropic.AuthenticationError as e:
            raise ValueError(f"Anthropic authentication failed: {e}") from e
        except anthropic.APIError as e:
            raise RuntimeError(f"Anthropic API error: {e}") from e


# ═══ Fallback LLM (tries backends in order) ══════════════════════════════════


class FallbackLLM(LLMBackend):
    """Tries multiple backends in order, falling back on failure.

    Default order: preferred → Ollama → Deterministic.
    Always succeeds because DeterministicBackend never fails.
    """

    def __init__(self, backends: Optional[list[LLMBackend]] = None) -> None:
        if backends:
            self._backends = backends
        else:
            self._backends = [
                OllamaBackend(),
                DeterministicBackend(),
            ]
        self._active_backend: Optional[LLMBackend] = None

    @property
    def name(self) -> str:
        if self._active_backend:
            return f"fallback({self._active_backend.name})"
        return "fallback"

    @property
    def model_id(self) -> str:
        if self._active_backend:
            return self._active_backend.model_id
        return "fallback/none"

    @property
    def active_backend(self) -> Optional[LLMBackend]:
        """The backend that last successfully responded."""
        return self._active_backend

    def generate(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Try each backend in order until one succeeds."""
        errors: list[str] = []

        for backend in self._backends:
            if not backend.is_available():
                errors.append(f"{backend.name}: not available")
                continue

            try:
                response = backend.generate(
                    messages, tools, temperature, max_tokens
                )
                self._active_backend = backend
                logger.info(f"FallbackLLM: using {backend.name}")
                return response

            except (ConnectionError, ValueError, RuntimeError, ImportError) as e:
                errors.append(f"{backend.name}: {e}")
                logger.warning(f"FallbackLLM: {backend.name} failed: {e}")
                continue

        # Should never reach here if DeterministicBackend is in the chain
        raise RuntimeError(
            f"All LLM backends failed: {'; '.join(errors)}"
        )


# ═══ Factory ══════════════════════════════════════════════════════════════════


def create_backend(backend_name: Optional[str] = None) -> LLMBackend:
    """Create an LLM backend by name.

    Parameters
    ----------
    backend_name : str, optional
        One of: 'ollama', 'openai', 'anthropic', 'deterministic', 'fallback'.
        If None, reads from AGENT_LLM_BACKEND env var (default: 'deterministic').

    Returns
    -------
    LLMBackend
        The configured backend instance.
    """
    name = backend_name or os.environ.get("AGENT_LLM_BACKEND", "deterministic")
    name = name.lower().strip()

    if name == "deterministic":
        return DeterministicBackend()
    elif name == "ollama":
        return OllamaBackend()
    elif name == "openai":
        return OpenAIBackend()
    elif name == "anthropic":
        return AnthropicBackend()
    elif name == "fallback":
        return FallbackLLM()
    else:
        logger.warning(f"Unknown backend '{name}', using deterministic")
        return DeterministicBackend()
