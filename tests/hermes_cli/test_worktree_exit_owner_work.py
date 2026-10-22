"""Viewer exit cannot authorize gateway worktree cleanup."""
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Import the real facade without leaving process-exit I/O callbacks behind.
with patch('atexit.register'):
    import cli as real_cli

import pytest

# Bootstrap is an import-time concern; load it before the per-test home I/O guard.
import hermes_cli.main

from hermes_cli import worktree_exit, worktree_ops
from hermes_cli.cli_tui_runtime_mixin import CLITuiRuntimeMixin
from hermes_cli.gateway_agent import GatewayAgent


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    from hermes_cli import curses_ui, worktree_sweep
    from agent.vault_backends import unlock
    from tools import voice_mode
    info = {'path': str(tmp_path), 'repo_root': str(tmp_path), 'exit_choice': 'discard'}
    menu, remove, archive = Mock(return_value=2), Mock(), Mock()
    monkeypatch.setattr(worktree_exit, '_has_tty', lambda: True)
    monkeypatch.setattr(worktree_exit, 'worktree_state', lambda _: 'dirty')
    monkeypatch.setattr(worktree_exit, '_still_in_use', lambda _: False)
    monkeypatch.setattr(curses_ui, 'curses_radiolist', menu)
    monkeypatch.setattr(worktree_ops, '_git_quiet', remove)
    monkeypatch.setattr(worktree_ops, 'release_lsp_clients', Mock())
    monkeypatch.setattr(worktree_sweep, 'archive_then_remove', archive)
    for name in ('lock', 'set_code_prompt_callback', 'set_save_login_prompt_callback', 'set_unlock_prompt_callback'):
        monkeypatch.setattr(unlock, name, Mock())
    monkeypatch.setattr(voice_mode, 'cleanup_temp_recordings', Mock())
    events = []
    cli = SimpleNamespace(_DIM='', _RST='', _cprint=Mock(), _signal_watchdog_armed=False,
                          _active_worktree=info, _invoke_interrupted_session_end=Mock(),
                          _run_cleanup=lambda: events.append('cleanup'),
                          set_approval_callback=Mock(), set_secret_capture_callback=Mock(),
                          set_sudo_password_callback=Mock())
    for name, value in vars(cli).items():
        monkeypatch.setattr(real_cli, name, value)
    monkeypatch.setattr(real_cli, '_active_agent_ref', None)
    monkeypatch.setattr(real_cli, '_worktree_cli_ref', None)
    probes = Mock(return_value=False)
    monkeypatch.setattr(real_cli, '_worktree_is_dirty', probes)
    monkeypatch.setattr(real_cli, '_worktree_has_unpushed_commits', probes)
    monkeypatch.setattr(real_cli, '_git_quiet', remove)
    monkeypatch.setattr(real_cli, 'release_lsp_clients', Mock())
    monkeypatch.setattr(worktree_ops, 'removal_blocked', lambda _: None)
    info['branch'] = 'test-owner'

    class Viewer(real_cli.HermesCLI):
        def _init_display_options(self, *a): pass
        def _init_model_routing(self, *a): pass
        def _init_runtime_state(self, *a): pass
        def _pet_stop_anim(self): pass
        def _persist_active_session_before_close(self): events.append('persist')
        def _discard_session_if_empty(self, sid): events.append('prune')
        def _print_exit_summary(self): events.append('summary')
        def _release_active_session(self): events.append('release')

    viewer = Viewer()
    viewer.agent = object.__new__(GatewayAgent)
    viewer.agent.session_id = 'owner'
    viewer.session_id = 'owner'
    viewer._gateway_session_open = True
    viewer._agent_running = False
    viewer._detach_on_exit = True
    viewer._voice_recorder = None
    viewer._delete_session_on_exit = False
    viewer._session_db = SimpleNamespace(call=Mock(), end_session=lambda *a: events.append('detach'))
    return SimpleNamespace(info=info, menu=menu, remove=remove, archive=archive,
                           viewer=viewer, cli=cli, events=events, path=tmp_path)


