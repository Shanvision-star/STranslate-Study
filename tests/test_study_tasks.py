"""验证任务路径转义与执行边界，不向系统注册真实定时任务。"""
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import study_tasks as tasks

def test_task_uses_current_user_and_quoted_paths(tmp_path):
    app = tmp_path / "study & learn"
    text = tasks.task_xml(app, "S-1-5-21-123", datetime(2026, 10, 30, 9))
    root = ET.fromstring(text)
    n = {"t":tasks.NAMESPACE}
    assert root.find(".//t:RunLevel", n).text == "LeastPrivilege"
    assert root.find(".//t:LogonType", n).text == "InteractiveToken"
    assert root.find(".//t:Command", n).text == str(app / "python/pythonw.exe")
    assert '"' in root.find(".//t:Arguments", n).text
    assert root.find(".//t:DaysInterval", n).text == "1"
    assert root.find(".//t:MultipleInstancesPolicy", n).text == "IgnoreNew"
    assert "password" not in text.lower()
