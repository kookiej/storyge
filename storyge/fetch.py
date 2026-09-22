"""대상 계정들의 현재 스토리 목록을 가져온다 (instagrapi 기반)."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Iterable, Optional

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    ClientLoginRequired,
    LoginRequired,
    PrivateError,
    UserNotFound,
)

from .i18n import t
from .model import StoryItemInfo  # 예전부터 여기서 가져다 쓰던 곳들이 있어 다시 내보낸다
from .session import RATE_LIMIT_HELP, describe_error, is_rate_limit

__all__ = ["StoryItemInfo", "fetch_stories"]


def _to_local_naive(value: datetime) -> datetime:
    """instagrapi 는 UTC 기준 시각을 주므로 로컬 시간으로 바꾼다.

    파일명의 날짜(YYMMDD)가 실제로 본 시각과 어긋나지 않게 하려면 반드시 필요하다.
    """
    if value.tzinfo is not None:
        value = value.astimezone()
    return value.replace(tzinfo=None)


def _to_item(account: str, story) -> Optional[StoryItemInfo]:
    is_video = story.media_type == 2
    media_url = story.video_url if is_video else story.thumbnail_url
    if not media_url:
        return None
    return StoryItemInfo(
        account=account,
        mediaid=int(story.pk),
        taken_at=_to_local_naive(story.taken_at),
        is_video=is_video,
        thumb_url=str(story.thumbnail_url or media_url),
        media_url=str(media_url),
    )


def fetch_stories(
    client: Client,
    account_ids: Iterable[str],
    skip_mediaids: Optional[set[int]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    on_account: Optional[Callable[[str, int, int], None]] = None,
) -> tuple[list[StoryItemInfo], list[str]]:
    """(스토리 목록, 안내 메시지 목록)을 돌려준다.

    한 계정에서 문제가 생겨도 나머지 계정은 계속 진행한다.

    돌려주는 안내는 **문제뿐이다.** '올라온 스토리가 없습니다' 같은 평범한 결과는 남기지
    않는다 — 계정이 많으면 그 줄만으로 기록이 가득 차고, 전체 결과는 부르는 쪽이 따로 알린다.

    should_stop 은 계정 하나를 시작하기 전마다 확인한다. 중간에 끊을 수 있는 자리가
    여기뿐이라서다 (계정 하나를 조회하는 중에는 instagrapi 안에서 멈춰 있다).
    창에서는 이 콜백이 '일시정지 동안 붙잡고 있다가 취소일 때만 True' 를 돌려준다.
    """
    skip = skip_mediaids or set()
    items: list[StoryItemInfo] = []
    notes: list[str] = []
    names = list(account_ids)

    for index, account in enumerate(names):
        if should_stop and should_stop():
            notes.append(t("중지 요청으로 나머지 계정을 건너뜁니다."))
            break
        if on_account:
            on_account(account, index, len(names))

        try:
            user_id = client.user_id_from_username(account)
            stories = client.user_stories(user_id)
        except Exception as err:
            # instagrapi 예외는 대부분 PrivateError 를 상속한다.
            # (PleaseWaitFewMinutes, RateLimitError, LoginRequired, ChallengeRequired, UserNotFound ...)
            # 그래서 except 절을 나열하면 넓은 것이 먼저 잡혀 엉뚱하게 안내된다.
            # 반드시 좁은 것부터 순서대로 직접 확인한다.
            if is_rate_limit(err):
                # 이미 차단당한 상태에서 다음 계정까지 두드리면 차단이 더 길어진다. 즉시 멈춘다.
                notes.append(t(RATE_LIMIT_HELP))
                break
            if isinstance(err, (LoginRequired, ClientLoginRequired)):
                notes.append(t("로그인 세션이 만료됐습니다. '로그인'을 눌러 주세요."))
                break
            if isinstance(err, ChallengeRequired):
                notes.append(t(
                    "인스타그램이 본인 확인을 요구합니다. 브라우저나 휴대폰 앱에서 "
                    "확인 절차를 마친 뒤 다시 시도해 주세요."
                ))
                break
            if isinstance(err, UserNotFound):
                notes.append(t("@{account}: 존재하지 않는 계정입니다.", account=account))
                continue
            if isinstance(err, PrivateError):
                notes.append(t("@{account}: 비공개 계정이고 팔로우하고 있지 않습니다.", account=account))
                continue
            notes.append(t(
                "@{account}: 스토리를 가져오지 못했습니다 ({reason}).",
                account=account, reason=describe_error(err),
            ))
            continue

        if not stories:
            # 스토리가 없는 것은 문제가 아니므로 아무 말도 남기지 않는다.
            # (계정이 많으면 이 줄만으로 기록이 가득 찬다. 전체 결과는 부르는 쪽이
            #  '새로 저장할 스토리가 없습니다' / '보관함에 0개' 로 알린다.)
            continue

        for story in stories:
            try:
                item = _to_item(account, story)
            except Exception as err:
                notes.append(t(
                    "@{account}: 스토리 하나를 건너뜁니다 ({reason}).",
                    account=account, reason=describe_error(err),
                ))
                continue
            if item is None or item.mediaid in skip:
                continue
            items.append(item)

    items.sort(key=lambda i: (i.account, i.taken_at))
    return items, notes
