import logging

import pytest
from miniviki.core.errors import MinivikiError
from miniviki.server.logging import (
    DEFAULT_LOG_LEVEL,
    HANDLER_MARKER,
    SERVER_LOGGERS,
    adopt_server_loggers,
    resolve_level,
    setup_logging,
)


def test_an_unknown_level_is_a_boot_error():
    with pytest.raises(MinivikiError):
        resolve_level("loud")


def test_a_level_name_is_read_case_insensitively():
    assert resolve_level("debug") == logging.DEBUG
    assert resolve_level("WARNING") == logging.WARNING


def test_no_level_configured_falls_back_to_info():
    assert resolve_level("") == DEFAULT_LOG_LEVEL


def test_the_server_loggers_are_handed_back_to_the_root(monkeypatch):
    target = logging.getLogger(SERVER_LOGGERS[0])
    monkeypatch.setattr(target, "handlers", [logging.StreamHandler()])
    monkeypatch.setattr(target, "propagate", False)
    adopt_server_loggers()
    assert target.handlers == []
    assert target.propagate is True


def test_setup_logging_installs_a_root_handler(monkeypatch):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.WARNING)
    setup_logging(logging.DEBUG)
    assert root.handlers
    assert root.level == logging.DEBUG


def test_setup_logging_does_not_stack_handlers(monkeypatch):
    """reger appends unconditionally, so a second boot would double every line."""
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.WARNING)
    setup_logging(logging.INFO)
    once = len(root.handlers)
    setup_logging(logging.INFO)
    assert len(root.handlers) == once
    assert all(getattr(handler, HANDLER_MARKER, False) for handler in root.handlers)


def test_setup_logging_leaves_foreign_handlers_alone(monkeypatch):
    root = logging.getLogger()
    foreign = logging.StreamHandler()
    monkeypatch.setattr(root, "handlers", [foreign])
    monkeypatch.setattr(root, "level", logging.WARNING)
    setup_logging(logging.INFO)
    assert foreign in root.handlers
    assert not getattr(foreign, HANDLER_MARKER, False)