@pytest.mark.parametrize('state', ['active', 'pending', 'liveworker', 'idle', 'unknown', 'no_agent'])
@pytest.mark.parametrize('choice', [None, 'archive', 'discard'])
def test_real_shutdown_keeps_gateway_checkout(boundary, state, choice):
    b = boundary
    b.info['exit_choice'] = choice
    b.viewer._agent_running = state == 'active'
    b.viewer._session_db.call.return_value = {
        'running': state == 'active', 'pending': [{}] if state == 'pending' else [],
        'prompts': [], 'workers': [{}] if state == 'liveworker' else []}
    if state == 'unknown':
        b.viewer._session_db.call.side_effect = OSError('offline')
    if state == 'no_agent':
        b.viewer.agent = None
    b.viewer._tui_shutdown()
    # The explicit-info atexit callback survives active-agent teardown.
    real_cli._active_agent_ref = None
    real_cli._cleanup_worktree(b.info)
    assert b.events == ['persist', 'detach', 'prune', 'cleanup', 'summary', 'release']
    b.viewer._session_db.call.assert_not_called()
    b.menu.assert_not_called()
    b.remove.assert_not_called()
    b.archive.assert_not_called()
    b.cli._invoke_interrupted_session_end.assert_not_called()
    assert b.viewer._should_exit and b.path.exists()


@pytest.mark.parametrize('session_file', ['owner', 'missing', 'malformed'])
@pytest.mark.parametrize('code', [0, 130, 1])
def test_real_launcher_keeps_canonical_checkout(boundary, monkeypatch, session_file, code):
    b = boundary
    from hermes_cli import main_tui_launch as launch, shared_session_attach, config, gateway_chat
    from hermes_cli.gateway_connection import GatewayConnection
    from tools.environments import local
    monkeypatch.setattr(local, 'build_subprocess_env', lambda **kw: {})
    monkeypatch.setattr(shared_session_attach, 'configure_tui_attachment', lambda *a: None)
    monkeypatch.setattr(config, 'apply_terminal_config_to_env', lambda **kw: None)
    monkeypatch.setattr(gateway_chat, 'shell_client_env', dict)
    monkeypatch.setattr(launch, '_setup_tui_worktree', lambda: b.info)
    monkeypatch.setattr(launch, '_make_tui_argv', lambda *a: (['node'], b.path))
    monkeypatch.setattr(launch, '_print_tui_exit_summary', Mock())
    owner, retained = Mock(), Mock()
    monkeypatch.setattr(GatewayConnection, 'shared', owner)
    monkeypatch.setattr(worktree_ops, '_retain_worktree_for_session', retained)

    def child(*a, env, **kw):
        from pathlib import Path
        path = Path(env['HERMES_TUI_ACTIVE_SESSION_FILE'])
        if session_file == 'owner':
            path.write_text('{"session_id":"owner"}')
        elif session_file == 'malformed':
            path.write_text('not json')
        else:
            path.unlink()
        return code

    monkeypatch.setattr(launch.subprocess, 'call', child)
    with pytest.raises(SystemExit) as exc:
        launch._launch_tui(worktree=True, native_mode=False)
    assert exc.value.code == code
    owner.assert_not_called()
    b.menu.assert_not_called()
    b.remove.assert_not_called()
    b.archive.assert_not_called()
    assert b.path.exists()
    if session_file == 'owner':
        assert retained.call_args.args[2] == 'owner'
    else:
        retained.assert_not_called()


@pytest.mark.parametrize('choice', [None, 'archive', 'discard'])
@pytest.mark.parametrize('owner', ['agent', 'no_agent'])
def test_atexit_without_viewer_shutdown_keeps_gateway_checkout(boundary, choice, owner):
    b = boundary
    b.info['exit_choice'] = choice
    if owner == 'agent':
        real_cli._active_agent_ref = b.viewer.agent
        real_cli._worktree_cli_ref = None  # exercise the agent guard independently
    else:
        b.viewer.agent = None
    real_cli._cleanup_worktree(b.info)
    b.remove.assert_not_called()
    b.archive.assert_not_called()
    real_cli._worktree_is_dirty.assert_not_called()
    assert real_cli._active_worktree is b.info


def test_standalone_shutdown_still_discards(boundary):
    b = boundary
    b.viewer.agent = None
    b.viewer._gateway_session_open = False
    b.viewer._session_db = None
    b.viewer._tui_shutdown()
    b.menu.assert_called_once()
    assert b.remove.call_args.args[0] == ['worktree', 'remove', str(b.path), '--force']
    b.archive.assert_not_called()
