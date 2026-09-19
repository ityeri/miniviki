import json
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import pytest

from miniviki.llm_interface import (
    ArgsDelta,
    BlockStopped,
    ContextRejected,
    MalformedPayload,
    RateLimited,
    Reasoning,
    Request,
    Role,
    ServerTool,
    StopReason,
    Text,
    TextDelta,
    ToolCall,
    ToolChoice,
    ToolChoiceMode,
    ToolResult,
    ToolSpec,
    Turn,
    UnsupportedCapability,
    UsageReported,
)
from miniviki.llm_interface.openai_compat import (
    ChatCompletionsAdapter,
    OpenAIChatClient,
    sse_payloads,
)

MODEL = 'gpt-x'


def weather_history() -> list[Turn]:
    return [
        Turn(role=Role.USER, blocks=[Text(text='서울 날씨?')]),
        Turn(role=Role.ASSISTANT, blocks=[
            Text(text='확인해볼게요'),
            ToolCall(
                call_id='call_1',
                name='weather',
                args={'city': 'seoul'},
                args_raw='{"city": "seoul"}'
            ),
        ]),
        Turn(role=Role.USER, blocks=[ToolResult(call_id='call_1', content=[Text(text='18')])]),
    ]


def chunk(delta: Mapping[str, Any], finish: str | None = None, choices: bool = True) -> bytes:
    payload: dict[str, Any] = {
        'id': 'chatcmpl-1',
        'object': 'chat.completion.chunk',
        'model': MODEL,
        'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}] if choices else [],
    }
    return f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'.encode()


class FakeTransport:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.url = ''
        self.headers: Mapping[str, str] = {}
        self.body: Mapping[str, Any] = {}

    async def post(self, url, headers, body):
        self.url, self.headers, self.body = url, headers, body
        return self.response


class FakeResponse:
    def __init__(
            self,
            status: int = 200,
            payload: Mapping[str, Any] | None = None,
            frames: Sequence[bytes] | None = None
    ):
        self.status = status
        self.payload = payload or {}
        self.frames = list(frames or [])

    async def json(self) -> Mapping[str, Any]:
        return self.payload

    def chunks(self) -> AsyncIterator[bytes]:
        return _iterate(self.frames)


async def _iterate(frames: Sequence[bytes]) -> AsyncIterator[bytes]:
    for frame in frames:
        yield frame


class FakeHome:
    """stands in for a server that answers with a recorded payload"""

    def __init__(self, *blocks):
        self.blocks = list(blocks)


def test_lower_request_maps_turns_to_messages():
    adapter = ChatCompletionsAdapter()
    body = adapter.lower_request(Request(model=MODEL, instructions='너는 날씨 봇', messages=weather_history()))
    assert body['messages'][0] == {'role': 'system', 'content': '너는 날씨 봇'}
    assert body['messages'][1] == {'role': 'user', 'content': '서울 날씨?'}
    assistant = body['messages'][2]
    assert assistant['role'] == 'assistant'
    assert assistant['content'] == '확인해볼게요'
    # arguments stay a string, and the text as received wins
    assert assistant['tool_calls'][0]['function']['arguments'] == '{"city": "seoul"}'
    # a tool result becomes its own turn here
    assert body['messages'][3] == {'role': 'tool', 'tool_call_id': 'call_1', 'content': '18'}
    assert 'tools' not in body


def test_lower_request_marks_stream_and_asks_for_usage():
    adapter = ChatCompletionsAdapter()
    body = adapter.lower_request(Request(model=MODEL), stream=True)
    assert body['stream'] is True
    assert body['stream_options'] == {'include_usage': True}


def test_lower_request_honours_instructions_role():
    adapter = ChatCompletionsAdapter(instructions_role='developer')
    body = adapter.lower_request(Request(model=MODEL, instructions='x'))
    assert body['messages'][0]['role'] == 'developer'


def test_lower_request_lowers_tools_and_choice():
    adapter = ChatCompletionsAdapter()
    request = Request(
        model=MODEL,
        tools=[ToolSpec(name='weather', description='lookup', parameters={'type': 'object'}, strict=True)],
        tool_choice=ToolChoice(mode=ToolChoiceMode.NONE)
    )
    body = adapter.lower_request(request)
    assert body['tools'][0]['function']['strict'] is True
    assert body['tool_choice'] == 'none'


