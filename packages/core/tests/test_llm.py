import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest
from miniviki.core import MinivikiError
from miniviki.core.llm import (
    Message,
    OpenAICompatClient,
    ScriptedClient,
    ToolSchema,
    call,
    from_openai_response,
    reply,
    to_openai_messages,
    to_openai_tools,
)


class _StubHandler(BaseHTTPRequestHandler):
    received: ClassVar[list[dict]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        _StubHandler.received.append(json.loads(self.rfile.read(length)))
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "hello from the stub",
                        "tool_calls": [
                            {
                                "id": "c9",
                                "type": "function",
                                "function": {"name": "exec", "arguments": "{\"command\": \"ls\"}"}
                            }
                        ]
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 4,
                "prompt_tokens_details": {"cached_tokens": 7}
            }
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        return None


@pytest.fixture
def stub_server():
    _StubHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    thread.join(timeout=5)


async def test_scripted_client_replays_the_script():
    client = ScriptedClient(script=[reply("first"), reply("second")])
    assert (await client.complete([])).message.content == "first"
    assert (await client.complete([])).message.content == "second"
    assert (await client.complete([])).message.content == ""


async def test_scripted_client_records_what_it_was_asked():
    client = ScriptedClient(script=[reply("x")])
    await client.complete([Message(role="user", content="hi")], [ToolSchema(name="exec")])
    assert client.seen[0][0].content == "hi"
    assert client.tools_seen[0] == ("exec",)


async def test_scripted_tool_call_helper():
    client = ScriptedClient(script=[call("exec", {"command": "ls"}, call_id="c3")])
    tool_calls = (await client.complete([])).message.tool_calls
    assert tool_calls[0].name == "exec"
    assert tool_calls[0].arguments == {"command": "ls"}
    assert tool_calls[0].id == "c3"


def test_messages_translate_into_the_openai_shape():
    message = Message(
        role="assistant",
        content="thinking",
        tool_calls=(call("exec", {"command": "ls"}).message.tool_calls[0],)
    )
    raw = to_openai_messages([message])[0]
    assert raw["role"] == "assistant"
    assert raw["tool_calls"][0]["type"] == "function"
    assert raw["tool_calls"][0]["function"]["name"] == "exec"
    assert json.loads(raw["tool_calls"][0]["function"]["arguments"]) == {"command": "ls"}


def test_tool_schemas_translate_into_the_openai_shape():
    schema = ToolSchema(name="exec", description="run", parameters={"type": "object"})
    raw = to_openai_tools([schema])
    assert raw[0]["function"]["description"] == "run"


def test_tool_schema_without_parameters_still_declares_an_object():
    raw = to_openai_tools([ToolSchema(name="exec")])
    assert raw[0]["function"]["parameters"] == {"type": "object", "properties": {}}


def test_response_parsing_reads_content_tools_and_usage():
    completion = from_openai_response(
        {
            "choices": [
                {
                    "message": {
                        "content": "ok",
                        "tool_calls": [
                            {"id": "c1", "function": {"name": "exec", "arguments": "{\"a\": 1}"}}
                        ]
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 2,
                "prompt_tokens_details": {"cached_tokens": 3}
            }
        }
    )
    assert completion.message.content == "ok"
    assert completion.message.tool_calls[0].arguments == {"a": 1}
    usage = (completion.prompt_tokens, completion.completion_tokens, completion.cached_tokens)
    assert usage == (5, 2, 3)


def test_malformed_tool_arguments_do_not_explode():
    completion = from_openai_response(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"id": "c1", "function": {"name": "exec", "arguments": "not json"}}
                        ]
                    }
                }
            ]
        }
    )
    assert completion.message.tool_calls[0].arguments == {}


def test_response_without_choices_is_an_error():
    with pytest.raises(MinivikiError):
        from_openai_response({"choices": []})


async def test_openai_compat_client_talks_to_a_real_endpoint(stub_server):
    client = OpenAICompatClient(base_url=stub_server, api_key="test-key", model="stub-model")
    try:
        completion = await client.complete(
            [Message(role="user", content="hi")],
            [ToolSchema(name="exec", description="run")]
        )
    finally:
        await client.aclose()
    assert completion.message.content == "hello from the stub"
    assert completion.message.tool_calls[0].name == "exec"
    assert completion.message.tool_calls[0].arguments == {"command": "ls"}
    assert completion.cached_tokens == 7


async def test_openai_compat_client_sends_the_expected_request(stub_server):
    client = OpenAICompatClient(base_url=stub_server, api_key="test-key", model="stub-model")
    try:
        await client.complete([Message(role="user", content="hi")], [ToolSchema(name="exec")])
    finally:
        await client.aclose()
    sent = _StubHandler.received[-1]
    assert sent["model"] == "stub-model"
    assert sent["messages"] == [{"role": "user", "content": "hi"}]
    assert sent["tools"][0]["function"]["name"] == "exec"
