"""파일명 규칙.

    YYMMDD @계정 #번호

  - 번호는 '같은 날짜 + 같은 계정' 묶음 안에서 1부터 매긴다.
  - 그 묶음이 한 개뿐이면 ' #번호' 를 붙이지 않는다.
  - 저장 폴더에 같은 묶음의 파일이 이미 있으면 그 뒤 번호부터 이어서 매긴다.
    (예전에 받아 둔 파일을 덮어쓰거나 이름이 겹치는 것을 막기 위해)

여기서 만드는 것은 확장자를 뺀 '스템'이다. 확장자는 실제 내려받을 때
응답의 Content-Type 을 보고 instaloader 가 붙인다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .model import StoryItemInfo


def base_name(item: StoryItemInfo) -> str:
    """번호를 뺀 부분. 예: '260830 @abc'"""
    return f"{item.taken_at:%y%m%d} @{item.account}"


def _highest_existing_number(save_dir: Path, base: str) -> int:
    """저장 폴더에 이미 있는 같은 묶음 파일 중 가장 큰 번호.

    번호 없는 파일 하나는 1번을 차지한 것으로 본다. 하나도 없으면 0.
    """
    if not save_dir.is_dir():
        return 0

    numbered = re.compile(rf"^{re.escape(base)} #(\d+)$")
    highest = 0
    for path in save_dir.glob(f"{base}*"):
        if not path.is_file():
            continue
        stem = path.stem
        if stem == base:
            highest = max(highest, 1)
            continue
        match = numbered.match(stem)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def build_names(items: list[StoryItemInfo], save_dir: Path) -> dict[int, str]:
    """mediaid -> 확장자 없는 파일명."""
    groups: dict[str, list[StoryItemInfo]] = defaultdict(list)
    for item in items:
        groups[base_name(item)].append(item)

    names: dict[int, str] = {}
    for base, group in groups.items():
        group.sort(key=lambda i: i.taken_at)
        start = _highest_existing_number(save_dir, base)

        # 새로 받는 게 딱 하나이고 기존 파일도 없을 때만 번호를 생략한다.
        if start == 0 and len(group) == 1:
            names[group[0].mediaid] = base
            continue

        for offset, item in enumerate(group, start=start + 1):
            names[item.mediaid] = f"{base} #{offset}"

    return names
