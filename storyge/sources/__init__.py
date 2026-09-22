"""스토리를 어디서 가져올지 고르는 자리 (웹 전용).

**이 층이 웹 버전에서 가장 중요한 이음매다.** 수집 사이트는 언제든 막히거나
사라질 수 있으므로, 그 위의 모든 것(작업 러너·그리드·파일명·저장)은 여기서
무엇이 오는지 몰라야 한다. 사이트 하나가 죽으면 파일 하나를 갈아 끼우면 된다.

인터페이스는 fetch.fetch_stories 에서 client 인자만 뺀 모양이다. 진행 콜백,
중지 규약, '안내는 문제뿐' 규약이 전부 같아서 web/jobs.py 는 어느 쪽이 오든
똑같은 코드로 몰 수 있다.

    source.fetch(account_ids, skip_mediaids, should_stop, on_account)
        -> (items, notes)

사이트 하나하나는 SiteSource 를 상속해 open() / fetch_account() 만 구현한다.
계정 루프·전환·쉬는 시간·안내 문구는 ChainSource 가 전부 처리한다.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, Optional, Protocol

from ..i18n import t
from ..model import StoryItemInfo
from . import common
from .common import AccountNotFound, AccountPrivate, SourceBlocked, SourceError

# 상수는 common 을 통해 그때그때 읽는다 — 값으로 가져오면 테스트에서 쉬는 시간을
# 0 으로 줄일 수 없고, 나중에 한 곳만 고쳐도 여기가 따라오지 않는다.

__all__ = [
    "StorySource", "SiteSource", "ChainSource",
    "register", "get", "available",
    "SourceBlocked", "SourceError", "AccountPrivate", "AccountNotFound",
]

ShouldStop = Callable[[], bool]
OnAccount = Callable[[str, int, int], None]
# 계정 하나를 마칠 때마다 그 계정에서 새로 찾은 것들을 넘겨준다.
# 화면이 기다리지 않고 차례차례 차오르게 하려고 있다 (진행 중 로딩 표시).
OnItems = Callable[[str, list[StoryItemInfo]], None]


class StorySource(Protocol):
    id: str
    label: str
    # 선택 사항. 사이트를 다 해 보고도 못 가져왔으면 True 가 된다.
    # 읽는 쪽은 getattr(source, "blocked", False) 를 써서 없어도 돌게 한다.
    blocked: bool

    def fetch(
        self,
        account_ids: Iterable[str],
        skip_mediaids: Optional[set[int]] = None,
        should_stop: Optional[ShouldStop] = None,
        on_account: Optional[OnAccount] = None,
        on_items: Optional[OnItems] = None,
    ) -> tuple[list[StoryItemInfo], list[str]]:
        ...


# ---------------------------------------------------------------- 사이트 하나

class SiteSource:
    """수집 사이트 하나. 실제 파일(fastdl.py / igram.py)이 상속한다."""

    id = ""
    label = ""

    def open(self) -> None:
        """랜딩 요청·토큰 확보. 막혀 있으면 SourceBlocked 를 낸다."""

    def fetch_account(self, account: str) -> list[StoryItemInfo]:
        """계정 하나의 스토리. 못 가져오면 SourceError 계열이나 SourceBlocked."""
        raise NotImplementedError

    def close(self) -> None:
        """세션 정리. 실패해도 조용히 넘어가야 한다."""


# ---------------------------------------------------------------- 자동 전환

def _sleep(seconds: float, should_stop: Optional[ShouldStop]) -> None:
    """중지 요청을 확인하며 쉰다. 취소를 눌렀는데 2초를 기다리게 하지 않는다."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if should_stop and should_stop():
            return
        time.sleep(0.1)


