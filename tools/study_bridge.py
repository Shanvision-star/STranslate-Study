"""学习助手引导与派发：用户自行绑定会话，仅发送本机筛选后的词汇。"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import study_practice as practice
import study_privacy as privacy
import study_tasks

PROVIDERS = ("codex_cli", "claude_code", "codex_desktop", "chatgpt_manual")


def profile_for(app_dir: Path) -> Path:
    portable = app_dir / "PortableConfig"
    if portable.exists() or not (app_dir / "STranslate.exe").exists(): return portable
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "STranslate-Study"


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def load_config(profile: Path) -> dict:
    path = profile / "Settings/StudyAssistant.json"
    if not path.exists(): return {"SchemaVersion": 1, "Enabled": False, "Bindings": {}}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("SchemaVersion") != 1 or not isinstance(data.get("Bindings"), dict):
        raise ValueError("学习助手配置格式错误，请重新运行设置")
    return data


def validate_binding(binding: dict) -> None:
    if binding.get("Provider") not in PROVIDERS: raise ValueError("不支持的学习助手")
    session = binding.get("SessionId", "")
    if session:
        try: uuid.UUID(session)
        except (ValueError, TypeError): raise ValueError("会话 ID 必须是明确的 UUID，不支持自动选择最近会话")
    if binding["Provider"] == "codex_desktop" and not session:
        raise ValueError("桌面端绑定需要先由客户端工具确认目标对话 ID")
    if binding["Provider"] in ("codex_cli", "claude_code") and not session and binding.get("AllowCreate") is not True:
        raise ValueError("请选择已有会话，或明确允许创建专用学习会话")
    workdir = binding.get("WorkDir")
    if workdir and not Path(workdir).is_dir(): raise ValueError("会话工作目录不存在")


def bind(profile: Path, language: str, binding: dict, enable: bool) -> dict:
    if language not in ("en", "es"): raise ValueError("仅支持英语和西语")
    validate_binding(binding)
    config = load_config(profile)
    config["Bindings"][language] = binding
    config["Enabled"] = bool(enable)
    atomic_json(profile / "Settings/StudyAssistant.json", config)
    settings_path = profile / "Settings/Settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8-sig")) if settings_path.exists() else {}
    settings["StudyLibraryCloudSyncEnabled"] = bool(enable)
    settings["EnableExternalCall"] = False
    atomic_json(settings_path, settings)
    return config


def destination(binding: dict, language: str) -> str:
    return binding.get("SessionId") or binding["Provider"] + ":new:" + language


def executable(binding: dict) -> str:
    name = binding.get("Executable") or ("codex" if binding["Provider"] == "codex_cli" else "claude")
    resolved = str(Path(name).resolve()) if Path(name).is_file() else shutil.which(name)
    if not resolved: raise FileNotFoundError("未找到 CLI，请先安装并正常登录，再重新绑定")
    return resolved


def cli_arguments(binding: dict, executable_path: str, reply_file: Path) -> list[str]:
    validate_binding(binding)
    session = binding.get("SessionId", "")
    if binding["Provider"] == "codex_cli":
        args = [executable_path, "exec", "--sandbox", "read-only"]
        if session: args.append("resume")
        args += ["--skip-git-repo-check", "--json"]
        if session: args.append(session)
        return args + ["-"]
    if binding["Provider"] == "claude_code":
        args = [executable_path, "-p", "--output-format", "json", "--tools", "", "--disallowedTools", "mcp__*"]
        if session: args += ["--resume", session]
        return args
    raise ValueError("此模式不能通过 CLI 派发")


def parse_cli_result(provider: str, stdout: str, reply: str = "") -> tuple[str, str]:
    if provider == "claude_code":
        result = json.loads(stdout)
        if result.get("is_error") or result.get("subtype") != "success": raise ValueError("Claude Code 未成功完成本轮")
        return result.get("session_id", ""), result.get("result", "")
    events = []
    for line in stdout.splitlines():
        try: events.append(json.loads(line))
        except json.JSONDecodeError: continue
    if not any(e.get("type") == "turn.completed" for e in events) or any(e.get("type") == "turn.failed" for e in events):
        raise ValueError("Codex 未返回已完成回合")
    session = next((e.get("thread_id", "") for e in events if e.get("type") == "thread.started"), "")
    if not reply:
        reply = "\n".join(e.get("item", {}).get("text", "") for e in events if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message")
    return session, reply


def claim(database: Path, batch_id: str) -> bool:
    profile = database.parent.parent
    config = load_config(profile)
    if not config.get("Enabled") or not practice.enabled(database): return False
    with practice.connect(database) as c:
        row = c.execute("SELECT * FROM PracticeBatches WHERE BatchId=?", (batch_id,)).fetchone()
        if not row or row["Status"] != "prepared": return False
        language = row["Language"]
        binding = config["Bindings"].get(language)
        if not binding or destination(binding, language) != row["Destination"]: return False
        validate_binding(binding)
        allowed = {r["term"] for r in practice.candidates(database, language)["candidates"] if r["priority"] == "general_use"}
        if any(t not in allowed for t in json.loads(row["TermsJson"]) + json.loads(row["ReviewJson"])): return False
        result = c.execute("UPDATE PracticeBatches SET Status='dispatching' WHERE BatchId=? AND Status='prepared'", (batch_id,))
        return result.rowcount == 1


def finish(database: Path, batch_id: str, status: str, evidence: str) -> None:
    if status not in ("cli_completed", "manual_confirmed", "cancelled", "needs_attention"):
        raise ValueError("不允许的完成状态")
    with practice.connect(database) as c:
        # 取消和派发抢占共用数据库写锁，防止检查后被另一进程改成 dispatching。
        c.execute("BEGIN IMMEDIATE")
        old = c.execute("SELECT Status FROM PracticeBatches WHERE BatchId=?", (batch_id,)).fetchone()
        if not old: raise ValueError("批次不存在")
        if status == "cancelled" and old["Status"] not in ("prepared", "cancelled"):
            raise ValueError("批次已开始或可能已发送，只能核对回执；不能用取消触发重发")
        if old["Status"] in practice.DELIVERED_STATES or old["Status"] == "cancelled":
            if old["Status"] == status: return
            raise ValueError("已有确认或已取消的批次不可改写；取消不能撤回已发送消息")
        c.execute("UPDATE PracticeBatches SET Status=?,VerifiedUtc=?,RemoteEvidence=? WHERE BatchId=?", (status, datetime.now(timezone.utc).isoformat(), evidence, batch_id))


def execute_cli(profile: Path, language: str, binding: dict, batch: dict, runner=subprocess.run) -> dict:
    database = profile / "StudyLibrary/study.db"
    command = executable(binding)
    replies = profile / "StudyLibrary/AssistantReplies"
    replies.mkdir(parents=True, exist_ok=True)
    reply_file = replies / (batch["BatchId"] + "-" + uuid.uuid4().hex[:8] + ".txt")
    args = cli_arguments(binding, command, reply_file)
    current = load_config(profile)
    allowed = {c["term"] for c in practice.candidates(database, language)["candidates"]}
    if not current.get("Enabled") or not practice.enabled(database) or current["Bindings"].get(language) != binding:
        return {"status":"permission_changed"}
    if any(t not in allowed for t in json.loads(batch["TermsJson"]) + json.loads(batch["ReviewJson"])):
        return {"status":"candidate_permission_revoked"}
    if not claim(database, batch["BatchId"]): return {"status": "already_claimed"}
    try:
        completed = runner(args, input=batch["Payload"], text=True, encoding="utf-8", errors="replace", capture_output=True,
                           cwd=binding.get("WorkDir") or str(profile), timeout=180, shell=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if completed.returncode != 0: raise RuntimeError("CLI 返回错误，请在自己的终端检查登录、模型及权限")
        session, reply = parse_cli_result(binding["Provider"], completed.stdout)
        uuid.UUID(session)
        if binding.get("SessionId") and session != binding["SessionId"]:
            raise ValueError("返回会话与绑定不一致，停止确认，不能改投其他会话")
        if not binding.get("SessionId"):
            config = load_config(profile)
            config["Bindings"][language]["SessionId"] = session
            config["Bindings"][language]["AllowCreate"] = False
            atomic_json(profile / "Settings/StudyAssistant.json", config)
        if privacy.restricted(reply, privacy.load_rules(database)):
            raise ValueError("回复包含隐私规则标识，已停止保存，请在自己的会话中核对")
        reply = privacy.redact(reply)
        reply_file.write_text(reply, encoding="utf-8")
        terms = json.loads(batch["TermsJson"]) + json.loads(batch["ReviewJson"])
        if batch["BatchId"] not in reply or not all(t.casefold() in reply.casefold() for t in terms):
            raise ValueError("CLI 已结束但回执缺少批次或词汇，请核对会话；不会自动重发")
        evidence = json.dumps({"provider": binding["Provider"], "session_id": session, "reply": reply}, ensure_ascii=False)
        finish(database, batch["BatchId"], "cli_completed", evidence)
        return {"status": "cli_completed", "session_id": session, "reply_file": str(reply_file)}
    except Exception as exc:
        finish(database, batch["BatchId"], "needs_attention", type(exc).__name__ + ": " + privacy.redact(str(exc)))
        return {"status": "needs_attention", "message": str(exc)}


def choose_selection(candidates: list[dict], language: str) -> dict | None:
    # 未审阅的小写专有词可能来自公司项目；自动发送只用明确的通用词表。
    candidates = [c for c in candidates if c.get("priority") == "general_use"]
    fresh = [c["term"] for c in candidates if c.get("introduced_utc") is None]
    review = [c["term"] for c in candidates if c.get("introduced_utc") is not None][:2]
    terms = fresh[:3 if review else 5]
    if not terms and not review: return None
    grammar = "concession" if "regardless of" in terms + review else "relative_clauses"
    return {"language": language, "terms": terms, "review_terms": review, "grammar_focus": grammar}


@contextmanager
def dispatch_lock(profile: Path):
    folder = profile / "StudyLibrary"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "dispatch.lock").open("a+b") as lock:
        if lock.tell() == 0: lock.write(b"0"); lock.flush()
        lock.seek(0)
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            pass
        try: yield acquired
        finally:
            if acquired:
                lock.seek(0)
                if os.name == "nt": msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else: fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def run_due(app_dir: Path, send: bool = False, runner=subprocess.run) -> dict:
    with dispatch_lock(profile_for(app_dir)) as acquired:
        if not acquired: return {"status":"already_running"}
        return _run_due(app_dir, send, runner)


def _run_due(app_dir: Path, send: bool = False, runner=subprocess.run) -> dict:
    profile = profile_for(app_dir)
    config = load_config(profile)
    database = profile / "StudyLibrary/study.db"
    if not config.get("Enabled") or not practice.enabled(database): return {"status": "disabled"}
    if not database.exists(): return {"status": "waiting_for_first_capture"}
    outcomes = []
    for language, binding in config["Bindings"].items():
        validate_binding(binding)
        if binding["Provider"] == "codex_desktop":
            outcomes.append({"language": language, "status": "desktop_agent_required"}); continue
        available = practice.candidates(database, language)["candidates"]
        selection = choose_selection(available, language)
        if selection is None:
            outcomes.append({"language": language, "status": "no_candidates"}); continue
        batch = practice.prepare(database, {language: {"thread_id": destination(binding, language)}}, selection)
        if "BatchId" not in batch:
            outcomes.append({"language": language, **batch}); continue
        if batch["Status"] not in ("prepared",):
            outcomes.append({"language": language, "status": "needs_verification", "batch_id": batch["BatchId"]}); continue
        outbox = profile / "StudyLibrary/Outbox" / (batch["BatchId"] + ".md")
        outbox.parent.mkdir(parents=True, exist_ok=True)
        outbox.write_text(batch["Payload"], encoding="utf-8")
        if binding["Provider"] == "chatgpt_manual" or not send:
            outcomes.append({"language": language, "status": "exported_only", "batch_id": batch["BatchId"], "path": str(outbox)}); continue
        outcomes.append({"language": language, "batch_id": batch["BatchId"], **execute_cli(profile, language, binding, batch, runner)})
    return {"status": "checked", "results": outcomes}


def doctor(app_dir: Path) -> dict:
    profile = profile_for(app_dir)
    config = load_config(profile)
    result = {"profile": str(profile), "configured": bool(config["Bindings"]), "enabled": config["Enabled"], "cli": {}}
    for name in ("codex", "claude"):
        result["cli"][name] = {"installed": shutil.which(name) is not None, "authentication_verified": False}
    database = profile / "StudyLibrary/study.db"
    result["practice"] = practice.status(database) if database.exists() else {"status": "waiting_for_first_capture"}
    return result


def desktop_prompt(app_dir: Path) -> str:
    profile = profile_for(app_dir)
    return f"""请帮我绑定 STranslate Study 的私密词汇练习。应用目录：{app_dir}；数据目录：{profile}。
