"""模拟 CLI 回执与配置边界；不调用真实模型，不创建系统定时任务。"""

import json
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import study_bridge as bridge
import study_practice as practice

SESSION = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def app(tmp_path):
    root = tmp_path / "app"
    profile = root / "PortableConfig"
    (profile / "StudyLibrary").mkdir(parents=True)
    database = profile / "StudyLibrary/study.db"
    with sqlite3.connect(database) as c:
        c.execute("CREATE TABLE StudyEntries(EntryKey TEXT,Language TEXT,Original TEXT,Translation TEXT,CloudSyncAllowed INTEGER)")
        c.execute("INSERT INTO StudyEntries VALUES('example','en','A coherent mechanism can strengthen a resilient system regardless of constraints.','虚构测试文本',1)")
    fake = root / "fake-cli.exe"
    fake.write_bytes(b"unit-test-placeholder")
    binding = {"Provider":"codex_cli","SessionId":SESSION,"AllowCreate":False,"Executable":str(fake),"WorkDir":str(profile)}
    bridge.bind(profile, "en", binding, True)
    return root, profile, binding


def successful_reply(profile):
    with practice.connect(profile / "StudyLibrary/study.db") as c:
        batch = dict(c.execute("SELECT * FROM PracticeBatches ORDER BY CreatedUtc DESC LIMIT 1").fetchone())
    return batch["BatchId"] + " " + " ".join(json.loads(batch["TermsJson"]) + json.loads(batch["ReviewJson"]))


def test_missing_config_is_disabled(tmp_path):
    assert bridge.run_due(tmp_path)["status"] == "disabled"


def test_cli_uses_stdin_explicit_session_and_no_permission_bypass(app):
    root, profile, binding = app
    seen = []
    def runner(args, **kwargs):
        seen.append((args, kwargs))
        assert kwargs["shell"] is False
        assert args[-1] == "-" and SESSION in args
        assert "--last" not in args and not any("dangerously" in a for a in args)
        output = "\n".join(json.dumps(x) for x in [{"type":"thread.started","thread_id":SESSION},{"type":"item.completed","item":{"type":"agent_message","text":successful_reply(profile)}},{"type":"turn.completed"}])
        return subprocess.CompletedProcess(args, 0, output, "")
    assert bridge.run_due(root, True, runner)["results"][0]["status"] == "cli_completed"
    assert bridge.run_due(root, True, runner)["results"][0]["status"] == "not_due"
    assert len(seen) == 1


def test_default_run_only_exports_and_does_not_ack(app):
    root, profile, binding = app
    result = bridge.run_due(root)
    assert result["results"][0]["status"] == "exported_only"
    assert practice.status(profile / "StudyLibrary/study.db")["batches"][0]["Status"] == "prepared"


def test_manual_provider_never_calls_cli_even_when_send_requested(app):
    root, profile, _ = app
    bridge.bind(profile, "en", {"Provider":"chatgpt_manual","SessionId":""}, True)
    def forbidden(*args, **kwargs): raise AssertionError("manual mode invoked CLI")
    assert bridge.run_due(root, True, forbidden)["results"][0]["status"] == "exported_only"


def test_claude_arguments_disable_builtin_and_mcp_tools(app):
    root, profile, binding = app
    binding["Provider"] = "claude_code"
    args = bridge.cli_arguments(binding, "claude.exe", profile / "unused.txt")
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--disallowedTools") + 1] == "mcp__*"
    assert args[args.index("--resume") + 1] == SESSION
    assert "--dangerously-skip-permissions" not in args


@pytest.mark.parametrize("provider,output", [("claude_code",'{"is_error":true,"subtype":"error"}'),("codex_cli",'{"type":"turn.failed"}')])
def test_failed_provider_response_is_not_success(provider, output):
    with pytest.raises(ValueError): bridge.parse_cli_result(provider, output)


def test_wrong_session_and_failed_attempt_are_not_automatically_retried(app):
    root, profile, binding = app
    def runner(args, **kwargs):
        data = "\n".join(json.dumps(e) for e in [{"type":"thread.started","thread_id":OTHER},{"type":"item.completed","item":{"type":"agent_message","text":successful_reply(profile)}},{"type":"turn.completed"}])
        return subprocess.CompletedProcess(args, 0, data, "")
    first = bridge.run_due(root, True, runner)
    assert first["results"][0]["status"] == "needs_attention"
    assert bridge.run_due(root, True, runner)["results"][0]["status"] == "needs_verification"


