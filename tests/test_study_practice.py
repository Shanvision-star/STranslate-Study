"""验证隐私清理、词汇最小外发、隔日节流和远端回读边界。"""

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import study_practice as practice
import study_privacy as privacy

ROUTES = {"en": {"thread_id": "english-thread"}, "es": {"thread_id": "spanish-thread"}}
SELECTION = {"language": "en", "terms": ["mechanism", "segmentation", "regardless of"], "grammar_focus": "concession"}
START = datetime(2026, 10, 30, 9).astimezone()


@pytest.fixture
def database(tmp_path):
    p = tmp_path / "profile/StudyLibrary/study.db"
    p.parent.mkdir(parents=True)
    settings = p.parent.parent / "Settings"
    settings.mkdir()
    (settings / "Settings.json").write_text('{"StudyLibraryCloudSyncEnabled":true}')
    (settings / "StudyPrivacy.json").write_text(json.dumps({"BlockedFingerprints":[privacy.fingerprint("Example Organization"),privacy.fingerprint("示例机构")]}),encoding="utf-8")
    with sqlite3.connect(p) as c:
        c.executescript("""
        CREATE TABLE StudyEntries(EntryKey TEXT PRIMARY KEY, Language TEXT, Original TEXT, Translation TEXT,
          SourcesJson TEXT, CloudSyncAllowed INTEGER, Revision INTEGER, SyncedRevision INTEGER);
        CREATE TABLE StudyEvents(EventId TEXT,EntryKey TEXT,CreatedUtc TEXT);
        CREATE TABLE SyncBatches(BatchId TEXT,Status TEXT,Payload TEXT,RemoteEvidence TEXT);
        """)
        c.execute("INSERT INTO StudyEntries VALUES(?,?,?,?,?,?,?,?)", ("general", "en", "An ineffective mechanism for market segmentation works regardless of context.", "普通学习内容", json.dumps([{"Title":"示例机构 - Chrome", "Url":"https://example-organization.test/account?id=2", "Application":"chrome"}]), 1, 1, 0))
        c.execute("INSERT INTO StudyEntries VALUES(?,?,?,?,?,?,?,?)", ("private", "en", "Example-Organization confidential proposal", "机构内容", "[]", 1, 1, 0))
        c.execute("INSERT INTO SyncBatches VALUES('legacy','prepared',?,?)", ("示例机构", "private-title"))
    return p


def test_privacy_migration_preserves_general_words_and_removes_restricted_body(database):
    r = privacy.clean_database(database, True)
    assert r["entries_removed"] == 1 and r["entries_sanitized"] == 1
    with sqlite3.connect(database) as c:
        row = c.execute("SELECT Original,SourcesJson FROM StudyEntries").fetchone()
        assert "mechanism" in row[0] and not privacy.restricted(row[1], privacy.load_rules(database))
        assert json.loads(row[1])[0]["Url"] is None
        assert c.execute("SELECT Status FROM SyncBatches").fetchone()[0] == "blocked_privacy"


@pytest.mark.parametrize("text", ["示 例 机 构", "EXAMPLE_organization", "%E7%A4%BA%E4%BE%8B%E6%9C%BA%E6%9E%84", "ＥｘａｍｐｌｅＯｒｇａｎｉｚａｔｉｏｎ"])
def test_restricted_aliases(text):
    assert privacy.restricted(text, [privacy.fingerprint("Example Organization"),privacy.fingerprint("示例机构")])


def test_redacts_contacts_and_local_or_internal_links():
    assert "person@" not in privacy.redact("person@example.org 13812345678 token=abcdefghijklmno")
    assert "13812345678" not in privacy.redact("13812345678")
    for link in ["file:///C:/private.pdf", "http://192.168.1.2/a", "http://corp.example/a", "https://user:pass@example.org/a"]:
        assert privacy.public_url(link) is None
    assert privacy.public_url("https://www.w3.org/article?tracking=private#user") == "https://www.w3.org/article"


