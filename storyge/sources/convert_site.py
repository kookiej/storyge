"""fastdl.app / igram.world 공용 구현.

두 사이트는 **같은 백엔드**다. 확인한 것:

  - 둘 다 `POST /api/convert` 하나로 동작하고 `/api/captcha`, `/api/cf`,
    `/get_country_code` 도 똑같이 갖고 있다.
  - 둘 다 첫 주소에서 `/en5IW`, `/en2` 같은 **매번 바뀌는 경로 세그먼트**로
    넘긴다. 그래서 세그먼트를 절대 하드코딩하지 않고 최종 주소에서 읽는다.
  - 둘 다 라라벨이라 `XSRF-TOKEN` 쿠키를 심고 `X-XSRF-TOKEN` 헤더를 받는다.
  - 둘 다 요청에 `x-token` 서명을 요구한다. 이 값은 사이트의 app.js
    (800KB~1.2MB, 난독화) 안에서 만들어진다. **이것이 지금 비어 있는 자리다**
    (_sign_request 참고).

그래서 사이트별 파일(fastdl.py / igram.py)은 주소와 이름만 갖는다.
고쳐야 할 곳이 한 벌뿐이라, 한쪽이 바뀌면 보통 양쪽이 같이 고쳐진다.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional
from urllib.parse import urlsplit

from ..i18n import t
from ..model import StoryItemInfo
from . import SiteSource, common
from .common import AccountNotFound, AccountPrivate, SourceBlocked

# 이 값을 1 로 두고 한 번 돌리면 응답 원문이 data\source_last.txt 에 떨어진다.
# 사이트가 바뀌었을 때 _parse_payload 를 고치는 출발점이다.
DEBUG_ENV = "STORYGE_DEBUG_SOURCE"


def story_url(account: str) -> str:
    """이 사이트들은 사용자 이름이 아니라 주소를 받는다."""
    return f"https://www.instagram.com/stories/{account}/"


# ==========================================================================
#  여기부터가 사이트의 응답을 읽는 유일한 자리다.
#  사이트가 바뀌면 이 함수 하나만 고치면 된다. 다른 곳은 손대지 말 것.
#
#  고치는 법:
#    1) set STORYGE_DEBUG_SOURCE=1 로 한 번 돌려 data\source_last.txt 를 받는다.
#    2) 그 파일을 픽스처로 넣고 t_parse.py 가 초록이 될 때까지 여기만 고친다.
#
#  StoryItemInfo 를 만들지 말 것. 평범한 dict 만 돌려주면 common.make_item 이
#  나머지(식별자 합성, 시각 해석, 원본 이름)를 처리한다.
# ==========================================================================
_MEDIA_RE = re.compile(r'https?://[^\s"\'<>]+?(?:cdninstagram\.com|fbcdn\.net)[^\s"\'<>]*')
_AGE_RE = re.compile(r'(\d+\s*(?:시간|분|초|일|hours?|minutes?|seconds?|days?|[hmsd])\s*(?:ago|전)?)',
                     re.IGNORECASE)


def _walk(node):
    """중첩된 응답 어디에 미디어가 들어 있든 찾아낸다."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _parse_payload(body: str) -> list[dict]:
    """응답 원문 -> [{"media_url", "thumb_url", "is_video", "taken_at", "age_text"}, ...]"""
    entries: list[dict] = []
    seen: set[str] = set()

    # 1) JSON 이면 구조를 따라 걷는다
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        data = None

    if data is not None:
        for node in _walk(data):
            url = node.get("url") or node.get("download_url") or node.get("src")
            if not isinstance(url, str) or "instagram" not in url and "fbcdn" not in url:
                continue
            path = urlsplit(url).path
            if path in seen:
                continue
            seen.add(path)
            entries.append({
                "media_url": url,
                "thumb_url": node.get("thumb") or node.get("thumbnail") or node.get("preview"),
                "is_video": bool(node.get("is_video")
                                 or str(node.get("type", "")).lower() in ("video", "mp4")
                                 or path.lower().endswith(".mp4")),
                "taken_at": (node.get("taken_at") or node.get("taken_at_timestamp")
                             or node.get("created_at") or node.get("timestamp")),
                "age_text": node.get("age") or node.get("time") or node.get("posted"),
            })

    # 2) JSON 에서 못 찾았으면 본문에서 CDN 주소를 긁는다
    if not entries:
        ages = _AGE_RE.findall(body)
        for index, url in enumerate(_MEDIA_RE.findall(body)):
            path = urlsplit(url).path
            if path in seen:
                continue
            seen.add(path)
            entries.append({
                "media_url": url,
                "thumb_url": None,
                "is_video": path.lower().endswith(".mp4"),
                "taken_at": None,
                "age_text": ages[index] if index < len(ages) else None,
            })

    return entries
# ==========================================================================
#  고치기 쉬운 자리 끝
# ==========================================================================


