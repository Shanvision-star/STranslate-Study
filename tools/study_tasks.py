"""使用 Windows 自带任务计划程序注册本应用任务，不修改脚本执行策略。"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"


def task_name(app_dir: Path) -> str:
    suffix = hashlib.sha256(str(app_dir.resolve()).casefold().encode()).hexdigest()[:12]
    return "STranslateStudy-" + suffix


def task_xml(app_dir: Path, user_sid: str, start: datetime | None = None) -> str:
    python = app_dir / "python/pythonw.exe"
    bridge = app_dir / "StudyTools/study_bridge.py"
    instant = start or datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    if start is None and instant <= datetime.now(): instant += timedelta(days=1)
    ET.register_namespace("", NAMESPACE)
    def element(parent, tag, text=None, **attributes):
        node = ET.SubElement(parent, "{"+NAMESPACE+"}"+tag, attributes)
        if text is not None: node.text = str(text)
        return node
    root = ET.Element("{"+NAMESPACE+"}Task", {"version":"1.2"})
    info = element(root, "RegistrationInfo")
    element(info, "Description", "STranslate Study: daily check, two-day private vocabulary practice; no full-text upload.")
    triggers = element(root, "Triggers")
    trigger = element(triggers, "CalendarTrigger")
    element(trigger, "StartBoundary", instant.isoformat(timespec="seconds"))
    element(trigger, "Enabled", "true")
    daily = element(trigger, "ScheduleByDay")
    element(daily, "DaysInterval", "1")
    principals = element(root, "Principals")
    principal = element(principals, "Principal", id="Author")
    element(principal, "UserId", user_sid)
    element(principal, "LogonType", "InteractiveToken")
    element(principal, "RunLevel", "LeastPrivilege")
    settings = element(root, "Settings")
    for key,value in {"MultipleInstancesPolicy":"IgnoreNew","DisallowStartIfOnBatteries":"false","StopIfGoingOnBatteries":"false","StartWhenAvailable":"true","ExecutionTimeLimit":"PT10M","Enabled":"true"}.items(): element(settings,key,value)
    actions = element(root, "Actions", Context="Author")
    action = element(actions, "Exec")
    element(action, "Command", str(python))
    element(action, "Arguments", subprocess.list2cmdline(["-X","utf8",str(bridge),"run-due","--send","--app-dir",str(app_dir)]))
    element(action, "WorkingDirectory", str(app_dir))
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def install(app_dir: Path, profile: Path, runner=subprocess.run) -> str:
    if os.name != "nt": raise RuntimeError("此任务安装入口仅支持 Windows")
    if not (app_dir / "python/pythonw.exe").is_file(): raise FileNotFoundError("请使用包含 Python 运行时的完整发布包")
    # SID 来自系统自身，不询问或保存账户密码。
    account = runner(["whoami.exe","/user","/fo","csv","/nh"],capture_output=True,check=True,text=True,errors="replace",shell=False)
    rows = list(csv.reader(io.StringIO(account.stdout)))
    sid = rows[0][1] if rows and len(rows[0]) > 1 else ""
    if not sid.startswith("S-1-"): raise ValueError("无法确认当前 Windows 用户")
    path = profile / "Cache/study-task.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(task_xml(app_dir, sid), encoding="utf-8")
    name = task_name(app_dir)
    result = runner(["schtasks.exe","/Create","/TN",name,"/XML",str(path),"/F"],capture_output=True,shell=False)
    if result.returncode != 0: raise RuntimeError("Windows 未接受任务注册，请通过任务计划程序检查权限；程序不会绕过公司策略")
    verified = runner(["schtasks.exe","/Query","/TN",name],capture_output=True,shell=False)
    if verified.returncode != 0: raise RuntimeError("未能回读任务，不能报告注册成功")
    return name


def uninstall(app_dir: Path, runner=subprocess.run) -> str:
    if os.name != "nt": raise RuntimeError("此任务管理入口仅支持 Windows")
    name = task_name(app_dir)
    result = runner(["schtasks.exe","/Delete","/TN",name,"/F"],capture_output=True,shell=False)
    if result.returncode != 0: raise RuntimeError("任务不存在或无权移除，请在任务计划程序检查")
    return name
