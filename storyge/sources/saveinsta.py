"""saveinsta.to.

fastdl / igram 과 **다른 백엔드**다. 저쪽은 /api/convert 가 클라이언트에서 계산한
x-token 서명을 요구해서 파이썬으로는 부를 수 없는데(convert_site.py 참고),
여기는 **토큰을 전부 서버가 내려준다.** 그래서 실제로 동작한다.

흐름 (확인함):

  1. GET  /en1/story            랜딩. 본문 스크립트에서 k_token / k_exp 를 긁는다.
  2. POST /api/userverify       {"url": 대상} -> {"token": ...}  (계정마다 한 번)
  3. POST /api/ajaxSearch       위 셋 + q/t/lang/v -> {"status":"ok", "data": "<html>"}

응답의 data 는 HTML 조각이고, 항목 하나가 <li> 하나다. 미디어 주소는 snapcdn 의
JWT 안에 들어 있다 — **토큰을 풀어 진짜 CDN 주소를 꺼내 쓴다.** 그들의 프록시로
내려받으면 영상 트래픽을 통째로 남에게 떠넘기게 되고, 우리 파일명 규칙도
CDN 경로에서 원본 이름을 뽑아 쓰기 때문이다.

**게시 시각은 주지 않는다.** 상대 시간 표시도 없어서 이 사이트에서 온 항목은
time_basis 가 "fetch" 가 된다 (화면에 '~' 로 표시된다).
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
from urllib.parse import urlsplit

from ..i18n import t
from ..model import StoryItemInfo
from . import SiteSource, common
from .common import AccountNotFound, SourceBlocked, SourceError

HOST = "saveinsta.to"
LANDING = f"https://{HOST}/en1/story"
DEBUG_ENV = "STORYGE_DEBUG_SOURCE"


def story_url(account: str) -> str:
    """이 사이트가 받는 입력 형태."""
    return f"https://www.instagram.com/stories/{account}"


def _claim(token: str) -> dict:
    """JWT 의 payload 를 읽는다. 서명은 확인하지 않는다 — 우리가 검증할 대상이 아니고,
    안에 든 주소를 꺼내려는 것뿐이다."""
    parts = token.split(".")
    payload = parts[1] if len(parts) > 2 else parts[-1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return {}


def _real_url(token: str) -> str:
    """토큰 안의 진짜 CDN 주소. 못 읽으면 빈 문자열."""
    found = _claim(token).get("url")
    return found if isinstance(found, str) else ""


# ==========================================================================
#  여기부터가 saveinsta 의 응답을 읽는 유일한 자리다.
#  사이트가 바뀌면 이 함수 하나만 고치면 된다. 다른 곳은 손대지 말 것.
#
#  고치는 법:
#    1) set STORYGE_DEBUG_SOURCE=1 로 한 번 돌려 data\source_last.txt 를 받는다.
#    2) 그 파일을 픽스처로 넣고 t_saveinsta.py 가 초록이 될 때까지 여기만 고친다.
#
#  StoryItemInfo 를 만들지 말 것. 평범한 dict 만 돌려주면 common.make_item 이
#  나머지(식별자 합성, 시각 해석, 원본 이름)를 처리한다.
# ==========================================================================

# 항목 하나가 <li> 하나다.
_ITEM_RE = re.compile(r"<li\b.*?</li>", re.DOTALL | re.IGNORECASE)
# 미리보기 이미지 (i.snapcdn.app/photo?token=...)
_THUMB_RE = re.compile(r'<img[^>]+src="https://i\.snapcdn\.app/[^"?]*\?token=([\w.\-]+)"',
                       re.IGNORECASE)
# 내려받기 단추. title 로 썸네일용인지 원본용인지 가른다.
_LINK_RE = re.compile(r'<a\b[^>]*href="https://dl\.snapcdn\.app/[^"?]*\?token=([\w.\-]+)"[^>]*>',
                      re.IGNORECASE)
_TITLE_RE = re.compile(r'title="([^"]*)"', re.IGNORECASE)


def _parse_payload(html: str) -> list[dict]:
    """응답의 data(HTML) -> [{"media_url", "thumb_url", "is_video"}, ...]"""
    entries: list[dict] = []
    seen: set[str] = set()

    for chunk in _ITEM_RE.findall(html or ""):
        thumb_token = _THUMB_RE.search(chunk)
        thumb = _real_url(thumb_token.group(1)) if thumb_token else ""

        media = ""
        for match in _LINK_RE.finditer(chunk):
            tag = match.group(0)
            title = (_TITLE_RE.search(tag) or [None, ""])[1].lower()
            # 'Download Thumbnail' 은 미리보기용이다. 원본은 Video / Image 쪽.
            if "thumbnail" in title:
                continue
            media = _real_url(match.group(1))
            if media:
                break

        # 원본 단추를 못 찾으면 미리보기라도 쓴다 (사진은 둘이 같은 경우가 있다)
        media = media or thumb
        if not media:
            continue

        path = urlsplit(media).path
        if path in seen:
            continue
        seen.add(path)

        entries.append({
            "media_url": media,
            "thumb_url": thumb or media,
            # 아이콘 종류가 가장 확실하고, 확장자는 보조로 본다
            "is_video": ("icon-dlvideo" in chunk) or path.lower().endswith(".mp4"),
            # 이 사이트는 게시 시각을 주지 않는다
            "taken_at": None,
            "age_text": None,
        })

    return entries
# ==========================================================================
#  고치기 쉬운 자리 끝
# ==========================================================================


class SaveInsta(SiteSource):
    id = "saveinsta"
    label = "saveinsta.to"

    def __init__(self) -> None:
        self.http = None
        self.k_token = ""
        self.k_exp = ""

    # --- 열기 -------------------------------------------------------

    def open(self) -> None:
        self.http = common.new_http()
        try:
            resp = self.http.get(LANDING, timeout=common.TIMEOUT, allow_redirects=True)
        except Exception as err:  # noqa: BLE001
            raise SourceBlocked(str(err) or type(err).__name__) from err

        if common.looks_blocked(resp.status_code, resp.text):
            raise SourceBlocked(t("자동 접속이 막혀 있습니다"))

        self.landing = resp.url
        for name in ("k_token", "k_exp"):
            found = re.search(rf'{name}\s*=\s*"([^"]+)"', resp.text)
            setattr(self, name, found.group(1) if found else "")
        if not self.k_token:
            # 토큰을 못 구하면 조회가 통째로 거절된다. 계정마다 두드리지 말고 여기서 접는다.
            raise SourceBlocked(t("자동 접속이 막혀 있습니다"))

    def close(self) -> None:
        if self.http is not None:
            try:
                self.http.close()
            finally:
                self.http = None

    # --- 요청 -------------------------------------------------------

    def _headers(self) -> dict:
        return {
            "Referer": getattr(self, "landing", LANDING),
            "Origin": f"https://{HOST}",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _verify(self, target: str) -> str:
        """계정마다 한 번. 대상 주소가 토큰 안에 박히므로 재사용할 수 없다."""
        try:
            resp = self.http.post(f"https://{HOST}/api/userverify",
                                  data={"url": target}, headers=self._headers(),
                                  timeout=common.TIMEOUT)
            return str((resp.json() or {}).get("token") or "")
        except Exception:  # noqa: BLE001 - 없으면 없는 대로 조회를 시도한다
            return ""

    def _search(self, target: str) -> dict:
        payload = {
            "k_exp": self.k_exp,
            "k_token": self.k_token,
            "q": target,
            "t": "media",
            "lang": "en",
            "v": "v2",
        }
        cftoken = self._verify(target)
        if cftoken:
            payload["cftoken"] = cftoken

        try:
            resp = self.http.post(f"https://{HOST}/api/ajaxSearch", data=payload,
                                  headers=self._headers(), timeout=common.TIMEOUT)
        except Exception as err:  # noqa: BLE001
            raise SourceBlocked(str(err) or type(err).__name__) from err

        body = resp.text
        if os.environ.get(DEBUG_ENV):
            self._dump(body)
        if common.looks_blocked(resp.status_code, body):
            raise SourceBlocked(t("자동 접속이 막혀 있습니다"))
        try:
            return resp.json() or {}
        except ValueError as err:
            raise SourceError(t("응답을 읽지 못했습니다.")) from err

    @staticmethod
    def _dump(body: str) -> None:
        from .. import paths
        try:
            paths.ensure_data_dir()
            (paths.DATA_DIR / "source_last.txt").write_text(body, encoding="utf-8")
        except OSError:
            pass

    # --- 계정 하나 ---------------------------------------------------

    def fetch_account(self, account: str) -> list[StoryItemInfo]:
        data = self._search(story_url(account))

        if str(data.get("status") or "").lower() not in ("ok", "success", ""):
            raise SourceError(t("응답을 읽지 못했습니다."))

        html = data.get("data") or ""
        if not html:
            # 안내 문구가 오지만 뜻이 뭉뚱그려져 있다. 실제로 확인해 보니
            # **올라온 스토리가 없을 때도** 'Video is private' 이라고 답한다.
            # 그래서 비공개로 단정하지 않는다 — 스토리가 없는 것은 문제가 아니므로
            # 아무 말도 남기지 않고 빈 목록으로 돌려준다.
            message = re.sub(r"<[^>]+>", "", str(data.get("mess") or "")).lower()
            if "not supported" in message:
                raise AccountNotFound()
            return []

        items = []
        for entry in _parse_payload(html):
            made = common.make_item(account, entry, self.id)
            if made is not None:
                items.append(made)
        return items
