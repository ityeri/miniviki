CONTEXT_CREATE = "context:create"
BEFORE_LLM = "before_llm"
AFTER_LLM = "after_llm"
BEFORE_TOOL = "before_tool"
AFTER_TOOL = "after_tool"
ON_COMPACT = "on_compact"
RUN_END = "run:end"

DEFAULT_LISTENERS = (
    CONTEXT_CREATE,
    BEFORE_LLM,
    AFTER_LLM,
    BEFORE_TOOL,
    AFTER_TOOL,
    ON_COMPACT,
    RUN_END
)