def test_lower_request_collapses_text_blocks_and_expands_media():
    adapter = ChatCompletionsAdapter()
    turn = Turn(role=Role.USER, blocks=[Text(text='a'), Text(text='b')])
    assert adapter.lower_request(Request(model=MODEL, messages=[turn]))['messages'][0]['content'] == 'a\nb'


def test_lower_request_rejects_what_the_format_cannot_hold():
    adapter = ChatCompletionsAdapter()
    signed = Turn(role=Role.ASSISTANT, blocks=[Reasoning(text='...', opaque=b'\x00sig')])
    with pytest.raises(UnsupportedCapability):
        adapter.lower_request(Request(model=MODEL, messages=[signed]))
    hosted = Turn(role=Role.USER, blocks=[ServerTool(kind='web_search')])
    with pytest.raises(UnsupportedCapability):
        adapter.lower_request(Request(model=MODEL, messages=[hosted]))
    whitelist = Request(model=MODEL, tool_choice=ToolChoice(allowed=['weather']))
    with pytest.raises(UnsupportedCapability):
        adapter.lower_request(whitelist)


def test_parse_completion_reads_blocks_stop_reason_and_usage():
    adapter = ChatCompletionsAdapter()
    payload = {
        'id': 'chatcmpl-1',
        'model': MODEL,
        'choices': [{
            'index': 0,
            'finish_reason': 'tool_calls',
            'message': {
                'role': 'assistant',
                'content': '확인해볼게요',
                'tool_calls': [{
                    'id': 'call_1',
                    'type': 'function',
                    'function': {'name': 'weather', 'arguments': '{"city": "seoul"}'},
                }],
            },
        }],
        'usage': {
            'prompt_tokens': 30,
            'completion_tokens': 12,
            'prompt_tokens_details': {'cached_tokens': 8},
        },
    }
    completion = adapter.parse_completion(payload)
    assert completion.turn.role is Role.ASSISTANT
    assert [type(block) for block in completion.turn.blocks] == [Text, ToolCall]
    call = completion.turn.blocks[1]
    assert call.args == {'city': 'seoul'}
    assert call.args_raw == '{"city": "seoul"}'
    assert completion.stop_reason is StopReason.TOOL_USE
    assert completion.raw_stop_reason == 'tool_calls'
    assert completion.usage.input_tokens == 30
    assert completion.usage.cached_read_tokens == 8
    assert completion.response_id == 'chatcmpl-1'


def test_parse_completion_keeps_malformed_arguments_out_of_the_way():
    adapter = ChatCompletionsAdapter()
    payload = {
        'choices': [{
            'finish_reason': 'tool_calls',
            'message': {'tool_calls': [{'id': 'c', 'function': {'name': 'f', 'arguments': '{oops'}}]},
        }],
    }
    call = adapter.parse_completion(payload).turn.blocks[0]
    assert call.args == {}
    assert call.args_raw == '{oops'


def test_parse_completion_rejects_a_payload_without_choices():
    with pytest.raises(MalformedPayload):
        ChatCompletionsAdapter().parse_completion({'choices': []})


def test_parse_message_carries_reasoning_and_refusal():
    adapter = ChatCompletionsAdapter()
    payload = {
        'choices': [{
            'finish_reason': 'stop',
            'message': {'content': '', 'reasoning_content': '생각중', 'refusal': '못합니다'},
        }],
    }
    assert [type(block).__name__ for block in adapter.parse_completion(payload).turn.blocks] == ['Reasoning', 'Unknown']


def test_parse_event_announces_the_text_block_once():
    adapter = ChatCompletionsAdapter()
    started = adapter.parse_event(json.loads(chunk({'role': 'assistant', 'content': ''})[6:]))
    # the role delta is the only lifecycle signal this wire format gives us
    assert [type(event).__name__ for event in started] == ['Started', 'BlockStarted']
    assert started[1].index == 0
    assert started[1].kind == 'text'
    text = adapter.parse_event(json.loads(chunk({'content': '확인'})[6:]))
    assert text == [TextDelta(index=0, text='확인')]


def test_parse_event_maps_parallel_tool_calls_to_distinct_indices():
    adapter = ChatCompletionsAdapter()
    delta = {'tool_calls': [
        {'index': 0, 'id': 'call_1', 'type': 'function', 'function': {'name': 'weather', 'arguments': ''}},
        {'index': 1, 'id': 'call_2', 'type': 'function', 'function': {'name': 'time', 'arguments': ''}},
    ]}
    events = adapter.parse_event(json.loads(chunk(delta)[6:]))
    assert [event.index for event in events] == [2, 3]
    assert [event.name for event in events] == ['weather', 'time']
    fragment = {'tool_calls': [{'index': 1, 'function': {'arguments': '{"zone"'}}]}
    assert adapter.parse_event(json.loads(chunk(fragment)[6:])) == [ArgsDelta(index=3, fragment='{"zone"')]


