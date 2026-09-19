import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from miniviki.llm_interfaces import Request, ToolChoice, ToolChoiceMode, ToolSpec
from miniviki.llm_interfaces.capabilities import Capabilities
from miniviki.llm_interfaces.content import (
    Block,
    Media,
    MediaKind,
    Reasoning,
    Role,
    ServerTool,
    Text,
    ToolCall,
    ToolResult,
    Turn,
    Unknown,
)
from miniviki.llm_interfaces.errors import (
    ContextRejected,
    InterfaceError,
    MalformedPayload,
    ProviderError,
    RateLimited,
    UnsupportedCapability,
)
from miniviki.llm_interfaces.events import (
    ArgsDelta,
    BlockStarted,
    BlockStopped,
    Completed,
    ProviderEvent,
    ReasoningDelta,
    Started,
    StreamEvent,
    TextDelta,
    UsageReported,
)
from miniviki.llm_interfaces.response import Completion, StopReason, Usage

# chat completions has no block index, so one is derived: text and reasoning are
# pinned and tool calls start past them, which keeps the three from colliding
_TEXT_INDEX = 0
_REASONING_INDEX = 1
_FIRST_TOOL_INDEX = 2

_BAD_REQUEST = 400
_RATE_LIMIT = 429


# what the wire format can express. a deployment may support less, so the
# declared set is overridable per instance
DEFAULT_CAPABILITIES = Capabilities(
    tools=True,
    parallel_tool_calls=True,
    json_schema_strict=True,
    reasoning=True,
    reasoning_visible=True,
    reasoning_opaque_roundtrip=False,
    media=frozenset({MediaKind.IMAGE}),
    server_side_tools=False,
    stateful_continuation=False,
    background_jobs=False,
    stream_usage=True
)


