"""로그인된 세션이 있으면 그걸로 가져온다 (웹 전용).

**이 소스만 게시 시각을 정확히 안다.** 수집 사이트(saveinsta 등)는 원본 게시 시각을
주지 않아 '받은 시각' 을 대신 쓸 수밖에 없다. 그래서 세션이 있으면 언제나 여기를
먼저 쓰고, 없으면 조용히 다음 사이트로 내려간다.

덤으로 **팔로우 중인 비공개 계정**도 가져온다 — 수집 사이트는 공개 계정만 된다.

**웹은 절대 로그인을 묻지 않는다.** ask_credentials / ask_two_factor 에 항상 None 을
돌려주는 콜백을 넘긴다. 기본 콜백은 input() 을 부르는데, 창도 콘솔도 없는 이 프로세스에서
그것이 불리면 요청이 영영 돌아오지 않는다 (launcher.run_scheduled 가 같은 이유로 같은
처리를 한다). 로그인은 exe 에서 한 번 해 두는 것이고, 웹은 그 결과만 빌려 쓴다.
"""

from __future__ import annotations

import json
from typing import Optional

from .. import config, paths
from ..i18n import t
from ..model import StoryItemInfo
from . import SiteSource
from .common import AccountNotFound, AccountPrivate, SourceBlocked, SourceError, orig_name


class _Expired(Exception):
    """실행 도중 세션이 만료됐다. 여기서만 쓰는 표시."""


