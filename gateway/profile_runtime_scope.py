"""Profile runtime binding without initializing the gateway runner."""

from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Optional


def _load_profile_secret_scope(profile_home: Path) -> dict:
    """Hydrate and load one profile's secrets under its home override."""
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from hermes_cli.env_loader import hydrate_profile_secret_sources
    from tui_gateway.launch_profile_policy import owner_secret_scope

    home_token = set_hermes_home_override(str(profile_home))
    try:
        hydrate_profile_secret_sources(Path(profile_home))
        return owner_secret_scope(Path(profile_home))
    finally:
        reset_hermes_home_override(home_token)


@contextmanager
def profile_runtime_scope(
    profile_home: Path, prepared_secret_scope: Optional[dict] = None, *,
    hydrate_secrets: bool = True, prepared_terminal_scope: Optional[dict] = None,
    load_secrets: Optional[Callable[[Path], dict]] = None,
):
    """Bind a profile's home, secrets and terminal policy for one activity."""
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from agent.secret_scope import set_secret_scope, reset_secret_scope

    home_token = secret_token = None
    try:
        home_token = set_hermes_home_override(str(profile_home))
        if prepared_secret_scope is not None:
            secrets = prepared_secret_scope
        elif hydrate_secrets:
            secrets = (load_secrets or _load_profile_secret_scope)(Path(profile_home))
        else:
            from tui_gateway.launch_profile_policy import owner_secret_scope
            secrets = owner_secret_scope(Path(profile_home))
        secret_token = set_secret_scope(secrets, profile_home=str(profile_home))
        # A complete policy prevents a prior profile's ambient TERMINAL_* values leaking in.
        from tools.terminal_scope import install_and_reset_profile_terminal_scope

        with install_and_reset_profile_terminal_scope(Path(profile_home), prepared=prepared_terminal_scope):
            yield
    finally:
        if secret_token is not None:
            reset_secret_scope(secret_token)
        if home_token is not None:
            reset_hermes_home_override(home_token)
