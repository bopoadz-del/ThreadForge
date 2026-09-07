#!/usr/bin/env python3
"""One-shot fetch of public DEXPI/Proteus assets into fixtures/public/dexpi13/.

Runtime ThreadForge never calls this. Checksums recorded in SOURCES.md / fetch_manifest.json.
Network is required only for this script (not for tests once vendored).
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "fixtures" / "public" / "dexpi13"
UA = {"User-Agent": "ThreadForge-fetch/1.0"}

# Pinned expected digests (fail loudly on mismatch).
EXPECTED_SHA256 = {
    "ProteusPIDSchema_4.1.xsd": "f14652c0f3ff79eea6bb1c92f276c79f41ebad2945324f70b348c377c00385ff",
    "C01V04-VER.EX01.xml": "a2b172f04e0dcf9a668e158c6dee3b5fd0dd4e9027b572dc39e54470562b809c",
}

SOURCES = [
    {
        "name": "ProteusPIDSchema_4.1.xsd",
        "rel": "xsd/ProteusPIDSchema_4.1.xsd",
        "url": "https://raw.githubusercontent.com/ProteusXML/proteusxml/master/ProteusPIDSchema%204.1.xsd",
    },
    {
        "name": "ProteusPIDSchema_4.1.1_RC1.xsd",
        "rel": "xsd/ProteusPIDSchema_4.1.1_RC1.xsd",
        "url": "https://raw.githubusercontent.com/ProteusXML/proteusxml/master/ProteusPIDSchema%204.1.1%20release%20candidate%201.xsd",
    },
    {
        "name": "LICENSE",
        "rel": "LICENSE",
        "url": "https://gitlab.com/api/v4/projects/dexpi%2FTrainingTestCases/repository/files/LICENSE/raw?ref=master",
    },
]

# GitLab TrainingTestCases (CC-BY-4.0) — dexpi 1.3 example P&IDs
GITLAB_PIDS = {
    "C01V04-VER.EX01.xml": "dexpi 1.3/example pids/C01 DEXPI Reference P&ID/C01V04-VER.EX01.xml",
    "C03V04-VER.EX02.xml": "dexpi 1.3/example pids/C03 Piping (Equinor)/C03V04-VER.EX02.xml",
    "E06V01-VER.EX01.xml": "dexpi 1.3/example pids/E06 Pump, HeatExchanger, Nozzles Connected With PNS/E06V01-VER.EX01.xml",
    "P01V01-VER.EX01.xml": "dexpi 1.3/example pids/P01 Pipe FromTo Nozzles/P01V01-VER.EX01.xml",
    "P02V01-VER.EX01.xml": "dexpi 1.3/example pids/P02 Pipe From OPC to Nozzle/P02V01-VER.EX01.xml",
}


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _gitlab_raw(repo_path: str) -> str:
    return (
        "https://gitlab.com/api/v4/projects/dexpi%2FTrainingTestCases/repository/files/"
        + urllib.parse.quote(repo_path, safe="")
        + "/raw?ref=master"
    )


def main() -> None:
    (DEST / "xsd").mkdir(parents=True, exist_ok=True)
    (DEST / "pids").mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    for item in SOURCES:
        dest = DEST / item["rel"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = _fetch(item["url"])
            digest = hashlib.sha256(data).hexdigest()
            if item["name"] in EXPECTED_SHA256 and digest != EXPECTED_SHA256[item["name"]]:
                raise ValueError(f"sha256 mismatch for {item['name']}: {digest}")
            dest.write_bytes(data)
            results.append(
                {"name": item["name"], "url": item["url"], "sha256": digest, "bytes": len(data), "ok": True}
            )
            print(f"OK {item['name']} sha256={digest} bytes={len(data)}")
        except Exception as exc:  # noqa: BLE001
            results.append({"name": item["name"], "url": item["url"], "ok": False, "error": str(exc)})
            print(f"FAIL {item['name']}: {exc}")

    for name, repo_path in GITLAB_PIDS.items():
        url = _gitlab_raw(repo_path)
        dest = DEST / "pids" / name
        try:
            data = _fetch(url)
            digest = hashlib.sha256(data).hexdigest()
            if name in EXPECTED_SHA256 and digest != EXPECTED_SHA256[name]:
                raise ValueError(f"sha256 mismatch for {name}: {digest}")
            dest.write_bytes(data)
            results.append(
                {
                    "name": name,
                    "url": url,
                    "path": repo_path,
                    "sha256": digest,
                    "bytes": len(data),
                    "ok": True,
                }
            )
            print(f"OK {name} sha256={digest} bytes={len(data)}")
        except Exception as exc:  # noqa: BLE001
            results.append({"name": name, "url": url, "path": repo_path, "ok": False, "error": str(exc)})
            print(f"FAIL {name}: {exc}")

    # C08: list GitLab tree; vendor any *.xml. Upstream historically PDF/XLS only.
    c08_repo = "dexpi 1.3/example pids/C08 Two connected P&IDs (Covestro)"
    c08_xml = 0
    try:
        import json as _json
        tree_url = (
            "https://gitlab.com/api/v4/projects/dexpi%2FTrainingTestCases/repository/tree?path="
            + urllib.parse.quote(c08_repo)
            + "&ref=master&per_page=100&recursive=true"
        )
        tree = _json.loads(_fetch(tree_url).decode("utf-8"))
        for item in tree:
            if item.get("type") == "blob" and str(item.get("name", "")).lower().endswith(".xml"):
                c08_xml += 1
                name = item["name"]
                url = _gitlab_raw(item["path"])
                dest = DEST / "pids" / "c08" / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                data = _fetch(url)
                digest = hashlib.sha256(data).hexdigest()
                dest.write_bytes(data)
                results.append(
                    {
                        "name": f"C08/{name}",
                        "url": url,
                        "path": item["path"],
                        "sha256": digest,
                        "bytes": len(data),
                        "ok": True,
                    }
                )
                print(f"OK C08/{name} sha256={digest} bytes={len(data)}")
        results.append(
            {
                "name": "C08",
                "ok": c08_xml > 0,
                "xml_count": c08_xml,
                "note": (
                    "Upstream Covestro C08 PDF/XLS only"
                    if c08_xml == 0
                    else f"vendored {c08_xml} XML"
                ),
            }
        )
        print(f"NOTE C08: upstream xml_count={c08_xml}")
    except Exception as exc:  # noqa: BLE001
        results.append({"name": "C08", "ok": False, "error": str(exc)})
        print(f"FAIL C08 list: {exc}")

    (DEST / "fetch_manifest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    # Also keep a cache copy of the manifest for Makefile compatibility
    cache = ROOT / "fixtures" / "public" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "fetch_manifest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