def test_candidates_and_payload_never_include_source_or_original(database):
    candidates = practice.candidates(database, "en")
    assert not privacy.restricted(json.dumps(candidates), privacy.load_rules(database))
    result = practice.prepare(database, ROUTES, SELECTION, START)
    payload = result["Payload"]
    assert result["Destination"] == "english-thread"
    assert "An ineffective mechanism" not in payload and "https://" not in payload
    assert "Original" not in payload and "SourcesJson" not in payload
    assert all(term in payload for term in SELECTION["terms"])


def test_company_only_content_and_revoked_terms_cannot_be_sent(database):
    with sqlite3.connect(database) as c:
        c.execute("UPDATE StudyEntries SET CloudSyncAllowed=0 WHERE EntryKey='general'")
    assert practice.candidates(database, "en")["candidates"] == []
    with pytest.raises(ValueError):
        practice.prepare(database, ROUTES, SELECTION, START)


def test_no_duplicate_and_every_second_day_gate(database):
    first = practice.prepare(database, ROUTES, SELECTION, START)
    assert practice.prepare(database, ROUTES, SELECTION, START)["BatchId"] == first["BatchId"]
    practice.mark_sent(database, first["BatchId"])
    assert practice.prepare(database, ROUTES, SELECTION, START)["Status"] == "sent_unverified"
    practice.ack(database, first["BatchId"], "Remote message read back: " + first["Payload"], at=START)
    assert practice.prepare(database, ROUTES, SELECTION, START + timedelta(days=1))["status"] == "not_due"
    second = practice.prepare(database, ROUTES, SELECTION, START + timedelta(days=2))
    assert second["BatchId"] != first["BatchId"]


def test_global_disable_and_inflight_revocation(database):
    batch = practice.prepare(database, ROUTES, SELECTION, START)
    settings = database.parent.parent / "Settings/Settings.json"
    settings.parent.mkdir(exist_ok=True)
    settings.write_text('{"StudyLibraryCloudSyncEnabled":false}')
    assert practice.prepare(database, ROUTES, SELECTION, START)["status"] == "cloud_sync_disabled"
    settings.write_text('{"StudyLibraryCloudSyncEnabled":true}')
    with sqlite3.connect(database) as c:
        c.execute("UPDATE StudyEntries SET CloudSyncAllowed=0")
    with pytest.raises(ValueError):
        practice.prepare(database, ROUTES, SELECTION, START)


def test_ack_requires_all_words_and_does_not_mark_learning_mastered(database):
    batch = practice.prepare(database, ROUTES, SELECTION, START)
    with pytest.raises(ValueError):
        practice.ack(database, batch["BatchId"], "tool accepted " + batch["BatchId"])
    evidence = "Remote readback: " + batch["Payload"]
    practice.ack(database, batch["BatchId"], evidence, at=START)
    practice.ack(database, batch["BatchId"], evidence, at=START)
    with sqlite3.connect(database) as c:
        assert c.execute("SELECT SyncedRevision FROM StudyEntries WHERE EntryKey='general'").fetchone()[0] == 0


def test_only_safe_candidate_terms_and_fixed_grammar_accepted(database):
    for changed in [{"terms": ["https://private.example"]}, {"terms": ["ExampleOrganization"]}, {"grammar_focus": "secret arbitrary text"}]:
        with pytest.raises(ValueError):
            practice.prepare(database, ROUTES, SELECTION | changed, START)



def test_spanish_route_and_unknown_language(database):
    with sqlite3.connect(database) as c:
        c.execute("INSERT INTO StudyEntries VALUES('spanish','es','Podemos desarrollar y mejorar las ideas.','学习内容','[]',1,1,0)")
    result = practice.prepare(database, ROUTES, {"language":"es", "terms":["desarrollar", "mejorar"], "grammar_focus":"cause_effect"}, START)
    assert result["Destination"] == "spanish-thread"
    with pytest.raises(ValueError):
        practice.candidates(database, "und")
