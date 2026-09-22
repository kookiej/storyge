"""인스타그램 로그인 세션 확보 (instagrapi 기반).

순서:
  1) data/session.json 에 저장된 세션 재사용
  2) 브라우저(크롬/엣지/파이어폭스 등)에 남아 있는 sessionid 쿠키 재사용
  3) 그래도 안 되면 한 번만 로그인 -> 세션을 저장해 다음부터는 1)로 통과

스토리는 비로그인 상태로는 조회할 수 없기 때문에 이 단계가 반드시 필요하다.

instaloader 대신 instagrapi 를 쓰는 이유:
  instaloader 는 웹 GraphQL 주소(하드코딩된 query_hash)로 스토리를 가져오는데,
  인스타그램이 이 경로를 자주 막아 401 "Please wait a few minutes" 가 뜬다.
  instagrapi 는 실제 앱이 쓰는 비공개 모바일 API 를 우선 사용한다.

진행 상황은 log 콜백으로 내보낸다. GUI 는 창에 찍고, 콘솔은 print 를 넘긴다.
"""

from __future__ import annotations

import getpass
from typing import Callable, Optional, Tuple

from instagrapi import Client
from instagrapi.exceptions import (
    BadPassword,
    ChallengeRequired,
    ClientLoginRequired,
    ClientThrottledError,
    LoginRequired,
    PleaseWaitFewMinutes,
    RateLimitError,
    TwoFactorRequired,
)

from . import config, credentials, paths
from .i18n import t

# browser_cookie3 함수 이름과 화면에 보여줄 이름
_BROWSERS = [
    ("Chrome", "chrome"),
    ("Edge", "edge"),
    ("Firefox", "firefox"),
    ("Brave", "brave"),
    ("Chromium", "chromium"),
    ("Opera", "opera"),
    ("Vivaldi", "vivaldi"),
]

# (아이디, 비밀번호) 또는 취소하면 None
CredentialsAsker = Callable[[], Optional[Tuple[str, str]]]
# 2단계 인증 코드 또는 취소하면 None
TwoFactorAsker = Callable[[], Optional[str]]
Logger = Callable[[str], None]

# 요청 사이에 두는 간격(초). 너무 빠르게 두드리면 인스타그램이 일시 차단한다.
DELAY_RANGE = [1, 3]


class LoginFailed(Exception):
    pass


class RateLimited(Exception):
    """인스타그램이 '잠시 후 다시 시도하라'고 응답한 상태."""


def describe_error(err: BaseException) -> str:
    """예외를 사람이 읽을 수 있는 한 줄로 바꾼다.

    윈도우 COM 오류(pywintypes.com_error)는 str() 하면
    "(-2147221020, '잘못된 구문입니다.', None, None)" 같은 튜플이 그대로 나와
    무슨 일인지 알 수 없다. 메시지 부분만 뽑아 준다.
    """
    args = getattr(err, "args", None)
    if isinstance(args, tuple) and len(args) >= 2 and isinstance(args[0], int) and isinstance(args[1], str):
        return t("{message} (윈도우 오류 코드 0x{code})",
                 message=args[1], code=f"{args[0] & 0xFFFFFFFF:08X}")
    text = str(err).strip()
    return text or type(err).__name__


def is_rate_limit(err: BaseException) -> bool:
    return isinstance(err, (PleaseWaitFewMinutes, RateLimitError, ClientThrottledError))


RATE_LIMIT_HELP = (
    "인스타그램이 요청을 잠시 막았습니다. 몇 분에서 몇 시간 뒤에 다시 시도해 주세요.\n"
    "짧은 간격으로 여러 번 실행하면 이 상태가 길어집니다."
)


def _new_client() -> Client:
    client = Client()
    client.delay_range = DELAY_RANGE      # 요청 사이에 무작위로 쉬어 차단을 피한다
    return client


def _session_state(client: Client) -> tuple[bool, Optional[str]]:
    """(세션이 살아있는가, 확인을 못 한 이유).

      - (True, None)    -> 확실히 로그인됨
      - (False, None)   -> 확실히 만료됨
      - (False, 이유)   -> 확인 자체를 못 함 (레이트 리밋·네트워크 등)

    확인이 안 됐다고 멀쩡한 세션을 버리면 매번 다시 로그인하게 되므로 구분한다.
    """
    try:
        client.get_timeline_feed()
        return True, None
    except (LoginRequired, ClientLoginRequired):
        return False, None
    except Exception as err:
        return False, describe_error(err)