我希望每两天使用英语/西语词汇做一问一答练习。先检查你是否有 list_threads、send_message_to_thread、read_thread、automation_update 这些客户端工具；没有时说明限制，改用手动导出，不调用 ChatGPT 私有接口、不读取浏览器凭据。
有这些工具时先列出我的学习对话，让我确认目标，再通过 tools/study_bridge.py bind（发布包目录名为 StudyTools）保存我选择的 SessionId，Provider 为 codex_desktop。不要使用别人的示例 ID。需要我授权后才启用发送和计划。
学习数据只用 study_practice.py candidates 提供的不带来源的候选。筛选 3—5 个实用词与最多 2 个旧词，写 selection JSON 后运行 prepare。先调用 study_bridge.py claim --batch，成功后才发送 Payload。用 read_thread 回读批次和全部词汇，再调用 study_practice.py ack；结果不确定不重发。只在我确认的对话中练习，不公开数据，不改其他任务。
在此客户端创建每天 09:00 检查的自动化，遵守 study_practice.py status 的 next_due，非到期日保持安静，实际每两天发送一次。教学一次只问一个问题，等待我的回答再纠错。检查任务真实保存的配置再报告完成。"""


def setup(app_dir: Path) -> None:
    profile = profile_for(app_dir)
    print("STranslate Study 学习助手设置\n词库保存在本机；只会发送筛选后的词汇，不发送来源与原段落。")
    print("数据目录：", profile)
    print("1. Codex CLI  2. Claude Code CLI  3. Codex 桌面端绑定 ChatGPT 对话  4. ChatGPT 手动粘贴")
    choices = {"1":"codex_cli", "2":"claude_code", "3":"codex_desktop", "4":"chatgpt_manual"}
    provider = choices.get(input("选择助手 [4]：").strip() or "4")
    if not provider: raise ValueError("无效选择")
    if provider == "codex_desktop":
        prompt = profile / "StudyLibrary/bind-desktop.txt"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text(desktop_prompt(app_dir), encoding="utf-8")
        print("把这个文件的内容粘贴到 Codex 桌面端，按提示选择自己的学习对话：", prompt)
        if os.name == "nt": os.startfile(str(prompt))
        input("按回车关闭设置…")
        return
    language = input("学习语种 en / es [en]：").strip() or "en"
    workspace = app_dir / "AssistantWorkspace"
    workspace.mkdir(parents=True, exist_ok=True)
    binding = {"Provider": provider, "SessionId": "", "AllowCreate": False, "WorkDir": str(workspace)}
    profile.mkdir(parents=True, exist_ok=True)
    if provider in ("codex_cli", "claude_code"):
        print("请先安装并登录相应 CLI。调用会使用你自己的模型配置及账户额度。")
        binding["Executable"] = input("CLI 程序路径（留空自动查找）：").strip()
        binding["SessionId"] = input("专用学习会话 UUID（留空创建新会话）：").strip()
        binding["AllowCreate"] = not bool(binding["SessionId"])
        binding["WorkDir"] = input("会话工作目录（留空使用独立练习目录）：").strip() or str(workspace)
        executable(binding)
    blocked = input("需要过滤的机构或身份词，用逗号分隔（留空不新增）：").strip()
    if blocked:
        rules = privacy.load_rules(profile / "StudyLibrary/study.db")
        for term in blocked.replace("，", ",").split(","):
            if term.strip():
                rule = privacy.fingerprint(term.strip())
                if rule not in rules: rules.append(rule)
        atomic_json(profile / "Settings/StudyPrivacy.json", {"BlockedFingerprints":rules})
    enabled = input("允许按此设置使用脱敏词汇生成练习？ y/N：").strip().lower() == "y"
    bind(profile, language, binding, enabled)
    print("设置已保存。默认每两天练习，已有仅本地条目不会自动改成可发送。")
    if enabled and input("现在生成一轮？ y/N：").strip().lower() == "y":
        print(json.dumps(run_due(app_dir, send=provider != "chatgpt_manual"), ensure_ascii=False, indent=2))
    if enabled and input("创建每天 09:00 检查、每两天生成练习的 Windows 任务？ y/N：").strip().lower() == "y":
        print("任务已注册并回读：", study_tasks.install(app_dir, profile))
    print("手动模式只生成待粘贴文件，不会自动写入 ChatGPT。")
    input("按回车关闭设置…")


def main() -> None:
    p = argparse.ArgumentParser(description="用户自行绑定的私密学习助手")
    p.add_argument("command", choices=["setup", "doctor", "run-due", "bind", "claim", "confirm-manual", "cancel", "desktop-prompt", "install-task", "uninstall-task"])
    p.add_argument("--app-dir", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--send", action="store_true")
    p.add_argument("--language", choices=["en", "es"], default="en")
    p.add_argument("--provider", choices=PROVIDERS)
    p.add_argument("--session-id", default="")
    p.add_argument("--work-dir", default="")
    p.add_argument("--executable", default="")
    p.add_argument("--allow-create", action="store_true")
    p.add_argument("--enable", action="store_true")
    p.add_argument("--batch")
    p.add_argument("--confirm", action="store_true")
    a = p.parse_args()
    app_dir = a.app_dir.resolve()
    profile = profile_for(app_dir)
    if a.command == "setup": setup(app_dir); return
    if a.command == "doctor": result = doctor(app_dir)
    elif a.command in ("install-task", "uninstall-task"):
        if not a.confirm: p.error("任务变更需要 --confirm")
        result = {"task": study_tasks.install(app_dir, profile) if a.command == "install-task" else study_tasks.uninstall(app_dir), "operation": a.command}
    elif a.command == "run-due": result = run_due(app_dir, a.send)
    elif a.command == "desktop-prompt": result = {"prompt": desktop_prompt(app_dir)}
    elif a.command == "bind":
        if not a.provider: p.error("bind 需要 --provider")
        result = bind(profile, a.language, {"Provider":a.provider,"SessionId":a.session_id,"WorkDir":a.work_dir,"Executable":a.executable,"AllowCreate":a.allow_create}, a.enable)
    elif a.command == "claim":
        if not a.batch: p.error("claim 需要 --batch")
        result = {"claimed":claim(profile / "StudyLibrary/study.db", a.batch)}
    else:
        if not a.batch or not a.confirm: p.error("需要 --batch 和 --confirm；本机确认或取消不能撤回已经送出的消息")
        database = profile / "StudyLibrary/study.db"
        with practice.connect(database) as c:
            row = c.execute("SELECT * FROM PracticeBatches WHERE BatchId=?", (a.batch,)).fetchone()
        if not row: raise ValueError("批次不存在")
        status = "manual_confirmed" if a.command == "confirm-manual" else "cancelled"
        finish(database, a.batch, status, "用户明确确认；不是远端回读或学习掌握证明")
        result = {"status":status,"batch":a.batch}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try: main()
    except Exception as error:
        print("学习助手未完成：" + privacy.redact(str(error)), file=sys.stderr)
        raise SystemExit(1)