def _borrowed_login_user() -> Optional[str]:
    """로그인 정보를 빌려 온 폴더에서 **계정 이름만** 읽는다.

    저장된 세션을 되살리려면 '누구의 세션인가' 가 필요하다
    (session._from_saved_session 이 cfg.login_user 없이는 아예 시도하지 않는다).
    그 이름은 설정이 아니라 **로그인 정보의 일부**라서 여기서만 건너온다 —
    계정 목록·저장 폴더 같은 나머지 설정은 서로 섞지 않는다.

    한 번 로그인에 성공하면 session._save 가 이 이름을 웹 자신의 config 에도
    적어 두므로, 다음부터는 이 함수까지 오지 않는다.
    """
    if paths.LOGIN_DIR == paths.DATA_DIR:
        return None                      # 같은 폴더면 config.load() 가 이미 갖고 있다
    try:
        raw = json.loads((paths.LOGIN_DIR / "config.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    name = raw.get("login_user") if isinstance(raw, dict) else None
    return name if isinstance(name, str) and name else None


class InstagrapiSource(SiteSource):
    id = "instagrapi"
    label = "instagram"

    def __init__(self) -> None:
        self.client = None
        # 한 실행에 다시 로그인하는 것은 한 번까지. 비밀번호가 바뀌었거나 계정이
        # 잠긴 상태에서 계정마다 로그인을 시도하면 차단만 길어진다.
        self._relogged = False

    # --- 열기 -------------------------------------------------------

    def _login(self) -> None:
        """저장된 세션 -> 저장된 자격증명 -> 브라우저 쿠키 순으로 조용히 로그인한다.

        session.get_client 가 이 순서를 이미 갖고 있다. 세션이 만료됐으면 스스로
        버리고 저장해 둔 아이디/비밀번호로 다시 로그인하며(credentials.py, DPAPI),
        성공하면 session.json 도 새것으로 덮어쓴다.
        """
        from .. import session   # instagrapi 를 여기서만 끌어온다

        cfg = config.load()
        if not cfg.login_user:
            cfg.login_user = _borrowed_login_user()

        self.client = session.get_client(
            cfg,
            force_login=False,          # True 면 저장된 자격증명까지 건너뛴다 — 여기선 반대다
            log=lambda _message: None,  # 웹에는 진행 기록 창이 없다
            ask_credentials=lambda: None,   # 절대 묻지 않는다 (위 설명 참고)
            ask_two_factor=lambda: None,
        )

    def open(self) -> None:
        """로그인을 시도한다.

        아무 수단도 없으면 SourceBlocked 를 내고 체인이 다음 사이트로 넘어간다.
        이것은 '실패' 가 아니라 '이 길은 못 쓴다' 는 뜻이라 화면에 안내가 남지 않는다.
        """
        try:
            self._login()
        except Exception as err:  # noqa: BLE001 - 로그인 실패는 그저 '이 길은 없음' 이다
            raise SourceBlocked(t("로그인된 세션이 없습니다.")) from err

    def _relogin(self) -> bool:
        """실행 도중 만료됐을 때 한 번만 조용히 다시 로그인한다."""
        if self._relogged:
            return False
        self._relogged = True
        try:
            self._login()
            return True
        except Exception:  # noqa: BLE001 - 요청 제한·2단계 인증 등. 더 두드리지 않는다.
            return False

    def close(self) -> None:
        self.client = None

    # --- 계정 하나 ---------------------------------------------------

    def _query(self, account: str) -> list:
        """계정 하나를 조회한다. 실패는 우리 예외로 바꿔서 올린다.

        **예외를 좁은 것부터 확인한다.** instagrapi 예외는 대부분 PrivateError 를
        상속해서(PleaseWaitFewMinutes, RateLimitError, LoginRequired, ChallengeRequired,
        UserNotFound ...) except 절을 나열하면 넓은 것이 먼저 잡혀 전부 '비공개 계정' 이
        되어 버린다. fetch.py 에 같은 규칙이 적혀 있다 — 고칠 때 같이 볼 것.
        """
        from instagrapi.exceptions import (
            ChallengeRequired, ClientLoginRequired, LoginRequired, PrivateError, UserNotFound,
        )
        from .. import session

        try:
            user_id = self.client.user_id_from_username(account)
            return self.client.user_stories(user_id) or []
        except Exception as err:  # noqa: BLE001 - 아래에서 좁은 것부터 가려낸다
            # 세션 만료는 되돌릴 수 있다. 부르는 쪽이 다시 로그인하고 한 번 더 해 본다.
            if isinstance(err, (LoginRequired, ClientLoginRequired)):
                raise _Expired() from err
            # 아래 둘은 계정이 아니라 **연결 자체**의 문제인데 되돌릴 수 없다.
            # SourceBlocked 로 올려 이 소스를 접고 수집 사이트로 넘어간다 —
            # 차단당한 채로 계정을 계속 두드리면 차단만 길어진다.
            if session.is_rate_limit(err):
                raise SourceBlocked(t("인스타그램이 요청을 잠시 막았습니다.")) from err
            if isinstance(err, ChallengeRequired):
                raise SourceBlocked(t("인스타그램이 본인 확인을 요구합니다.")) from err
            # 여기부터는 그 계정만의 사정이다
            if isinstance(err, UserNotFound):
                raise AccountNotFound() from err
            if isinstance(err, PrivateError):
                raise AccountPrivate() from err
            raise SourceError(session.describe_error(err)) from err

    def fetch_account(self, account: str) -> list[StoryItemInfo]:
        """계정 하나의 스토리.

        조회 도중 세션이 만료되면 **저장된 로그인 정보로 조용히 다시 로그인하고**
        같은 계정을 한 번 더 시도한다. 그러지 않으면 남은 계정이 전부 수집 사이트로
        넘어가 게시 시각을 잃는다 (거기는 시각을 주지 않는다).
        """
        from .. import fetch

        try:
            stories = self._query(account)
        except _Expired:
            if not self._relogin():
                raise SourceBlocked(t("로그인 세션이 만료됐습니다.")) from None
            try:
                stories = self._query(account)
            except _Expired:
                # 새로 로그인하고도 만료라면 더 해 볼 것이 없다
                raise SourceBlocked(t("로그인 세션이 만료됐습니다.")) from None

        items: list[StoryItemInfo] = []
        for story in stories:
            try:
                made = fetch._to_item(account, story)
            except Exception:  # noqa: BLE001 - 하나가 이상해도 나머지는 가져온다
                continue
            if made is None:
                continue
            # taken_at 은 진짜 게시 시각이다 (model 의 기본값 time_basis="exact" 그대로).
            # 웹의 기본 파일명은 CDN 원본 이름이므로 그것만 채워 준다.
            made.source = self.id
            made.orig_name = orig_name(made.media_url)
            items.append(made)
        return items
