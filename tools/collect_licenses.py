"""从本次发布项目的 NuGet 还原清单收集依赖声明和包内版权文本。"""
import argparse
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path


def collect(root: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    packages = {}
    projects = ["STranslate", "STranslate.Plugin.Translate.MicrosoftBuiltIn", "STranslate.Plugin.Translate.OpenAI", "STranslate.Plugin.Ocr.Tesseract"]
    for project in projects:
        data = json.loads((root / "src/.artifacts/obj" / project / "project.assets.json").read_text(encoding="utf-8-sig"))
        for identity, library in data["libraries"].items():
            if library["type"] != "package": continue
            for folder in data["packageFolders"]:
                directory = Path(folder) / library["path"]
                if directory.is_dir(): packages[identity] = directory; break
    # 自包含运行时由 SDK 下载，不一定出现在 libraries 列表中。
    for folder in data["packageFolders"]:
        for name in ("microsoft.netcore.app.runtime.win-x64", "microsoft.windowsdesktop.app.runtime.win-x64"):
            directory = Path(folder) / name / "10.0.14"
            if directory.is_dir(): packages[name + "/10.0.14"] = directory
    rows = ["# NuGet dependency notices", "", "Generated from the four release projects; build-time dependencies are included conservatively.", "", "| Package | License / authors / copyright | Project |", "| --- | --- | --- |"]
    manifest = []
    for identity, directory in sorted(packages.items()):
        metadata = ET.parse(next(directory.glob("*.nuspec"))).getroot()
        def field(name):
            node = metadata.find(".//{*}" + name)
            return node.text if node is not None and node.text else ""
        license_node = metadata.find(".//{*}license")
        license_value = field("license") or field("licenseUrl")
        license_kind = license_node.attrib.get("type") if license_node is not None else "url"
        target = output / identity.replace("/", "-")
        target.mkdir(exist_ok=True)
        # 保留原 nuspec，包含作者、版权、许可证标识和来源；不保存本机缓存路径。
        shutil.copyfile(next(directory.glob("*.nuspec")), target / "package.nuspec")
        copied = []
        for source in directory.rglob("*"):
            if source.is_file() and (re.search(r"license|licence|notice|copying|copyright", source.name, re.I) or (license_kind == "file" and source == directory / license_value)):
                relative = source.relative_to(directory)
                dest = target / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest); copied.append(str(relative).replace("\\", "/"))
        details = " · ".join(filter(None, [license_value, field("authors"), field("copyright")])).replace("|", "\\|").replace("\n", " ")
        rows.append(f"| {identity} | {details} | {field('projectUrl')} |")
        manifest.append({"package":identity,"license":license_value,"kind":license_kind,"authors":field("authors"),"copyright":field("copyright"),"project":field("projectUrl"),"license_files":copied})
    (output / "DEPENDENCIES.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Dependency metadata and embedded notices: {len(manifest)} packages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collect(args.root, args.output)
