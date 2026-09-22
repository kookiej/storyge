"""고른 스토리를 저장 폴더에 내려받는다."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from . import history, naming, net
from .i18n import t
from .model import StoryItemInfo
from .session import describe_error

Logger = Callable[[str], None]


def save_one(item: StoryItemInfo, save_dir: Path, stem: str) -> tuple[Path, bool]:
    """파일 하나를 저장한다. (실제 저장 경로, 새로 받았는지 여부).

    실패하면 예외를 그대로 올린다 — 어떻게 알릴지는 부르는 쪽이 정한다.
    창(exe)은 아래 download_items 가 로그 문장으로 바꾸고, 웹은 이 함수를 직접
    불러 구조화된 결과를 만든다 (번역된 문장을 되파싱하지 않으려고).
    """
    path, downloaded = net.download_to(item.media_url, save_dir / stem, item.is_video)
    if downloaded:
        # 탐색기에서 시간순 정렬이 되도록 파일 시각을 스토리 시각에 맞춘다
        try:
            stamp = item.taken_at.timestamp()
            os.utime(path, (stamp, stamp))
        except OSError:
            pass
    return path, downloaded


def download_items(
    items: list[StoryItemInfo],
    save_dir: Path,
    log: Logger = print,
    should_stop: Optional[Callable[[], bool]] = None,
    names: Optional[dict[int, str]] = None,
) -> tuple[int, int]:
    """(저장 성공 수, 실패 수).

    should_stop 은 파일 하나를 받기 전마다 확인한다. 중간에 멈춰도 그때까지 받은
    파일은 남고 history 에도 기록된다 (다음에 같은 것을 또 받지 않는다).

    names 를 주면 그 이름을 쓴다. 주지 않으면 지금까지처럼 naming.py 의 규칙을
    따른다 — 창(exe)에서 부를 때는 항상 이쪽이다.
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    if names is None:
        names = naming.build_names(items, save_dir)

    saved_ids: list[int] = []
    ok = 0
    failed = 0

    for item in sorted(items, key=lambda i: (i.account, i.taken_at)):
        if should_stop and should_stop():
            log(t("중지 요청으로 나머지 저장을 건너뜁니다."))
            break
        stem = names[item.mediaid]
        try:
            path, downloaded = save_one(item, save_dir, stem)
        except Exception as err:
            log(t("  실패: {name} ({reason})", name=stem, reason=describe_error(err)))
            failed += 1
            continue

        if downloaded:
            log(t("  저장: {name}", name=path.name))
            ok += 1
        else:
            log(t("  건너뜀(이미 있음): {name}", name=path.name))
        saved_ids.append(item.mediaid)

    if saved_ids:
        history.add(saved_ids)

    return ok, failed
