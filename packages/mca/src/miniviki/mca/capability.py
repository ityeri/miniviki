from dataclasses import dataclass
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class ClientCapability:
    """What this client can actually do.

    The server never assumes any of it: an undeclared capability means the
    matching tool is not exposed and the prompt does not promise it.
    """

    label: str = ""
    markdown: bool = True
    images: bool = False
    attachments: bool = False
    streaming: bool = True
    approval_ui: bool = False
    interrupt: bool = False
    shell: bool = False
    filesystem: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "markdown": self.markdown,
            "images": self.images,
            "attachments": self.attachments,
            "streaming": self.streaming,
            "approval_ui": self.approval_ui,
            "interrupt": self.interrupt,
            "shell": self.shell,
            "filesystem": self.filesystem
        }

    @staticmethod
    def from_json(raw_data: dict[str, Any]) -> Self:
        return ClientCapability(
            label=str(raw_data.get("label", "")),
            markdown=bool(raw_data.get("markdown", True)),
            images=bool(raw_data.get("images", False)),
            attachments=bool(raw_data.get("attachments", False)),
            streaming=bool(raw_data.get("streaming", True)),
            approval_ui=bool(raw_data.get("approval_ui", False)),
            interrupt=bool(raw_data.get("interrupt", False)),
            shell=bool(raw_data.get("shell", False)),
            filesystem=bool(raw_data.get("filesystem", False))
        )

    def flags(self) -> tuple[str, ...]:
        return tuple(
            name for name, value in self.to_json().items() if name != "label" and value
        )