def test_global_disable_and_local_only_records_block_sender(app):
    root, profile, binding = app
    bridge.bind(profile, "en", binding, False)
    assert bridge.run_due(root, True)["status"] == "disabled"
    bridge.bind(profile, "en", binding, True)
    with sqlite3.connect(profile / "StudyLibrary/study.db") as c: c.execute("UPDATE StudyEntries SET CloudSyncAllowed=0")
    assert bridge.run_due(root, True)["results"][0]["status"] == "no_candidates"


def test_new_session_requires_explicit_opt_in(app):
    root, profile, binding = app
    binding["SessionId"] = ""
    with pytest.raises(ValueError): bridge.bind(profile, "en", binding, True)
    binding["AllowCreate"] = True
    bridge.bind(profile, "en", binding, True)
    def runner(args, **kwargs):
        assert "resume" not in args
        data = "\n".join(json.dumps(e) for e in [{"type":"thread.started","thread_id":SESSION},{"type":"item.completed","item":{"type":"agent_message","text":successful_reply(profile)}},{"type":"turn.completed"}])
        return subprocess.CompletedProcess(args, 0, data, "")
    assert bridge.run_due(root, True, runner)["results"][0]["status"] == "cli_completed"
    assert bridge.load_config(profile)["Bindings"]["en"]["SessionId"] == SESSION


def test_claim_prevents_double_dispatch(app):
    root, profile, _ = app
    batch = bridge.run_due(root)["results"][0]["batch_id"]
    db = profile / "StudyLibrary/study.db"
    assert bridge.claim(db, batch)
    assert not bridge.claim(db, batch)


def test_session_argument_cannot_be_a_command(app):
    _, profile, binding = app
    binding["SessionId"] = '--last & echo unsafe'
    with pytest.raises(ValueError): bridge.bind(profile, "en", binding, True)


@pytest.mark.parametrize("change", ["disable", "rebind", "revoke"])
def test_claim_rechecks_live_permission(app, change):
    root, profile, binding = app
    batch = bridge.run_due(root)["results"][0]["batch_id"]
    db = profile / "StudyLibrary/study.db"
    if change == "disable": bridge.bind(profile, "en", binding, False)
    elif change == "rebind": bridge.bind(profile, "en", binding | {"SessionId":OTHER}, True)
    else:
        with sqlite3.connect(db) as c: c.execute("UPDATE StudyEntries SET CloudSyncAllowed=0")
    assert not bridge.claim(db, batch)


def test_automatic_selection_excludes_unreviewed_project_words():
    assert bridge.choose_selection([{"term":"orchidfalcon","priority":"review_required"}], "en") is None


def test_cancelled_batch_cannot_be_acknowledged_or_recreated_today(app):
    root, profile, _ = app
    db = profile / "StudyLibrary/study.db"
    batch = bridge.run_due(root)["results"][0]["batch_id"]
    evidence = successful_reply(profile)
    bridge.finish(db, batch, "cancelled", "user cancelled")
    with pytest.raises(ValueError): practice.ack(db, batch, evidence)
    assert bridge.run_due(root)["results"][0]["status"] == "cancelled"


def test_running_dispatch_cannot_be_cancelled(app):
    root, profile, _ = app
    db = profile / "StudyLibrary/study.db"
    batch = bridge.run_due(root)["results"][0]["batch_id"]
    assert bridge.claim(db, batch)
    with pytest.raises(ValueError): bridge.finish(db, batch, "cancelled", "stop")
    bridge.finish(db, batch, "needs_attention", "ambiguous provider failure")
    assert bridge.run_due(root, True)["results"][0]["status"] == "needs_verification"


def test_cancel_racing_with_dispatch_preserves_inflight_state(app):
    root, profile, _ = app
    db = profile / "StudyLibrary/study.db"
    batch = bridge.run_due(root)["results"][0]["batch_id"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        with sqlite3.connect(db) as sender:
            sender.execute("BEGIN IMMEDIATE")
            sender.execute("UPDATE PracticeBatches SET Status='dispatching' WHERE BatchId=?", (batch,))
            cancellation = pool.submit(bridge.finish, db, batch, "cancelled", "race")
            time.sleep(0.15)
            sender.commit()
        with pytest.raises(ValueError): cancellation.result(timeout=5)
    assert practice.status(db)["batches"][0]["Status"] == "dispatching"
