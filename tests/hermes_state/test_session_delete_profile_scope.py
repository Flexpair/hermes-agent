"""Deletion hooks bind the store owner's complete scope, including lazy discovery."""

from pathlib import Path
from types import SimpleNamespace

import hermes_bootstrap  # Activate dependencies before the home I/O guard.
import pytest

from agent.secret_scope import get_secret, reset_secret_scope, set_secret_scope
from hermes_constants import get_hermes_home, reset_hermes_home_override, set_hermes_home_override
from hermes_state_common import emit_session_deleted
from tools.terminal_scope import reset_terminal_scope, set_terminal_scope, terminal_env


@pytest.mark.parametrize("same_home", [False, True])
@pytest.mark.parametrize("failure", [None, "discovery", "delivery"])
def test_owner_scope_and_restore(tmp_path, monkeypatch, same_home, failure):
    from hermes_cli import lifecycle, plugins

    launch = tmp_path / ".hermes"
    target = launch / "profiles" / "repair"
    target.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(launch))
    (target / ".env").write_text("OPENAI_API_KEY=test-owner-only\n")
    (target / "config.yaml").write_text("terminal:\n  env: local\n  cwd: /test-owner\n")
    monkeypatch.setattr(lifecycle, "_observe", lambda *a, **kw: None)
    seen = []

    def snapshot(stage):
        seen.append((stage, get_hermes_home(), get_secret("OPENAI_API_KEY"),
                     terminal_env("TERMINAL_CWD")))
        if failure == stage:
            raise RuntimeError("test callback failure")

    class Manager:
        _discovered = False

        def discover_and_load(self):
            snapshot("discovery")
            self._discovered = True

        def invoke_hook(self, name, **payload):
            assert name == "on_session_delete"
            assert payload["profile"] == "repair"
            snapshot("delivery")
            return []

    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: Manager())
    monkeypatch.setattr(plugins, "_join_background_discovery", lambda: None)
    ambient_home = target if same_home else launch
    home_token = set_hermes_home_override(str(ambient_home))
    secret_token = set_secret_scope({"OPENAI_API_KEY": "test-launch-only"}, profile_home=str(launch))
    terminal_token = set_terminal_scope({"TERMINAL_CWD": "/test-launch"})
    try:
        emit_session_deleted(SimpleNamespace(db_path=target / "state.db"), ["s"], reason="delete")
        expected_stages = ["discovery"] if failure == "discovery" else ["discovery", "delivery"]
        assert seen == [(stage, target, "test-owner-only", "/test-owner") for stage in expected_stages]
        assert get_hermes_home() == ambient_home
        assert get_secret("OPENAI_API_KEY") == "test-launch-only"
        assert terminal_env("TERMINAL_CWD") == "/test-launch"
    finally:
        reset_terminal_scope(terminal_token)
        reset_secret_scope(secret_token)
        reset_hermes_home_override(home_token)


@pytest.mark.parametrize("own_profile", [True, False])
@pytest.mark.parametrize("mirrored_home", [False, True])
def test_launch_env_only_terminal_policy_is_owner_only(tmp_path, monkeypatch, own_profile, mirrored_home):
    from agent import secret_scope
    import hermes_constants
    from hermes_cli import lifecycle, plugins
    from tui_gateway import launch_profile_policy

    launch = tmp_path / ".hermes" / "profiles" / "launcher"
    other = launch.parent / "repair"
    launch.mkdir(parents=True)
    other.mkdir()
    target = launch if own_profile else other
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(launch))
    monkeypatch.setattr(hermes_constants, "_PINNED_PROCESS_HERMES_HOME", str(launch))
    monkeypatch.setattr(launch_profile_policy, "_snapshot", None)
    monkeypatch.setattr(secret_scope, "_MULTIPLEX_ACTIVE", False)
    monkeypatch.setenv("TERMINAL_ENV", "ssh")
    monkeypatch.setenv("TERMINAL_SSH_HOST", "launch-only.invalid")
    monkeypatch.setenv("OPENAI_API_KEY", "test-launch-env-only")
    (other / ".env").write_text("OPENAI_API_KEY=test-other-only\n")
    (other / "config.yaml").write_text("terminal:\n  env: local\n")
    launch_profile_policy.activate_multi_profile_hosting()
    # A hosted turn may mirror its home into environ after the launch snapshot.
    if mirrored_home:
        monkeypatch.setenv("HERMES_HOME", str(target))
    monkeypatch.setenv("TERMINAL_ENV", "local")
    monkeypatch.setenv("TERMINAL_SSH_HOST", "stale-ambient.invalid")
    monkeypatch.setattr(lifecycle, "_observe", lambda *a, **kw: None)
    seen = []

    def snapshot(stage):
        seen.append((stage, get_hermes_home(), get_secret("OPENAI_API_KEY"),
                     terminal_env("TERMINAL_ENV"), terminal_env("TERMINAL_SSH_HOST")))

    class Manager:
        _discovered = False

        def discover_and_load(self):
            snapshot("discovery")
            self._discovered = True

        def invoke_hook(self, name, **payload):
            assert name == "on_session_delete"
            assert payload["profile"] == ("launcher" if own_profile else "repair")
            snapshot("delivery")
            return []

    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: Manager())
    monkeypatch.setattr(plugins, "_join_background_discovery", lambda: None)
    home_token = set_hermes_home_override(str(target))
    secret_token = set_secret_scope({"OPENAI_API_KEY": "test-stale-only"}, profile_home=str(other))
    terminal_token = set_terminal_scope({"TERMINAL_ENV": "local", "TERMINAL_SSH_HOST": "stale-scope.invalid"})
    try:
        emit_session_deleted(SimpleNamespace(db_path=target / "state.db"), ["s"], reason="delete")
        expected = ("test-launch-env-only", "ssh", "launch-only.invalid") if own_profile else (
            "test-other-only", "local", "")
        assert seen == [(stage, target, *expected) for stage in ("discovery", "delivery")]
        assert get_hermes_home() == target
        assert get_secret("OPENAI_API_KEY") == "test-stale-only"
        assert terminal_env("TERMINAL_ENV") == "local"
        assert terminal_env("TERMINAL_SSH_HOST") == "stale-scope.invalid"
    finally:
        reset_terminal_scope(terminal_token)
        reset_secret_scope(secret_token)
        reset_hermes_home_override(home_token)


def test_unknown_store_home_keeps_ambient_scope(tmp_path, monkeypatch):
    from hermes_cli import lifecycle

    launch = tmp_path / ".hermes"
    launch.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(launch))
    seen = []
    monkeypatch.setattr(lifecycle, "invoke_hook", lambda name, **kw: seen.append(
        (get_hermes_home(), get_secret("OPENAI_API_KEY"), terminal_env("TERMINAL_CWD"), kw["profile"])))
    secret_token = set_secret_scope({"OPENAI_API_KEY": "test-launch-only"}, profile_home=str(launch))
    terminal_token = set_terminal_scope({"TERMINAL_CWD": "/test-launch"})
    try:
        emit_session_deleted(SimpleNamespace(db_path=tmp_path / "other" / "state.db"), ["s"], reason="delete")
        assert seen == [(launch, "test-launch-only", "/test-launch", None)]
    finally:
        reset_terminal_scope(terminal_token)
        reset_secret_scope(secret_token)
