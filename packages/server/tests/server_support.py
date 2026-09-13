import json
from contextlib import asynccontextmanager

import httpx
from miniviki.server import Runtime, create_app


@asynccontextmanager
async def serve(runtime: Runtime):
    transport = httpx.ASGITransport(app=create_app(runtime))
    async with httpx.AsyncClient(transport=transport, base_url="http://miniviki.test") as http:
        yield http
    runtime.aclose()


async def collect(http: httpx.AsyncClient, context_id: str, from_seq: int = 0) -> list[dict]:
    async with http.stream(
        "GET", f"/contexts/{context_id}/events", params={"from_seq": from_seq}
    ) as response:
        body = "".join([chunk async for chunk in response.aiter_text()])
    return [
        json.loads(line[len("data: "):])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def kinds(events: list[dict]) -> list[str]:
    return [event["kind"] for event in events]


def tool_results(events: list[dict]) -> list[str]:
    return [str(event["payload"]["content"]) for event in events if event["kind"] == "tool_result"]
