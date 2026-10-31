"""Held-row CAS rejection is a durable worker no-op, not a failed transport."""
import json
from types import SimpleNamespace

import pytest

from agent.micro_compaction import MicroCompactionMixin
import hermes_bootstrap  # Activate dependencies before the home I/O guard.
from hermes_state_errors import HeldRowRewrittenError


def test_archive_cas_miss_is_receipted_and_future_writes_finish(worker):
    db, store = worker
    store.append_messages_batch('owned', [{'role': 'user', 'content': 'old'}])
    held = store.get_messages_as_conversation('owned', include_row_ids=True)
    db.set_user_message_content('owned', held[0]['_row_id'], 'winner')
    revision = db.get_session('owned')['runtime_revision']
    sequence = store.journal['next_sequence']
    replacement = [{'role': 'assistant', 'content': 'stale summary'}]
    calls = []
    rpc = store.rpc

    def boundary(method, **params):
        calls.append((method, params))
        return rpc(method, **params)

    store.rpc = boundary
    with pytest.raises(HeldRowRewrittenError):
        store.archive_and_compact('owned', replacement, held_for_cas=held,
                                  model_config_patch={'_proactive_prune_rearm_tokens': 99})
    receipt = json.loads(db._read_one(
        'SELECT result_json FROM worker_receipts WHERE execution_id=? AND sequence=?',
        ('worker', sequence))[0])
    assert receipt == {'value': None, 'annotations': [], 'stale_held_rows': True}
    assert db.get_session('owned')['runtime_revision'] == revision
    assert db._read_one('SELECT last_sequence FROM worker_executions')[0] == sequence
    assert store.failure is None and store.journal['pending'] == []
    assert store.journal['next_sequence'] == sequence + 1
    assert json.loads(store.path.read_text()) == store.journal
    assert '_row_id' not in replacement[0]
    assert rpc(calls[-1][0], **calls[-1][1]) == receipt  # exact replay is the same no-op
    assert [m['content'] for m in db.get_messages_as_conversation('owned')] == ['winner']
    assert db.get_session_model_config_value('owned', '_proactive_prune_rearm_tokens') is None
    store.append_messages_batch('owned', [{'role': 'assistant', 'content': 'after'}])
    store.finish()
    assert db._read_one('SELECT status FROM worker_executions')[0] == 'terminal'
    assert [m['content'] for m in db.get_messages_as_conversation('owned')] == ['winner', 'after']
    assert store.failure is None and store.journal['pending'] == []


def test_micro_compaction_discards_commit_window_cas_miss(worker):
    db, store = worker
    store.append_messages_batch('owned', [{'role': 'user', 'content': 'old'}])
    held = store.get_messages_as_conversation('owned', include_row_ids=True)
    watermark = store.get_active_message_watermark('owned')
    rpc = store.rpc

    def boundary(method, **params):
        if params['operation'] == 'compression.archive':
            db.set_user_message_content('owned', held[0]['_row_id'], 'winner')
        return rpc(method, **params)

    store.rpc = boundary
    marker = {'role': 'assistant', 'content': 'stale summary', '_micro_compact_marker': True}
    assert MicroCompactionMixin._sync_micro_compact_to_db(
        SimpleNamespace(_session_db=store, _session_id='owned'), [marker],
        held=held, start_watermark=watermark) is False
    assert '_db_persisted' not in marker and '_row_id' not in marker
    assert store.failure is None and store.journal['pending'] == []
    assert [m['content'] for m in db.get_messages_as_conversation('owned')] == ['winner']
    store.append_messages_batch('owned', [{'role': 'assistant', 'content': 'after'}])
    store.finish()
    assert db._read_one('SELECT status FROM worker_executions')[0] == 'terminal'