def _from_saved_session(cfg: config.Config, log: Logger) -> Optional[Client]:
    if not (paths.SESSION_FILE.exists() and cfg.login_user):
        return None

    client = _new_client()
    try:
        client.load_settings(paths.SESSION_FILE)
    except Exception as err:
        log(t("  저장된 세션을 읽지 못했습니다: {reason}", reason=describe_error(err)))
        return None

    alive, reason = _session_state(client)
    if alive:
        log(t("  저장된 세션으로 로그인됨 (@{user})", user=cfg.login_user))
        return client
    if reason:
        # 확인을 못 했을 뿐이니 세션을 버리지 않는다.
        # 정말 만료됐다면 스토리를 가져오는 단계에서 걸러진다.
        log(t("  로그인 확인 요청이 실패했지만 저장된 세션을 그대로 씁니다 (@{user})",
              user=cfg.login_user))
        log(t("    이유: {reason}", reason=reason))
        return client
    log(t("  저장된 세션이 만료되었습니다."))
    return None


def _from_saved_credentials(cfg: config.Config, log: Logger) -> Optional[Client]:
    """저장해 둔 아이디/비밀번호로 말없이 다시 로그인한다.

    세션이 만료됐을 때 사용자가 다시 타이핑하지 않아도 되게 하는 부분이다.
    실패하면 None 을 돌려주고, 부르는 쪽이 다음 방법(쿠키 -> 로그인 창)으로 넘어간다.
    """
    saved = credentials.load()
    if saved is None:
        return None
    username, password = saved

    log(t("  저장된 로그인 정보로 다시 로그인합니다 (@{user})", user=username))
    client = _new_client()
    try:
        client.login(username, password)
    except TwoFactorRequired:
        # 코드가 필요하니 자동으로는 끝낼 수 없다. 창을 띄우는 쪽으로 넘긴다.
        log(t("  2단계 인증이 필요해 자동 로그인을 건너뜁니다."))
        return None
    except BadPassword:
        log(t("  저장된 비밀번호가 더 이상 맞지 않습니다. 다시 입력이 필요합니다."))
        credentials.clear()
        return None
    except Exception as err:
        if is_rate_limit(err):
            # 여기서 더 두드리면 차단이 길어진다. 그대로 알리고 멈춘다.
            raise LoginFailed(t(RATE_LIMIT_HELP)) from err
        log(t("  자동 로그인에 실패했습니다: {reason}", reason=describe_error(err)))
        return None

    _save(client, client.username or username, cfg, log)
    return client


def forget_login(cfg: config.Config) -> None:
    """저장된 로그인 정보를 모두 지운다 (세션 + 자격증명 + 기억한 아이디)."""
    credentials.clear()
    try:
        paths.SESSION_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    cfg.login_user = None
    config.save(cfg)


def _from_browser_cookies(log: Logger) -> Optional[Client]:
    """브라우저 쿠키 재사용 시도. 어떤 이유로 실패하든 절대 예외를 밖으로 내지 않는다.

    이건 '편의 기능'이라, 여기서 실패해도 로그인 창으로 넘어가면 그만이다.
    (예: 관리자 권한으로 실행하면 shadowcopy 가 WMI/COM 을 쓰는데 여기서 COM 오류가 날 수 있다)
    """
    try:
        return _try_browser_cookies(log)
    except Exception as err:
        log(t("  브라우저 쿠키를 확인하지 못해 건너뜁니다: {reason}", reason=describe_error(err)))
        return None


def _try_browser_cookies(log: Logger) -> Optional[Client]:
    try:
        import browser_cookie3
    except Exception as err:
        # ImportError 뿐 아니라, 딸려 오는 COM 관련 모듈이 import 중에 터질 수도 있다
        log(t("  브라우저 쿠키 기능을 쓸 수 없습니다: {reason}", reason=describe_error(err)))
        return None

    needs_admin = False
    reasons: list[str] = []

    for label, func_name in _BROWSERS:
        loader_func = getattr(browser_cookie3, func_name, None)
        if loader_func is None:
            continue
        try:
            jar = loader_func(domain_name="instagram.com")
            cookies = {c.name: c.value for c in jar}
        except Exception as err:
            # 크롬/엣지는 127 버전부터 쿠키가 더 강하게 암호화돼 있어
            # 관리자 권한 없이는 읽지 못한다.
            if type(err).__name__ == "RequiresAdminError":
                needs_admin = True
                reasons.append(t("{browser}: 관리자 권한 필요", browser=label))
            else:
                reasons.append(t("{browser}: {reason}", browser=label, reason=describe_error(err)))
            continue

        sessionid = cookies.get("sessionid")
        if not sessionid:
            reasons.append(t("{browser}: 인스타그램에 로그인돼 있지 않음", browser=label))
            continue

        client = _new_client()
        try:
            if client.login_by_sessionid(sessionid):
                log(t("  {browser} 에 남아 있는 로그인 쿠키를 사용합니다 (@{user})",
                      browser=label, user=client.username))
                return client
            reasons.append(t("{browser}: 쿠키로 로그인하지 못함", browser=label))
        except Exception as err:
            reasons.append(t("{browser}: {reason}", browser=label, reason=describe_error(err)))

    log(t("  브라우저에서 쓸 수 있는 인스타 로그인 쿠키를 찾지 못했습니다."))
    for reason in reasons:
        log(f"    · {reason}")
    if needs_admin:
        log(t("    힌트: 이 방식을 쓰려면 '관리자 권한으로 실행' 해야 합니다."))
        log(t("          번거로우면 아래에서 한 번만 로그인하세요(세션이 저장됩니다)."))
    return None


