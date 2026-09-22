"""로그인 정보를 윈도우 DPAPI 로 암호화해 보관한다.

왜 필요한가:
  instagrapi 의 dump_settings() 는 쿠키와 기기 정보만 저장하고 비밀번호는 남기지 않는다.
  그래서 세션이 만료되면 다시 입력받는 수밖에 없는데, 그러지 않으려면
  아이디/비밀번호를 따로 보관해야 한다.

왜 DPAPI 인가:
  CryptProtectData 로 암호화하면 **이 윈도우 계정으로 로그인한 상태에서만** 풀린다.
  파일을 통째로 복사해 다른 PC 나 다른 계정으로 가져가도 읽지 못한다.
  pywin32 가 이미 설치돼 있어 새 의존성도 필요 없다.

그래도 비밀번호를 보관하는 것은 맞으므로, 지우는 방법(clear)을 창에서 제공한다.
"""

from __future__ import annotations

import json
from typing import Optional, Tuple

from . import paths

# 이 프로그램이 만든 자료만 풀리도록 섞는 값
_ENTROPY = b"igstory-credential-v1"
_DESCRIPTION = "igstory login"


def available() -> bool:
    """이 PC 에서 DPAPI 를 쓸 수 있는지."""
    try:
        import win32crypt  # noqa: F401

        return True
    except Exception:
        return False


def save(username: str, password: str) -> bool:
    """암호화해서 저장한다. 실패해도 예외를 내지 않는다(로그인 자체는 이미 됐으므로)."""
    if not username or not password:
        return False
    try:
        import win32crypt

        blob = json.dumps({"u": username, "p": password}).encode("utf-8")
        encrypted = win32crypt.CryptProtectData(blob, _DESCRIPTION, _ENTROPY, None, None, 0)
        paths.ensure_data_dir()
        paths.CREDENTIAL_FILE.write_bytes(encrypted)
        return True
    except Exception:
        return False


def load() -> Optional[Tuple[str, str]]:
    """(아이디, 비밀번호) 또는 None. 파일이 없거나 못 풀면 조용히 None."""
    if not paths.CREDENTIAL_FILE.exists():
        return None
    try:
        import win32crypt

        encrypted = paths.CREDENTIAL_FILE.read_bytes()
        _, blob = win32crypt.CryptUnprotectData(encrypted, _ENTROPY, None, None, 0)
        data = json.loads(blob.decode("utf-8"))
        username, password = data.get("u"), data.get("p")
        if username and password:
            return username, password
    except Exception:
        # 다른 PC 에서 복사해 온 파일이거나 손상된 경우
        pass
    return None


def clear() -> None:
    try:
        paths.CREDENTIAL_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def exists() -> bool:
    return paths.CREDENTIAL_FILE.exists()