def test_parse_event_keeps_unknown_chunks():
    adapter = ChatCompletionsAdapter()
    payload = {'id': 'x', 'choices': []}
    events = adapter.parse_event(payload)
    assert events[0].kind == 'chunk_without_choices'


def test_parse_event_reports_usage_on_the_final_chunk():
    adapter = ChatCompletionsAdapter()
    payload = {'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 4}}
    events = adapter.parse_event(payload)
    assert events == [UsageReported(usage=events[0].usage)]
    assert events[0].usage.output_tokens == 4


def test_parse_event_completes_on_finish_reason():
    adapter = ChatCompletionsAdapter()
    events = adapter.parse_event(json.loads(chunk({}, finish='length')[6:]))
    assert events == [BlockStopped(index=0), events[1]]
    assert events[1].stop_reason is StopReason.MAX_TOKENS
    assert events[1].raw_stop_reason == 'length'


def test_parse_error_classifies_the_status():
    adapter = ChatCompletionsAdapter()
    assert isinstance(adapter.parse_error(429, {'error': {'message': 'slow down'}}), RateLimited)
    long_context = {'error': {'message': 'This model maximum context length is 8192 tokens'}}
    assert isinstance(adapter.parse_error(400, long_context), ContextRejected)
    assert '401' in str(adapter.parse_error(401, {'error': {'message': 'bad key'}}))


async def test_sse_payloads_survive_a_split_multibyte_character():
    frame = chunk({'content': '안녕'})
    head, tail = frame[:20], frame[20:]
    payloads = [payload async for payload in sse_payloads(_iterate((head, tail, b'data: [DONE]\n\n')))]
    assert len(payloads) == 1
    assert payloads[0]['choices'][0]['delta']['content'] == '안녕'


async def test_client_complete_posts_the_lowered_body():
    transport = FakeTransport(FakeResponse(payload={
        'id': 'chatcmpl-1',
        'model': MODEL,
        'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '18도'}}],
    }))
    client = OpenAIChatClient(transport=transport, base_url='https://api.deepseek.com/v1/', api_key='sk-x')
    completion = await client.complete(Request(model=MODEL, messages=[Turn(role=Role.USER, blocks=[Text(text='hi')])]))
    assert transport.url == 'https://api.deepseek.com/v1/chat/completions'
    assert transport.headers['authorization'] == 'Bearer sk-x'
    assert completion.turn.blocks == [Text(text='18도')]
    assert (await client.capabilities()).tools is True


async def test_client_stream_turns_frames_into_canonical_events():
    frames = [
        chunk({'role': 'assistant', 'content': ''}),
        chunk({'content': '확인'}),
        chunk({'tool_calls': [{'index': 0, 'id': 'call_1', 'type': 'function',
                               'function': {'name': 'weather', 'arguments': '{"city":'}}]}),
        chunk({'tool_calls': [{'index': 0, 'function': {'arguments': '"seoul"}'}}]}),
        chunk({}, finish='tool_calls'),
        f'data: {json.dumps({"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 7}})}\n\n'.encode(),
        b'data: [DONE]\n\n'
    ]
    transport = FakeTransport(FakeResponse(frames=frames))
    client = OpenAIChatClient(transport=transport)
    events = [event async for event in client.stream(Request(model=MODEL, messages=weather_history()))]
    kinds = [type(event).__name__ for event in events]
    assert kinds == [
        'Started',
        'BlockStarted',
        'TextDelta',
        'BlockStarted',
        'ArgsDelta',
        'ArgsDelta',
        'BlockStopped',
        'Completed',
        'UsageReported',
    ]
    assert transport.body['stream'] is True
    assert events[1].index == 0
    assert events[3].call_id == 'call_1'
    assert events[7].stop_reason is StopReason.TOOL_USE
    assert events[8].usage.output_tokens == 7


async def test_client_raises_a_classified_error_on_a_failed_stream():
    transport = FakeTransport(FakeResponse(status=429, payload={'error': {'message': 'slow down'}}))
    client = OpenAIChatClient(transport=transport)
    with pytest.raises(RateLimited):
        [event async for event in client.stream(Request(model=MODEL))]