def _console_credentials() -> Optional[Tuple[str, str]]:
    print(t("\n브라우저 쿠키를 쓰지 못해 직접 로그인이 필요합니다."))
    print(t("(한 번만 하면 세션이 저장되어 다음 실행부터는 묻지 않습니다)"))
    user = input(t("인스타그램 ID: ")).strip().lstrip("@")
    if not user:
        return None
    return user, getpass.getpass(t("비밀번호(화면에 보이지 않음): "))


def _console_two_factor() -> Optional[str]:
    return input(t("2단계 인증 코드: ")).strip() or None


def _do_login(
    ask_credentials: CredentialsAsker,
    ask_two_factor: TwoFactorAsker,
    log: Logger,
) -> tuple[Client, str]:
    answer = ask_credentials()
    if not answer:
        raise LoginFailed(t("로그인을 취소했습니다."))
    user, password = answer
    user = user.strip().lstrip("@")
    if not user or not password:
        raise LoginFailed(t("ID 와 비밀번호를 모두 입력해야 합니다."))

    client = _new_client()
    try:
        client.login(user, password)
    except TwoFactorRequired:
        log(t("  2단계 인증이 필요합니다."))
        code = ask_two_factor()
        if not code:
            raise LoginFailed(t("2단계 인증을 취소했습니다."))
        try:
            client.login(user, password, verification_code=code)
        except Exception as err:
            raise LoginFailed(
                t("2단계 인증에 실패했습니다: {reason}", reason=describe_error(err))
            ) from err
    except BadPassword as err:
        raise LoginFailed(
            t("ID 또는 비밀번호가 틀렸습니다: {reason}", reason=describe_error(err))
        ) from err
    except ChallengeRequired as err:
        raise LoginFailed(t(
            "인스타그램이 본인 확인을 요구합니다. 브라우저나 휴대폰 앱에서 인스타그램에 "
            "로그인해 확인 절차를 마친 뒤 다시 시도해 주세요.\n  ({reason})",
            reason=describe_error(err),
        )) from err
    except Exception as err:
        if is_rate_limit(err):
            raise LoginFailed(t(RATE_LIMIT_HELP)) from err
        raise LoginFailed(
            t("로그인에 실패했습니다: {reason}", reason=describe_error(err))
        ) from err

    # 세션이 만료돼도 다시 묻지 않으려면 여기서 보관해 두는 수밖에 없다.
    # (instagrapi 의 dump_settings 는 비밀번호를 저장하지 않는다)
    credentials.save(user, password)
    return client, (client.username or user)


def _save(client: Client, username: str, cfg: config.Config, log: Logger) -> None:
    try:
        paths.ensure_data_dir()
        client.dump_settings(paths.SESSION_FILE)
        cfg.login_user = username
        config.save(cfg)
        log(t("  세션을 저장했습니다. 다음부터는 로그인 없이 실행됩니다."))
    except Exception as err:
        # 저장에 실패해도 이번 실행은 계속할 수 있다.
        log(t("  세션 저장에 실패했습니다(이번 실행은 계속 진행): {reason}",
              reason=describe_error(err)))


def get_client(
    cfg: config.Config,
    force_login: bool = False,
    log: Logger = print,
    ask_credentials: Optional[CredentialsAsker] = None,
    ask_two_factor: Optional[TwoFactorAsker] = None,
) -> Client:
    """로그인된 instagrapi Client 를 돌려준다."""
    log(t("인스타그램 로그인 상태 확인 중..."))

    # force_login=True 는 '로그인' 버튼을 누른 것 = 계정을 바꾸겠다는 뜻이다.
    # 이때 저장된 세션과 자격증명을 건너뛰지 않으면 늘 같은 계정으로만 들어가
    # 계정을 영영 바꿀 수 없게 된다.
    if not force_login:
        client = _from_saved_session(cfg, log)
        if client is not None:
            return client

        client = _from_saved_credentials(cfg, log)
        if client is not None:
            return client

        client = _from_browser_cookies(log)
        if client is not None:
            _save(client, client.username or "", cfg, log)
            return client

    client, name = _do_login(
        ask_credentials or _console_credentials,
        ask_two_factor or _console_two_factor,
        log,
    )
    _save(client, name, cfg, log)
    return client
