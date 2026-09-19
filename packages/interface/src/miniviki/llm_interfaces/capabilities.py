from dataclasses import dataclass, field

from miniviki.llm_interfaces.content import MediaKind


@dataclass(frozen=True)
class Capabilities:
    # a provider that cannot express a requested feature is a request time
    # failure, not something to discover halfway through a stream
    tools: bool = False
    parallel_tool_calls: bool = False
    json_schema_strict: bool = False
    reasoning: bool = False
    reasoning_visible: bool = False
    # whether the opaque part of a reasoning block survives a round trip
    reasoning_opaque_roundtrip: bool = False
    media: frozenset[MediaKind] = field(default_factory=frozenset)
    # provider executed tools have no client side approval gate
    server_side_tools: bool = False
    # server held conversation state (store, previous_response_id, conversation)
    stateful_continuation: bool = False
    background_jobs: bool = False
    stream_usage: bool = False