class ChainSource:
    """사이트를 순서대로 써 보는 소스.

    첫 사이트가 막히면 **남은 계정 전체**를 다음 사이트로 이어서 처리한다.
    계정 단위가 아니라 실행 단위로 바꾸는 이유: 한 번 막힌 사이트는 그 실행 내내
    막혀 있고, 계정마다 다시 두드리면 차단만 길어진다.

    비공개 계정이나 없는 계정은 **전환 사유가 아니다.** 어느 사이트로 가도
    결과가 같으므로 안내만 남기고 다음 계정으로 넘어간다.

    **전환은 조용히 한다.** 사용자가 사이트를 고르지 않으므로 어디가 언제 막혔는지는
    알려 줄 이유가 없다. 다 해 보고도 안 되면 그때 `blocked` 를 세우고 안내를
    **딱 한 줄** 남긴다. 사이트별 사유는 `_failures` 에만 모아 둔다.
    """

    def __init__(self, sites: list[SiteSource], source_id: str = "auto",
                 label: str = "") -> None:
        self.id = source_id
        self.label = label or " → ".join(s.label for s in sites)
        # 모든 사이트를 다 해 보고도 못 가져왔으면 True. 화면은 이것으로
        # '사이트가 막혔다' 와 '올라온 스토리가 없다' 를 가른다.
        self.blocked = False
        self._pending = list(sites)
        self._site: Optional[SiteSource] = None
        self._errors_in_row = 0
        # 사이트별 실패 사유. 안내로 내보내지는 않고 문제를 좇을 때만 본다.
        self._failures: list[str] = []

    # --- 사이트 관리 -------------------------------------------------
    #
    # 사이트를 바꾸는 일은 **조용히** 한다. 사용자가 사이트를 고르지 않으므로
    # 어디가 언제 막혔는지는 알 바가 아니다. 전부 실패했을 때만 한 줄로 알린다.

    def _ensure_site(self) -> Optional[SiteSource]:
        """쓸 수 있는 사이트를 하나 확보한다. 다 떨어지면 None."""
        while self._site is None and self._pending:
            candidate = self._pending.pop(0)
            try:
                candidate.open()
            except Exception as err:  # noqa: BLE001 - 사이트 코드가 어떻게 터지든 다음으로 넘어간다
                self._failures.append(
                    f"{candidate.label}: {err or type(err).__name__}")
                self._safe_close(candidate)
                continue
            self._site = candidate
            self._errors_in_row = 0
        return self._site

    def _drop_site(self, reason: str) -> None:
        """지금 사이트를 포기한다. 다음 _ensure_site 가 다음 것을 연다."""
        dropped = self._site
        if dropped is None:
            return
        self._failures.append(f"{dropped.label}: {reason}")
        self._safe_close(dropped)
        self._site = None
        self._errors_in_row = 0

    @staticmethod
    def _safe_close(site: SiteSource) -> None:
        try:
            site.close()
        except Exception:  # noqa: BLE001 - 정리 실패로 수집이 멈추면 안 된다
            pass

    # --- 본체 -------------------------------------------------------

    def fetch(
        self,
        account_ids: Iterable[str],
        skip_mediaids: Optional[set[int]] = None,
        should_stop: Optional[ShouldStop] = None,
        on_account: Optional[OnAccount] = None,
        on_items: Optional[OnItems] = None,
    ) -> tuple[list[StoryItemInfo], list[str]]:
        """(스토리 목록, 안내 목록).

        안내는 **문제뿐이다.** 스토리가 없는 계정은 아무 말도 남기지 않는다
        (fetch.fetch_stories 와 같은 규약 — 계정이 많으면 그 줄만으로 가득 찬다).
        """
        skip = skip_mediaids or set()
        names = list(account_ids)
        items: list[StoryItemInfo] = []
        notes: list[str] = []
        seen: set[int] = set()

        try:
            for index, account in enumerate(names):
                if should_stop and should_stop():
                    notes.append(t("중지 요청으로 나머지 계정을 건너뜁니다."))
                    break
                if on_account:
                    on_account(account, index, len(names))

                if index:
                    _sleep(common.DELAY_BETWEEN_ACCOUNTS, should_stop)
                    if should_stop and should_stop():
                        notes.append(t("중지 요청으로 나머지 계정을 건너뜁니다."))
                        break

                found = self._fetch_one(account, notes)
                if found is None:
                    # 사이트를 다 해 봤고 전부 실패했다. 여기서 **딱 한 번** 알린다.
                    self.blocked = True
                    notes.append(t("서버에 연결하지 못했습니다."))
                    break

                fresh = []
                for item in found:
                    if item.mediaid in skip or item.mediaid in seen:
                        continue
                    seen.add(item.mediaid)
                    fresh.append(item)
                items.extend(fresh)
                if on_items and fresh:
                    # 계정 하나가 끝날 때마다 넘겨준다. 화면이 전부 끝나기를
                    # 기다리지 않고 차례차례 차오른다.
                    on_items(account, fresh)
        finally:
            if self._site is not None:
                self._safe_close(self._site)
                self._site = None

        items.sort(key=lambda i: (i.account, i.taken_at))
        return items, notes

    def _fetch_one(self, account: str, notes: list[str]) -> Optional[list[StoryItemInfo]]:
        """계정 하나. 사이트가 막히면 다음 사이트로 **같은 계정을 다시** 시도한다.

        돌려주는 값: 스토리 목록 (실패했으면 빈 목록), 또는 더 쓸 사이트가 없으면 None.
        """
        while True:
            site = self._ensure_site()
            if site is None:
                return None

            try:
                found = site.fetch_account(account)
                # 한 번이라도 성공하면 연속 실패는 끊긴 것이다. 여기서 되돌리지 않으면
                # 띄엄띄엄 실패한 것만으로도 멀쩡한 사이트를 버리게 된다.
                self._errors_in_row = 0
                return found

            except SourceBlocked as err:
                self._drop_site(str(err) or "?")
                continue                      # 같은 계정을 다음 사이트로

            except AccountPrivate:
                notes.append(t(
                    "@{account}: 비공개 계정이라 로그인 없이 가져올 수 없습니다.",
                    account=account,
                ))
                return []

            except AccountNotFound:
                notes.append(t("@{account}: 존재하지 않는 계정입니다.", account=account))
                return []

            except Exception as err:  # noqa: BLE001 - 한 계정 때문에 전체가 멈추면 안 된다
                reason = str(err) or type(err).__name__
                notes.append(t(
                    "@{account}: 스토리를 가져오지 못했습니다 ({reason}).",
                    account=account, reason=reason,
                ))
                self._errors_in_row += 1
                if self._errors_in_row >= common.MAX_CONSECUTIVE_ERRORS:
                    # 연달아 실패하면 계정 문제가 아니라 사이트 문제로 본다
                    self._drop_site(reason)
                    continue                  # 같은 계정을 다음 사이트로
                return []


