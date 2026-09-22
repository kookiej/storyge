"""스토리 이미지·영상을 받아오는 공용 HTTP 창구.

인스타그램 CDN 주소는 로그인 없이도 받을 수 있으므로 평범한 requests 세션을 쓴다.
썸네일 미리보기와 실제 저장이 같은 연결을 재사용하도록 여기에 모아 둔다.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional

import requests

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

_session: Optional[requests.Session] = None

TIMEOUT = 60

# Content-Type -> 확장자. 인스타그램이 주는 값만 추려 둔다.
_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}


def get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": _UA})
    return _session


def fetch_bytes(url: str) -> bytes:
    """주소 하나를 통째로 받아 온다 (썸네일용)."""
    resp = get_session().get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.content


def _extension_for(content_type: Optional[str], url: str, is_video: bool) -> str:
    """저장할 확장자를 정한다. Content-Type 을 우선하고, 없으면 주소와 종류로 추정."""
    if content_type:
        base = content_type.split(";")[0].strip().lower()
        if base in _EXTENSIONS:
            return _EXTENSIONS[base]
        guessed = mimetypes.guess_extension(base)
        if guessed:
            return ".jpg" if guessed == ".jpe" else guessed

    suffix = Path(url.split("?")[0]).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"}:
        return ".jpg" if suffix == ".jpeg" else suffix

    return ".mp4" if is_video else ".jpg"


def download_to(url: str, dest_without_extension: Path, is_video: bool) -> tuple[Path, bool]:
    """파일을 내려받아 저장한다.

    확장자는 응답의 Content-Type 을 보고 정하므로, 호출하는 쪽은 확장자 없는 경로만 준다.
    같은 이름의 파일이 이미 있으면 받지 않고 그대로 둔다.

    반환값: (실제 저장 경로, 새로 받았는지 여부)
    """
    with get_session().get(url, timeout=TIMEOUT, stream=True) as resp:
        resp.raise_for_status()
        extension = _extension_for(resp.headers.get("Content-Type"), url, is_video)
        target = dest_without_extension.with_name(dest_without_extension.name + extension)

        if target.exists():
            return target, False

        target.parent.mkdir(parents=True, exist_ok=True)
        # 중간에 끊겨도 반쪽짜리 파일이 남지 않도록 임시 이름으로 받은 뒤 옮긴다
        temp = target.with_name(target.name + ".part")
        try:
            with temp.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
            temp.replace(target)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    return target, True
