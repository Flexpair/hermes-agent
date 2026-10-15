"""Fork provider removal stays consistent across catalog and interactive selection."""


def test_removed_builtin_providers_absent_from_catalog_and_picker():
    from hermes_cli.models_catalog_static import CANONICAL_PROVIDERS, PROVIDER_GROUPS, _PROVIDER_MODELS
    from hermes_cli.main_provider_setup import _GENERIC_API_KEY_PROVIDERS, _build_provider_picker_rows
    from hermes_cli.models import list_available_providers

    removed = {"alibaba", "deepseek", "kimi-coding", "kimi-coding-cn", "minimax",
               "minimax-oauth", "minimax-cn", "qwen-oauth", "stepfun", "xiaomi", "zai"}
    assert not removed.intersection(_PROVIDER_MODELS)
    assert not removed.intersection(p.slug for p in CANONICAL_PROVIDERS)
    assert not removed.intersection(_GENERIC_API_KEY_PROVIDERS)
    assert not removed.intersection(member for _, _, members in PROVIDER_GROUPS.values() for member in members)
    assert not removed.intersection(p["id"] for p in list_available_providers())
    rows, _ = _build_provider_picker_rows({}, "", {}, {})
    assert not removed.intersection(slug for key, _, members in rows for slug in ([key] + members))


def test_picker_excludes_canonical_provider_missing_from_registry(monkeypatch):
    from hermes_cli import auth
    from hermes_cli.main_provider_setup import _build_provider_picker_rows

    monkeypatch.delitem(auth.PROVIDER_REGISTRY, "gemini")
    rows, _ = _build_provider_picker_rows({}, "", {}, {})
    assert "gemini" not in {member for key, _, members in rows for member in [key, *members]}


def test_missing_registry_provider_selection_does_not_dispatch(monkeypatch, capsys):
    import sys
    from types import ModuleType

    monkeypatch.setitem(sys.modules, "hermes_bootstrap", ModuleType("hermes_bootstrap"))
    import hermes_cli._early_recovery as recovery
    monkeypatch.setattr(recovery, "restore_interrupted_pull", lambda: False)
    import hermes_cli.main as main
    from hermes_cli import auth

    monkeypatch.setattr(main, "_pick_provider", lambda *args: "gemini")
    monkeypatch.setattr(main, "_resolve_active_provider", lambda *args: None)
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {"model": {"provider": "nous", "default": "old"}})
    monkeypatch.delitem(auth.PROVIDER_REGISTRY, "gemini")
    monkeypatch.setattr(main, "_model_flow_api_key_provider", lambda *args: (_ for _ in ()).throw(AssertionError("dispatched")))
    main.select_provider_and_model()
    assert "no longer available" in capsys.readouterr().out
