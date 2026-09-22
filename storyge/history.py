"""이미 저장한 스토리의 mediaid 기록.

fetch 단계에서 걸러내는 용도로 읽고, download 단계에서 추가한다.
"""

from __future__ import annotations

import json

from . import paths


def load() -> set[int]:
    if not paths.DOWNLOADED_FILE.exists():
        return set()
    try:
        # utf-8-sig: 파일에 BOM 이 붙어 있어도 읽히게 한다 (config.py 와 같은 이유)
        with paths.DOWNLOADED_FILE.open(encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        # 기록이 깨졌다면 중복 저장이 생길 뿐 치명적이지 않으므로 빈 집합으로 계속한다.
        return set()
    return {int(m) for m in raw.get("mediaids", [])}


def add(mediaids) -> None:
    known = load()
    known.update(int(m) for m in mediaids)
    paths.ensure_data_dir()
    with paths.DOWNLOADED_FILE.open("w", encoding="utf-8") as f:
        json.dump({"mediaids": sorted(known)}, f, indent=2)
