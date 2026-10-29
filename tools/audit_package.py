"""核对公开包的空白配置、依赖版本及来源文件一致性，不读取私人学习库。"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def audit(root: Path, archive: Path) -> dict:
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None, "ZIP CRC failed"
        names = z.namelist()
        assert not any(n.lower().endswith((".db", ".db-wal", ".db-shm", ".pdb", ".readback.json", ".pyc")) for n in names)
        assert not any("WeChat" in n for n in names)
        for name in ["LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"]:
            assert z.read(name) == (root / name).read_bytes(), name
        for name in ["study_bridge.py", "study_practice.py", "study_privacy.py", "study_tasks.py"]:
            assert z.read("StudyTools/" + name) == (root / "tools" / name).read_bytes(), name
        for name in ["study-assistants.md", "study-intranet.md", "study-release.md"]:
            assert z.read("docs/" + name) == (root / "docs" / name).read_bytes(), name
        settings = json.loads(z.read("PortableConfig/Settings/Settings.json"))
        assert settings["StudyLibraryCloudSyncEnabled"] is False
        assert settings["EnableExternalCall"] is False and settings["AutoCheckUpdate"] is False
        services = json.loads(z.read("PortableConfig/Settings/ServiceSettings.json"))
        assert not any(s["IsEnabled"] for s in services["TranSvcDatas"])
        for name in names:
            if name.startswith("PortableConfig/") and name.endswith(".json"):
                data = json.loads(z.read(name))
                assert not data.get("ApiKey") and not data.get("SessionId"), name
        for asset in json.loads((root / "tools/dependencies.json").read_text()):
            if asset["name"].endswith(".traineddata"):
                data = z.read("Plugins/STranslate.Plugin.Ocr.Tesseract/tessdata/" + asset["name"])
                assert hashlib.sha256(data).hexdigest() == asset["sha256"]
        assert "licenses/iNKORE.UI.WPF-1.2.8-source.zip" in names
        assert "licenses/iNKORE-Modern.txt" in names
        assert "python/LICENSE.txt" in names
        assert any("microsoft.netcore.app.runtime" in n and n.endswith("THIRD-PARTY-NOTICES.TXT") for n in names)
    return {"status":"passed", "files":len(names), "sha256":hashlib.sha256(archive.read_bytes()).hexdigest(), "personal_database":False, "cloud_enabled":False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--zip", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.root, args.zip), indent=2))