@dataclass(frozen=True)
class ChatCompletionsAdapter:
    """the chat completions wire format, shared by openai and the many servers
    that imitate it"""

    declared: Capabilities = DEFAULT_CAPABILITIES
    # openai wants developer, most compatible servers only know system
    instructions_role: str = 'system'

    def capabilities(self) -> Capabilities:
        return self.declared

    def lower_request(
        self, request: Request, stream: bool = False
    ) -> Mapping[str, Any]:
        self._reject_unrepresentable(request)
        body: dict[str, Any] = {
            'model': request.model,
            'messages': self._lower_messages(request),
        }
        if request.tools:
            body['tools'] = [self._lower_tool(tool) for tool in request.tools]
            body['tool_choice'] = self._lower_tool_choice(request.tool_choice)
        if request.limits.max_output_tokens is not None:
            body['max_completion_tokens'] = request.limits.max_output_tokens
        if request.limits.temperature is not None:
            body['temperature'] = request.limits.temperature
        if request.limits.top_p is not None:
            body['top_p'] = request.limits.top_p
        if request.limits.stop:
            body['stop'] = list(request.limits.stop)
        if request.reasoning is not None and request.reasoning.effort is not None:
            body['reasoning_effort'] = request.reasoning.effort
        if stream:
            body['stream'] = True
            body['stream_options'] = {'include_usage': True}
        body.update(request.extra)
        return body

    def parse_completion(self, payload: Mapping[str, Any]) -> Completion:
        choice = self._first_choice(payload)
        message = choice.get('message') or {}
        finish = choice.get('finish_reason')
        return Completion(
            turn=Turn(role=Role.ASSISTANT, blocks=self._parse_message(message)),
            stop_reason=self._stop_reason(finish),
            raw_stop_reason=str(finish or ''),
            usage=self._parse_usage(payload.get('usage')),
            response_id=payload.get('id'),
            model=payload.get('model'),
        )

    def parse_event(self, payload: Mapping[str, Any]) -> Sequence[StreamEvent]:
        choices = payload.get('choices')
        if not choices:
            usage = payload.get('usage')
            if usage is None:
                return (ProviderEvent(kind='chunk_without_choices', payload=dict(payload)),)
            return (UsageReported(usage=self._parse_usage(usage)),)
        choice = choices[0]
        delta = choice.get('delta') or {}
        events: list[StreamEvent] = []
        if 'role' in delta:
            events.append(Started(response_id=payload.get('id'), model=payload.get('model')))
            events.append(BlockStarted(index=_TEXT_INDEX, kind='text'))
        if delta.get('content'):
            events.append(TextDelta(index=_TEXT_INDEX, text=delta['content']))
        if delta.get('reasoning_content'):
            events.append(ReasoningDelta(index=_REASONING_INDEX, text=delta['reasoning_content']))
        for entry in delta.get('tool_calls') or []:
            events.extend(self._parse_tool_call_delta(entry))
        finish = choice.get('finish_reason')
        if finish is not None:
            events.append(BlockStopped(index=_TEXT_INDEX))
            events.append(
                Completed(
                    stop_reason=self._stop_reason(finish),
                    raw_stop_reason=str(finish),
                    response_id=payload.get('id'),
                )
            )
        if not events:
            events.append(ProviderEvent(kind='empty_delta', payload=dict(payload)))
        return tuple(events)

    def parse_error(self, status: int, payload: Mapping[str, Any]) -> InterfaceError:
        detail = self._error_detail(payload)
        if status == _RATE_LIMIT:
            return RateLimited(detail)
        if status == _BAD_REQUEST and ('context' in detail.lower() or 'maximum' in detail.lower()):
            return ContextRejected(detail)
        return ProviderError(f'{status}: {detail}')

    def _reject_unrepresentable(self, request: Request) -> None:
        # dropping these silently would push the failure into the next turn
        for turn in request.messages:
            for block in turn.blocks:
                if isinstance(block, Reasoning) and block.opaque is not None:
                    raise UnsupportedCapability('signed reasoning has no chat completions form')
                if isinstance(block, (ServerTool, Unknown)):
                    raise UnsupportedCapability(f'{type(block).__name__} has no chat completions form')
        if request.tool_choice.allowed:
            raise UnsupportedCapability('a tool whitelist is not expressible in chat completions')

    def _lower_messages(self, request: Request) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if request.instructions is not None:
            messages.append({'role': self.instructions_role, 'content': request.instructions})
        for turn in request.messages:
            if turn.role is Role.ASSISTANT:
                messages.append(self._lower_assistant(turn))
            else:
                messages.extend(self._lower_user(turn))
        return messages

    def _lower_assistant(self, turn: Turn) -> dict[str, Any]:
        # this format has no block list, so several text blocks collapse into
        # one string and tool calls move to a sibling field
        texts = [block.text for block in turn.blocks if isinstance(block, Text)]
        calls = [block for block in turn.blocks if isinstance(block, ToolCall)]
        message: dict[str, Any] = {'role': 'assistant', 'content': '\n'.join(texts) or None}
        if calls:
            message['tool_calls'] = [self._lower_tool_call(call) for call in calls]
        return message

    def _lower_user(self, turn: Turn) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        content = self._lower_user_content(turn)
        if content is not None:
            messages.append({'role': 'user', 'content': content})
        for block in turn.blocks:
            if isinstance(block, ToolResult):
                messages.append({
                    'role': 'tool',
                    'tool_call_id': block.call_id,
                    'content': self._blocks_text(block.content),
                })
        return messages

    def _lower_user_content(self, turn: Turn) -> str | list[dict[str, Any]] | None:
        texts = [block.text for block in turn.blocks if isinstance(block, Text)]
        media = [block for block in turn.blocks if isinstance(block, Media)]
        if not media:
            return '\n'.join(texts) or None
        parts: list[dict[str, Any]] = [{'type': 'text', 'text': text} for text in texts]
        parts.extend(self._lower_media(block) for block in media)
        return parts

    def _lower_media(self, block: Media) -> dict[str, Any]:
        if block.kind is not MediaKind.IMAGE:
            raise UnsupportedCapability(f'{block.kind} input has no chat completions form')
        return {'type': 'image_url', 'image_url': {'url': self._media_url(block)}}

    def _media_url(self, block: Media) -> str:
        if block.url is not None:
            return block.url
        if block.data is None:
            raise MalformedPayload('media block carries neither data nor url')
        return f'data:{block.media_type};base64,{base64.b64encode(block.data).decode()}'

    def _lower_tool_call(self, call: ToolCall) -> dict[str, Any]:
        # arguments are a json string on this wire format. the text as received
        # wins, because re-encoding a malformed call would hide the problem
        arguments = call.args_raw if call.args_raw is not None else json.dumps(call.args)
        return {
            'id': call.call_id,
            'type': 'function',
            'function': {'name': call.name, 'arguments': arguments},
        }

    def _lower_tool(self, tool: ToolSpec) -> dict[str, Any]:
        function: dict[str, Any] = {
            'name': tool.name,
            'description': tool.description,
            'parameters': tool.parameters,
        }
        if tool.strict:
            function['strict'] = True
        return {'type': 'function', 'function': function}

    def _lower_tool_choice(self, choice: ToolChoice) -> str | dict[str, Any]:
        if choice.mode is ToolChoiceMode.NONE:
            return 'none'
        if choice.name is not None:
            return {'type': 'function', 'function': {'name': choice.name}}
        if choice.mode is ToolChoiceMode.REQUIRED:
            return 'required'
        return 'auto'

    def _blocks_text(self, blocks: Sequence[Block]) -> str:
        return '\n'.join(block.text for block in blocks if isinstance(block, Text))

    def _parse_message(self, message: Mapping[str, Any]) -> list[Block]:
        blocks: list[Block] = []
        reasoning = message.get('reasoning_content')
        if reasoning:
            blocks.append(Reasoning(text=reasoning))
        content = message.get('content')
        if content:
            blocks.append(Text(text=content))
        refusal = message.get('refusal')
        if refusal:
            blocks.append(Unknown(kind='refusal', payload={'text': refusal}))
        for entry in message.get('tool_calls') or []:
            blocks.append(self._parse_tool_call(entry))
        return blocks

    def _parse_tool_call(self, entry: Mapping[str, Any]) -> ToolCall:
        function = entry.get('function') or {}
        arguments = function.get('arguments')
        args: dict[str, Any] = {}
        args_raw: str | None = None
        if isinstance(arguments, str):
            args_raw = arguments
            args = _maybe_json(arguments)
        elif isinstance(arguments, Mapping):
            args = dict(arguments)
        return ToolCall(
            call_id=str(entry.get('id') or ''),
            name=str(function.get('name') or ''),
            args=args,
            args_raw=args_raw,
        )

    def _parse_tool_call_delta(self, entry: Mapping[str, Any]) -> list[StreamEvent]:
        index = _FIRST_TOOL_INDEX + int(entry.get('index') or 0)
        function = entry.get('function') or {}
        events: list[StreamEvent] = []
        # the first entry of an index carries id and name, later ones carry only
        # argument fragments
        if entry.get('id') or function.get('name'):
            events.append(
                BlockStarted(
                    index=index,
                    kind='tool_call',
                    call_id=entry.get('id'),
                    name=function.get('name'),
                )
            )
        if function.get('arguments'):
            events.append(ArgsDelta(index=index, fragment=function['arguments']))
        return events

    def _first_choice(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        choices = payload.get('choices')
        if not isinstance(choices, list) or not choices:
            raise MalformedPayload('payload carries no choices')
        return choices[0]

    def _error_detail(self, payload: Mapping[str, Any]) -> str:
        error = payload.get('error')
        if isinstance(error, Mapping) and error.get('message'):
            return str(error['message'])
        return str(payload) if payload else 'no error body'

    def _stop_reason(self, finish_reason: str | None) -> StopReason:
        match finish_reason:
            case 'stop':
                return StopReason.END_TURN
            case 'tool_calls' | 'function_call':
                return StopReason.TOOL_USE
            case 'length':
                return StopReason.MAX_TOKENS
            case 'content_filter':
                return StopReason.CONTENT_FILTER
            case _:
                return StopReason.UNKNOWN

    def _parse_usage(self, usage: Mapping[str, Any] | None) -> Usage:
        if not usage:
            return Usage()
        completion_details = usage.get('completion_tokens_details') or {}
        prompt_details = usage.get('prompt_tokens_details') or {}
        # this format reports cache reads but never cache writes
        return Usage(
            input_tokens=int(usage.get('prompt_tokens') or 0),
            output_tokens=int(usage.get('completion_tokens') or 0),
            cached_read_tokens=int(prompt_details.get('cached_tokens') or 0),
            reasoning_tokens=int(completion_details.get('reasoning_tokens') or 0),
        )


def _maybe_json(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
