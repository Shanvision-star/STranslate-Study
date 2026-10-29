"""在本机脱敏学习数据，清理来源身份与旧同步载荷；不连接外部服务。"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit


def normalize_rule(value: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", unquote(value)).lower())


def fingerprint(term: str) -> dict:
    text = normalize_rule(term)
    if not 1 <= len(text) <= 128:
        raise ValueError("隐私词需包含 1—128 个有效字符")
    return {"Length": len(text), "Sha256": hashlib.sha256(text.encode()).hexdigest()}


def load_rules(database: Path) -> list[dict]:
    path = database.parent.parent / "Settings/StudyPrivacy.json"
    if not path.exists(): return []
    rules = json.loads(path.read_text(encoding="utf-8-sig")).get("BlockedFingerprints")
    if not isinstance(rules, list) or any(not isinstance(r, dict) or type(r.get("Length")) is not int or not 1 <= r["Length"] <= 128 or not re.fullmatch(r"[a-fA-F0-9]{64}", str(r.get("Sha256", ""))) for r in rules):
        raise ValueError("隐私规则格式错误，请重新运行学习助手设置")
    return rules


def restricted(value: str | None, rules: list[dict] | None = None) -> bool:
    compact = normalize_rule(value or "")
    for rule in rules or []:
        length = rule["Length"]
        if any(hashlib.sha256(compact[i:i+length].encode()).hexdigest() == rule["Sha256"].lower() for i in range(len(compact)-length+1)):
            return True
    return False


def redact(value: str | None) -> str:
    text = value or ""
    patterns = [r"https?://\S+", r"file:/+\S+", r"[A-Za-z]:\\[^\r\n]+", r"\\\\[^\s]+",
                r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)",
                r"(?i)\b(?:sk|ghp|gho|github_pat)[-_][A-Za-z0-9_-]{12,}\b",
                r"(?i)\b(?:api[_ -]?key|password|token|secret)\s*[:=]\s*\S+"]
    for pattern in patterns:
        text = re.sub(pattern, "[已脱敏]", text)
    return text


def public_url(value: str | None, rules: list[dict] | None = None) -> str | None:
    if not value or restricted(value, rules):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.scheme not in ("https", "http") or parts.username or parts.password or "." not in host:
            return None
        if any(x in host.lower().split(".") for x in ("corp", "internal", "intranet", "local", "lan", "localhost")):
            return None
        try:
            ipaddress.ip_address(host)
            return None
        except ValueError:
            pass
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except ValueError:
        return None


def clean_sources(raw: str, rules: list[dict] | None = None) -> str:
    sources = json.loads(raw or "[]")
    clean = []
    for source in sources:
        kind = source.get("Kind", "selection")
        if kind not in ("selection", "screenshot", "screenshot_import", "clipboard", "manual"):
            kind = "selection"
        url = public_url(source.get("Url"), rules)
        if restricted(source.get("Title"), rules):
            url = None
        app = source.get("Application", "")
        clean.append({"Kind": kind, "Title": "阅读来源（标题已脱敏）", "Application": app if app in ("chrome", "msedge", "firefox", "AcroRd32", "Acrobat") else "desktop", "Url": url})
    return json.dumps(clean, ensure_ascii=False)


def clean_database(path: Path, apply: bool = False) -> dict:
    rules = load_rules(path)
    report = {"entries_scanned": 0, "entries_removed": 0, "entries_sanitized": 0, "legacy_batches_scrubbed": 0, "applied": apply}
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA secure_delete=ON")
        for row in connection.execute("SELECT * FROM StudyEntries").fetchall():
            report["entries_scanned"] += 1
            if restricted(row["Original"], rules) or restricted(row["Translation"], rules):
                report["entries_removed"] += 1
                if apply:
                    connection.execute("DELETE FROM StudyEntries WHERE EntryKey=?", (row["EntryKey"],))
                    connection.execute("DELETE FROM StudyEvents WHERE EntryKey=?", (row["EntryKey"],))
                continue
            values = (redact(row["Original"]), redact(row["Translation"]), clean_sources(row["SourcesJson"], rules))
            if values != (row["Original"], row["Translation"], row["SourcesJson"]):
                report["entries_sanitized"] += 1
                if apply:
                    connection.execute("UPDATE StudyEntries SET Original=?,Translation=?,SourcesJson=? WHERE EntryKey=?", (*values, row["EntryKey"]))
            if apply and "Engine" in row.keys() and restricted(row["Engine"], rules):
                connection.execute("UPDATE StudyEntries SET Engine='翻译服务' WHERE EntryKey=?", (row["EntryKey"],))
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "SyncBatches" in tables:
            report["legacy_batches_scrubbed"] = connection.execute("SELECT COUNT(*) FROM SyncBatches").fetchone()[0]
            if apply:
                connection.execute("UPDATE SyncBatches SET Payload='[旧原文同步已停用，载荷已清除]',RemoteEvidence='[旧来源信息已清除]',Status=CASE WHEN Status='verified' THEN 'verified' ELSE 'blocked_privacy' END")
        connection.commit()
        if apply:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.execute("VACUUM")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="仅处理明确指定的本机学习库")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(clean_database(args.db, args.apply), ensure_ascii=False, indent=2))
