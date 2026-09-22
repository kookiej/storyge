"""예약 수집이 모아 둔 스토리 임시 보관함 (data/staging/).

왜 원본과 썸네일을 **둘 다** 내려받는가:
  스토리는 24시간이면 사라지고 인스타 CDN 주소도 함께 죽는다. 나중에 골라서 저장하려면
  그때 다시 받을 수 없으므로 지금 받아 둬야 한다. 영상은 원본이 mp4 라 미리보기로 쓸 수
  없어서 표지 이미지를 따로 보관한다.

index.json 이 깨져도 프로그램이 죽지 않고 빈 보관함으로 시작한다.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from . import history, naming, net, paths
from .fetch import StoryItemInfo

Logger = Callable[[str], None]


@dataclass
class StagedRecord:
    mediaid: int
    account: str
    taken_at: datetime
    is_video: bool
    media: str          # 파일 이름 (staging 폴더 기준)
    thumb: str
    fetched_at: datetime


def _load_index() -> dict[str, dict]:
    if not paths.STAGING_INDEX.exists():
        return {}
    try:
        with paths.STAGING_INDEX.open(encoding="utf-8-sig") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        # 보관함이 깨져도 앱은 떠야 한다. 파일은 남지만 목록에서는 빠진다.
        return {}


def _save_index(index: dict[str, dict]) -> None:
    paths.ensure_staging_dir()
    with paths.STAGING_INDEX.open("w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def _to_record(key: str, raw: dict) -> Optional[StagedRecord]:
    try:
        return StagedRecord(
            mediaid=int(key),
            account=raw["account"],
            taken_at=datetime.fromisoformat(raw["taken_at"]),
            is_video=bool(raw.get("is_video", False)),
            media=raw["media"],
            thumb=raw.get("thumb") or raw["media"],
            fetched_at=datetime.fromisoformat(raw["fetched_at"]),
        )
    except (KeyError, ValueError, TypeError):
        return None


def records() -> list[StagedRecord]:
    found = [_to_record(k, v) for k, v in _load_index().items()]
    good = [r for r in found if r is not None]
    good.sort(key=lambda r: (r.account, r.taken_at))
    return good


def staged_ids() -> set[int]:
    """이미 보관 중인 mediaid. 예약 실행이 같은 것을 또 받지 않게 하는 데 쓴다."""
    return {r.mediaid for r in records()}


def count() -> int:
    return len(records())


def items() -> list[StoryItemInfo]:
    """선택 창에 넘길 형태. 주소 자리에 **로컬 파일 경로**가 들어간다.

    picker 는 thumb_url 을 콜백으로 읽으므로, 파일을 읽는 함수만 넘기면 그대로 쓸 수 있다.
    """
    result = []
    for r in records():
        result.append(StoryItemInfo(
            account=r.account,
            mediaid=r.mediaid,
            taken_at=r.taken_at,
            is_video=r.is_video,
            thumb_url=str(paths.STAGING_DIR / r.thumb),
            media_url=str(paths.STAGING_DIR / r.media),
        ))
    return result


def read_bytes(path: str) -> bytes:
    """picker 에 넘길 fetch_bytes. 주소가 아니라 로컬 파일을 읽는다."""
    return Path(path).read_bytes()


def add(item: StoryItemInfo, log: Logger = print) -> bool:
    """스토리 하나를 보관함에 내려받는다. 이미 있으면 건너뛴다."""
    index = _load_index()
    if str(item.mediaid) in index:
        return False

    paths.ensure_staging_dir()
    try:
        media_path, _ = net.download_to(
            item.media_url, paths.STAGING_DIR / str(item.mediaid), item.is_video
        )
        thumb_path, _ = net.download_to(
            item.thumb_url, paths.STAGING_DIR / f"{item.mediaid}_thumb", False
        )
    except Exception as err:
        log(f"  보관 실패: @{item.account} {item.mediaid} ({err})")
        return False

    index[str(item.mediaid)] = {
        "account": item.account,
        "taken_at": item.taken_at.isoformat(),
        "is_video": item.is_video,
        "media": media_path.name,
        "thumb": thumb_path.name,
        "fetched_at": datetime.now().isoformat(),
    }
    _save_index(index)
    return True


def _delete_files(record: StagedRecord) -> None:
    for name in (record.media, record.thumb):
        try:
            (paths.STAGING_DIR / name).unlink(missing_ok=True)
        except OSError:
            pass


def remove(mediaids) -> int:
    index = _load_index()
    removed = 0
    for mediaid in mediaids:
        raw = index.pop(str(mediaid), None)
        if raw is None:
            continue
        record = _to_record(str(mediaid), raw)
        if record:
            _delete_files(record)
        removed += 1
    if removed:
        _save_index(index)
    return removed


def purge_older_than(days: int) -> int:
    """받은 지 days 일이 지난 보관분을 지운다. 0 이면 지우지 않는다."""
    if days <= 0:
        return 0
    cutoff = datetime.now() - timedelta(days=days)
    old = [r.mediaid for r in records() if r.fetched_at < cutoff]
    return remove(old)


def clear_all() -> int:
    """보관함을 통째로 비운다."""
    all_ids = [r.mediaid for r in records()]
    removed = remove(all_ids)
    # 목록에 없는 찌꺼기 파일까지 정리
    try:
        for path in paths.STAGING_DIR.glob("*"):
            if path.is_file() and path.name != paths.STAGING_INDEX.name:
                path.unlink(missing_ok=True)
    except OSError:
        pass
    return removed


def move_to(chosen: list[StoryItemInfo], save_dir: Path, log: Logger = print) -> tuple[int, int]:
    """고른 항목을 저장 폴더로 옮긴다. (성공, 실패)

    파일명은 평소 저장과 똑같이 naming.build_names() 를 쓴다.
    옮긴 것은 보관함에서 지우고 history 에 남겨 다음에 또 받지 않게 한다.
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    names = naming.build_names(chosen, save_dir)

    moved_ids: list[int] = []
    ok = failed = 0

    for item in sorted(chosen, key=lambda i: (i.account, i.taken_at)):
        source = Path(item.media_url)
        target = save_dir / (names[item.mediaid] + source.suffix)
        try:
            shutil.copy2(source, target)
            stamp = item.taken_at.timestamp()
            os.utime(target, (stamp, stamp))
        except Exception as err:
            log(f"  실패: {target.name} ({err})")
            failed += 1
            continue
        log(f"  저장: {target.name}")
        ok += 1
        moved_ids.append(item.mediaid)

    if moved_ids:
        history.add(moved_ids)
        remove(moved_ids)
    return ok, failed
