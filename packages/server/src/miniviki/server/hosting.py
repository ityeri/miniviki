import os

from miniviki.core.errors import MinivikiError
from miniviki.core.llm import EchoClient, LLMClient, OpenAICompatClient, ScriptedClient, reply

from .bootstrap import Runtime

TRUE_WORDS = {"1", "true", "yes", "on"}


def flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in TRUE_WORDS


def build_client() -> LLMClient:
    """Pick a model client from the environment.

    `echo` and `script` exist so the whole path can be driven with no key and no
    network, which is how this gets verified.
    """
    mode = os.environ.get("MINIVIKI_LLM", "openai")
    if mode == "echo":
        return EchoClient()
    if mode == "script":
        raw = os.environ.get("MINIVIKI_SCRIPT", "")
        return ScriptedClient(script=[reply(text) for text in raw.split("|") if text])
    base_url = os.environ.get("MINIVIKI_LLM_BASE_URL")
    api_key = os.environ.get("MINIVIKI_LLM_API_KEY")
    model = os.environ.get("MINIVIKI_LLM_MODEL")
    if not (base_url and api_key and model):
        raise MinivikiError(
            "set MINIVIKI_LLM=echo for local work, or MINIVIKI_LLM_BASE_URL,"
            " MINIVIKI_LLM_API_KEY and MINIVIKI_LLM_MODEL together"
        )
    return OpenAICompatClient(base_url=base_url, api_key=api_key, model=model)


def build_runtime() -> Runtime:
    return Runtime.build(
        llm=build_client(),
        home=os.environ.get("MINIVIKI_HOME"),
        exec_requires_approval=flag("MINIVIKI_EXEC_APPROVAL")
    )