class ConvertSite(SiteSource):
    """fastdl / igram 공용 동작. 하위 클래스는 host / id / label 만 정한다."""

    host = ""
    id = ""
    label = ""

    def __init__(self) -> None:
        self.http = None
        self.landing = ""
        self.segment = ""

    # --- 열기 -------------------------------------------------------

    def open(self) -> None:
        self.http = common.new_http()
        try:
            resp = self.http.get(f"https://{self.host}/", timeout=common.TIMEOUT,
                                 allow_redirects=True)
        except Exception as err:  # noqa: BLE001
            raise SourceBlocked(str(err) or type(err).__name__) from err

        if common.looks_blocked(resp.status_code, resp.text):
            raise SourceBlocked(t("자동 접속이 막혀 있습니다"))

        # 경로 세그먼트(/en5IW, /en2)는 매번 바뀐다. 하드코딩하지 않고 여기서 읽는다.
        self.landing = resp.url
        parts = [p for p in urlsplit(resp.url).path.split("/") if p]
        self.segment = parts[0] if parts else ""

    def close(self) -> None:
        if self.http is not None:
            try:
                self.http.close()
            finally:
                self.http = None

    # --- 요청 -------------------------------------------------------

    def _headers(self) -> dict:
        xsrf = ""
        if self.http is not None:
            from urllib.parse import unquote
            xsrf = unquote(self.http.cookies.get("XSRF-TOKEN") or "")
        headers = {
            "Referer": self.landing or f"https://{self.host}/",
            "Origin": f"https://{self.host}",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        }
        if xsrf:
            headers["X-XSRF-TOKEN"] = xsrf
        return headers

    # ----------------------------------------------------------------
    #  아직 채우지 못한 자리.
    #
    #  /api/convert 는 요청을 받기 전에 x-token 서명을 확인한다. 서명이 없으면
    #  URL 을 읽지도 않고 {"code": "URL_IS_EMPTY"} 로 돌려보낸다 (JSON 으로 보내든
    #  폼으로 보내든 같다 — 확인함).
    #
    #  서명은 사이트의 /js/app.js 안에서 만들어진다. 채우는 법:
    #    1) 크롬 devtools > Network > Fetch/XHR 만 필터
    #    2) 그 사이트에서 공개 계정 하나를 실제로 조회
    #    3) /api/convert 요청을 'Copy as cURL' 로 복사
    #    4) 그 요청의 헤더(x-token 등)와 본문 필드를 아래 두 함수에 옮겨 적는다
    #       — 값이 시각이나 주소에서 계산된다면 그 계산까지 옮겨야 한다
    #    5) t_parse.py 를 픽스처로 돌려 _parse_payload 가 맞는지 확인
    #
    #  이 함수가 None 을 돌려주는 동안에는 이 사이트를 건너뛴다 (SourceBlocked).
    #  그래야 '되는 척하다 빈 결과' 대신 무엇이 문제인지 화면에 보인다.
    # ----------------------------------------------------------------
    def _sign_request(self, target: str) -> Optional[dict]:
        """(headers, data) 로 합칠 서명 값. 아직 모르므로 None."""
        return None

    def _convert(self, target: str) -> str:
        signed = self._sign_request(target)
        if signed is None:
            raise SourceBlocked(t(
                "이 사이트는 서명된 요청만 받습니다. 아직 지원하지 않습니다."
            ))

        headers = self._headers()
        headers.update(signed.get("headers", {}))
        payload = {"url": target}
        payload.update(signed.get("data", {}))

        try:
            resp = self.http.post(
                f"https://{self.host}/api/convert",
                data=payload, headers=headers, timeout=common.TIMEOUT,
            )
        except Exception as err:  # noqa: BLE001
            raise SourceBlocked(str(err) or type(err).__name__) from err

        body = resp.text
        if os.environ.get(DEBUG_ENV):
            self._dump(body)
        if common.looks_blocked(resp.status_code, body):
            raise SourceBlocked(t("자동 접속이 막혀 있습니다"))
        return body

    @staticmethod
    def _dump(body: str) -> None:
        """응답 원문을 남긴다. _parse_payload 를 고칠 때의 출발점."""
        from .. import paths
        try:
            paths.ensure_data_dir()
            (paths.DATA_DIR / "source_last.txt").write_text(body, encoding="utf-8")
        except OSError:
            pass

    # --- 계정 하나 ---------------------------------------------------

    def fetch_account(self, account: str) -> list[StoryItemInfo]:
        body = self._convert(story_url(account))
        self._raise_for_code(account, body)

        items = []
        for entry in _parse_payload(body):
            made = common.make_item(account, entry, self.id)
            if made is not None:
                items.append(made)
        return items

    @staticmethod
    def _raise_for_code(account: str, body: str) -> None:
        """응답이 알려 주는 문제를 우리 예외로 바꾼다."""
        lowered = body[:2000].lower()
        if "private" in lowered:
            raise AccountPrivate()
        if "not_found" in lowered or "not found" in lowered or "no_user" in lowered:
            raise AccountNotFound()
        if "captcha" in lowered or "rate" in lowered and "limit" in lowered:
            raise SourceBlocked(t("자동 접속이 막혀 있습니다"))
