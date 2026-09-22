"""스토리 한 건을 나타내는 자료형.

원래 fetch.py 안에 있었지만 웹 버전 때문에 여기로 옮겼다. fetch.py 를 불러오면
instagrapi 가 통째로 딸려 오는데, 웹은 로그인을 쓰지 않으므로 그럴 이유가 없다.
fetch.py 가 이 이름을 다시 내보내므로 기존 `from .fetch import StoryItemInfo` 는
그대로 동작한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class StoryItemInfo:
    account: str          # 소유 계정 ID
    mediaid: int          # 중복 판별 키
    taken_at: datetime    # 올라온 시각 (로컬 시간)
    is_video: bool
    thumb_url: str        # 미리보기용 이미지 (영상이면 표지)
    media_url: str        # 실제로 저장할 원본

    # --- 아래는 웹 버전에서만 채운다. 전부 기본값이 있어야 한다 -------------
    # staging.py 가 키워드 인자로 이 자료형을 만들기 때문에, 기본값 없는 필드를
    # 뒤에 붙이면 예약 수집이 깨진다.

    # taken_at 을 어떻게 알아냈는지.
    #   "exact"    응답이 준 진짜 시각
    #   "relative" '3시간 전' 같은 표시를 역산한 값 (오차 ±1시간)
    #   "fetch"    아무것도 못 찾아서 가져온 시각을 그대로 쓴 값
    # 화면은 exact 가 아닐 때 '~' 를 붙여 추정값임을 알린다.
    time_basis: str = "exact"

    # 이 항목을 실제로 가져온 곳 ("instagrapi" / "fastdl" / "igram" / "fake")
    source: str = "instagrapi"

    # CDN 주소 경로에서 딴 원본 파일명 (확장자 제외).
    # 웹 버전의 기본 파일명이 이것이다. 예: "481234567_1122334455_n"
    orig_name: str = ""

    @property
    def label(self) -> str:
        return self.taken_at.strftime("%m-%d %H:%M")