# ---------------------------------------------------------------- 레지스트리

# id -> 그때그때 소스를 만들어 주는 함수.
# 소스는 실행마다 새로 만든다 (세션·토큰·전환 상태를 들고 있으므로 재사용하면 안 된다).
_REGISTRY: dict[str, Callable[[], StorySource]] = {}
_LABELS: dict[str, str] = {}


def register(source_id: str, factory: Callable[[], StorySource], label: str = "") -> None:
    """소스를 등록한다. 테스트가 가짜 소스를 꽂는 자리이기도 하다."""
    _REGISTRY[source_id] = factory
    _LABELS[source_id] = label or source_id


def get(source_id: str) -> StorySource:
    """새 소스 하나. 모르는 이름이면 auto."""
    factory = _REGISTRY.get(source_id) or _REGISTRY["auto"]
    return factory()


def available() -> list[dict]:
    """설정 화면에 보여 줄 목록."""
    return [{"id": key, "label": _LABELS.get(key, key)} for key in _REGISTRY]


def _make_instagrapi() -> SiteSource:
    from .instagrapi_source import InstagrapiSource
    return InstagrapiSource()


def _make_saveinsta() -> SiteSource:
    from .saveinsta import SaveInsta
    return SaveInsta()


def _make_fastdl() -> SiteSource:
    from .fastdl import Fastdl
    return Fastdl()


def _make_igram() -> SiteSource:
    from .igram import Igram
    return Igram()


# 기본 구성. 사이트 파일은 실제로 쓸 때만 불러온다 (import 비용과 고장 격리).
#
# 순서에 뜻이 있다.
#   instagrapi  저장된 세션이 있을 때만 열린다. **게시 시각을 정확히 아는 유일한 길**이고
#               팔로우 중인 비공개 계정도 가져온다. 없으면 조용히 다음으로 내려간다.
#   saveinsta   로그인 없이 되는 곳. 다만 게시 시각을 주지 않아 '받은 시각' 을 쓴다.
#   fastdl      요청 서명을 아직 못 만든다 (convert_site.py 의 _sign_request).
#   igram       위와 같은 백엔드. 서명이 채워지면 둘 다 살아난다.
_AUTO = t("자동")
register("auto", lambda: ChainSource(
    [_make_instagrapi(), _make_saveinsta(), _make_fastdl(), _make_igram()],
    "auto", _AUTO), _AUTO)
register("instagrapi", lambda: ChainSource([_make_instagrapi()], "instagrapi", "instagram"),
         "instagram")
register("saveinsta", lambda: ChainSource([_make_saveinsta()], "saveinsta", "saveinsta.to"),
         "saveinsta.to")
register("fastdl", lambda: ChainSource([_make_fastdl()], "fastdl", "fastdl.app"), "fastdl.app")
register("igram", lambda: ChainSource([_make_igram()], "igram", "igram.world"), "igram.world")
