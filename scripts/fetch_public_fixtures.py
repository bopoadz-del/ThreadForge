#!/usr/bin/env python3
"""One-shot fetch of public DEXPI/Proteus assets into fixtures/public/dexpi13/.

Runtime ThreadForge never calls this. Checksums recorded in SOURCES.md / fetch_manifest.json.
Network is required only for this script (not for tests once vendored).

Vendors every ``*.xml`` under TrainingTestCases ``dexpi 1.3/example pids/``
(CC-BY-4.0) plus Proteus XSDs. C08 historically has 0 Proteus XML upstream.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "fixtures" / "public" / "dexpi13"
UA = {"User-Agent": "ThreadForge-fetch/1.0"}
GITLAB_PROJECT = "dexpi%2FTrainingTestCases"
EXAMPLE_PIDS = "dexpi 1.3/example pids"

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


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _gitlab_raw(repo_path: str) -> str:
    return (
        f"https://gitlab.com/api/v4/projects/{GITLAB_PROJECT}/repository/files/"
        + urllib.parse.quote(repo_path, safe="")
        + "/raw?ref=master"
    )


def _gitlab_tree(path: str) -> list[dict[str, Any]]:
    """Recursive tree listing with GitLab pagination."""
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode(
            {
                "path": path,
                "ref": "master",
                "per_page": "100",
                "recursive": "true",
                "page": str(page),
            }
        )
        url = f"https://gitlab.com/api/v4/projects/{GITLAB_PROJECT}/repository/tree?{qs}"
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=120) as resp:
            batch = json.loads(resp.read().decode("utf-8"))
            next_page = resp.headers.get("X-Next-Page") or ""
        if not isinstance(batch, list):
            raise ValueError(f"unexpected tree payload: {type(batch)}")
        items.extend(batch)
        if not next_page:
            break
        page = int(next_page)
    return items


def _dest_for_pid(repo_path: str, name: str) -> Path:
    """Flatten unique basenames under pids/; prefix with parent folder on collision."""
    dest = DEST / "pids" / name
    if dest.exists():
        parent = Path(repo_path).parent.name.replace(" ", "_")
        dest = DEST / "pids" / f"{parent}__{name}"
    return dest


def main() -> None:
    (DEST / "xsd").mkdir(parents=True, exist_ok=True)
    (DEST / "pids").mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

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

    tree = _gitlab_tree(EXAMPLE_PIDS)
    xml_blobs = [
        item
        for item in tree
        if item.get("type") == "blob" and str(item.get("name", "")).lower().endswith(".xml")
    ]
    print(f"NOTE tree blobs={len(tree)} xml={len(xml_blobs)}")
    used_names: set[str] = set()
    for item in xml_blobs:
        name = str(item["name"])
        repo_path = str(item["path"])
        url = _gitlab_raw(repo_path)
        dest_name = name
        if dest_name in used_names:
            dest_name = Path(repo_path).parent.name.replace(" ", "_") + "__" + name
        used_names.add(dest_name)
        dest = DEST / "pids" / dest_name
        try:
            data = _fetch(url)
            digest = hashlib.sha256(data).hexdigest()
            if name in EXPECTED_SHA256 and digest != EXPECTED_SHA256[name]:
                raise ValueError(f"sha256 mismatch for {name}: {digest}")
            dest.write_bytes(data)
            results.append(
                {
                    "name": dest_name,
                    "url": url,
                    "path": repo_path,
                    "sha256": digest,
                    "bytes": len(data),
                    "ok": True,
                    "license": "CC-BY-4.0",
                }
            )
            print(f"OK {dest_name} sha256={digest} bytes={len(data)} path={repo_path}")
        except Exception as exc:  # noqa: BLE001
            results.append(
                {"name": dest_name, "url": url, "path": repo_path, "ok": False, "error": str(exc)}
            )
            print(f"FAIL {dest_name}: {exc}")

    # C08 capability fixtures (not upstream XML) stay as-is; record tree xml count.
    c08_repo = f"{EXAMPLE_PIDS}/C08 Two connected P&IDs (Covestro)"
    c08_xml = sum(1 for i in xml_blobs if str(i.get("path", "")).startswith(c08_repo))
    results.append(
        {
            "name": "C08",
            "ok": True,
            "xml_count": c08_xml,
            "note": (
                "Upstream Covestro C08 PDF/XLS only; capability fixtures under pids/c08/"
                if c08_xml == 0
                else f"vendored {c08_xml} XML"
            ),
        }
    )
    print(f"NOTE C08: upstream xml_count={c08_xml}")

    (DEST / "fetch_manifest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    cache = ROOT / "fixtures" / "public" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "fetch_manifest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    xml_ok = [r for r in results if r.get("ok") and str(r.get("name", "")).endswith(".xml")]
    print(f"DONE vendor_xml={len(xml_ok)}")


if __name__ == "__main__":
    main()
