"""수집 사이트 두 곳이 같이 쓰는 도구.

fastdl.py 와 igram.py 는 응답을 읽는 방법만 다르고 나머지는 전부 같다.
**여기 있는 코드는 사이트가 바뀌어도 고칠 일이 없어야 한다.**
사이트를 타는 부분은 각 파일의 _parse_payload 하나뿐이다.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import requests

from .. import net
from ..model import StoryItemInfo

# ---------------------------------------------------------------- 예의 규칙
#
# 남의 무료 서비스를 쓰는 것이므로 요청 수를 최소로 유지한다.
# 한 실행당 랜딩 1회 + 계정당 조회 1회, 순차 처리, 4xx 재시도 없음.
# 상대 서버에 실제로 부담을 주는 것은 UA 가 아니라 빈도다.

TIMEOUT = 30
# 계정과 계정 사이에 쉬는 시간(초). 스레드 풀을 쓰지 않는 이유이기도 하다.
DELAY_BETWEEN_ACCOUNTS = 2.0
# 연속으로 이만큼 막히면 이 사이트는 포기하고 다음 사이트로 넘어간다.
# (fetch.py 의 '차단당하면 계정 루프를 빠져나온다' 와 같은 취지)
MAX_CONSECUTIVE_ERRORS = 2

# 스토리는 24시간이면 사라진다. 이보다 오래된 것으로 계산되면 잘못 읽은 것이다.
MAX_AGE = timedelta(hours=48)


class SourceError(Exception):
    """계정 하나를 가져오지 못했다. 나머지 계정은 계속 진행한다."""


class AccountPrivate(SourceError):
    """비공개 계정. 로그인 없이는 방법이 없으므로 더 시도하지 않는다."""


class AccountNotFound(SourceError):
    pass


class SourceBlocked(Exception):
    """사이트가 우리를 막았다. 이 사이트로는 더 진행할 수 없다.

    이것만이 다른 사이트로 넘어가는 사유다. 비공개/없는 계정은 해당하지 않는다.
    """


# ---------------------------------------------------------------- HTTP

def new_http() -> requests.Session:
    """이 실행 전용 세션.

    net.get_session() 을 재사용하지 않는다 — 수집 사이트가 심은 쿠키가
    인스타그램 CDN 요청에 같이 실려 나가면 안 된다 (반대도 마찬가지).
    """
    session = requests.Session()
    session.headers.update({
        # net.py 와 같은 크롬 UA. 정직한 봇 UA 를 쓰면 첫 요청에서 막히고,
        # 상대 서버에 실제로 부담을 주는 것은 UA 가 아니라 빈도다 (위 예의 규칙).
        "User-Agent": net._UA,
        "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
    })
    return session


# 클라우드플레어가 막았을 때 본문에 나타나는 표시들
_BLOCKED_MARKS = ("just a moment", "cf-mitigated", "checking your browser",
                  "enable javascript and cookies", "attention required")


def looks_blocked(status: int, body: str) -> bool:
    if status in (403, 429, 503):
        return True
    head = body[:4000].lower()
    return any(mark in head for mark in _BLOCKED_MARKS)


# ---------------------------------------------------------------- 식별자

def synthetic_mediaid(media_url: str) -> int:
    """같은 미디어면 언제 받아도 같은 값.

    수집 사이트는 인스타그램 pk 를 주지 않는데 코드 전체가 mediaid(int) 를 키로
    쓴다 (history 중복 판별, 선택 상태, 파일명 dict). 그래서 주소로 만들어 낸다.
    서명(쿼리)은 매번 바뀌므로 **경로만** 쓴다.

    6바이트(48비트)인 이유:
      - 2**53 미만이라 JSON -> 자바스크립트 Number 에서 정밀도가 깨지지 않는다.
      - 진짜 인스타 pk(~10^18)보다 세 자릿수 작다. 그래서 두 가지가 섞여 들어가는
        data\\downloaded.json 안에서 서로 충돌할 수가 없다.
    """
    path = urlsplit(media_url).path
    return int.from_bytes(hashlib.sha1(path.encode("utf-8")).digest()[:6], "big")


def orig_name(media_url: str) -> str:
    """CDN 주소 경로에서 딴 원본 파일명 (확장자 제외).

    예: ".../481234567_1122334455_n.jpg?..." -> "481234567_1122334455_n"
    웹 버전의 기본 파일명이 이것이다.
    """
    return Path(urlsplit(media_url).path).stem


# ---------------------------------------------------------------- 시각

# "3 hours ago" / "3시간 전" / "21h" / "45 minutes ago" / "2d"
_AGE_RE = re.compile(r"(\d+)\s*(시간|분|초|일|[a-zA-Z]+)", re.IGNORECASE)

_UNITS = {
    "s": "seconds", "sec": "seconds", "secs": "seconds",
    "second": "seconds", "seconds": "seconds", "초": "seconds",
    # m 은 달이 아니라 분으로 읽는다. 스토리는 24시간이면 사라지므로 달일 수 없다.
    "m": "minutes", "min": "minutes", "mins": "minutes",
    "minute": "minutes", "minutes": "minutes", "분": "minutes",
    "h": "hours", "hr": "hours", "hrs": "hours",
    "hour": "hours", "hours": "hours", "시간": "hours",
    "d": "days", "day": "days", "days": "days", "일": "days",
}

_JUST_NOW = ("방금", "just now", "now", "지금")


def parse_relative(text: Optional[str]) -> Optional[timedelta]:
    """'3시간 전' 같은 표시를 지난 시간으로 바꾼다. 못 읽으면 None."""
    if not text:
        return None
    lowered = text.strip().lower()
    if any(mark in lowered for mark in _JUST_NOW):
        return timedelta(0)

    match = _AGE_RE.search(text)
    if not match:
        return None
    unit = _UNITS.get(match.group(2).lower())
    if not unit:
        return None
    try:
        amount = int(match.group(1))
    except ValueError:
        return None
    return timedelta(**{unit: amount})


def _to_local_naive(value: datetime) -> datetime:
    """UTC 기준 시각을 로컬 시간으로 바꾼다.

    (fetch.py 에도 같은 것이 있지만 그쪽을 불러오면 instagrapi 가 통째로 딸려 온다.)
    """
    if value.tzinfo is not None:
        value = value.astimezone()
    return value.replace(tzinfo=None)


def _from_stamp(value) -> Optional[datetime]:
    """응답이 준 타임스탬프를 해석한다. 초 단위 epoch 또는 ISO 문자열."""
    if isinstance(value, datetime):
        return _to_local_naive(value)
    if isinstance(value, (int, float)) and value > 0:
        try:
            # 밀리초로 주는 곳도 있다
            seconds = value / 1000 if value > 1e11 else value
            return datetime.fromtimestamp(seconds)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return _from_stamp(int(text))
        try:
            return _to_local_naive(datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def resolve_taken_at(
    stamp=None, age_text: Optional[str] = None, now: Optional[datetime] = None
) -> tuple[datetime, str]:
    """(올라온 시각, 어떻게 알아냈는지).

    순서:
      1. 응답이 준 진짜 시각이 있고 말이 되면 그대로  -> "exact"
      2. '3시간 전' 같은 표시를 역산                  -> "relative"
      3. 아무것도 없으면 지금 시각                    -> "fetch"

    2번만으로도 파일명 날짜는 거의 항상 맞는다. 자정 직후에 받아도 '1시간 전'이면
    어제로 제대로 떨어진다.
    """
    now = (now or datetime.now()).replace(microsecond=0)

    exact = _from_stamp(stamp)
    if exact is not None and timedelta(0) <= now - exact <= MAX_AGE:
        return exact, "exact"

    delta = parse_relative(age_text)
    if delta is not None and delta <= MAX_AGE:
        return (now - delta).replace(second=0), "relative"

    return now, "fetch"


def make_item(
    account: str, entry: dict, source_id: str, now: Optional[datetime] = None
) -> Optional[StoryItemInfo]:
    """_parse_payload 가 돌려준 평범한 dict 하나를 StoryItemInfo 로 바꾼다.

    사이트를 타는 코드(_parse_payload)가 이 자료형을 몰라도 되도록 여기서 만든다.
    주소가 없으면 None (건너뛴다).
    """
    media_url = str(entry.get("media_url") or "").strip()
    if not media_url:
        return None

    taken_at, basis = resolve_taken_at(entry.get("taken_at"), entry.get("age_text"), now)
    return StoryItemInfo(
        account=account,
        mediaid=synthetic_mediaid(media_url),
        taken_at=taken_at,
        is_video=bool(entry.get("is_video")),
        thumb_url=str(entry.get("thumb_url") or media_url),
        media_url=media_url,
        time_basis=basis,
        source=source_id,
        orig_name=orig_name(media_url),
    )
