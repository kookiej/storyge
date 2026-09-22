"""웹 버전의 파일명 규칙.

데스크톱(exe)은 `YYMMDD @계정 #N` 으로 고정이고 그 규칙은 naming.py 에 있다.
**여기는 웹 전용이고 naming.py 를 건드리지 않는다.**

웹의 기본값은 템플릿이 아니라 **CDN 원본 파일명**(`item.orig_name`)이다.
수집 사이트가 주는 주소에 이미 고유한 이름이 들어 있어 번호를 매길 필요가 없다.
사용자가 '이름 형식 지정'을 켜면 그때부터 아래 토큰으로 조립한 템플릿을 쓴다.

여기서 만드는 것은 확장자를 뺀 '스템'이다. 확장자는 net.download_to 가
응답의 Content-Type 을 보고 붙인다.

## 토큰

    {orig}                원본 이름            481234567_1122334455_n
    {date}                = {yy}{mm}{dd}       260830
    {yyyy} {yy} {mm} {dd} 년 / 년2 / 월 / 일   2026 26 08 30
    {time}                = {HH}{MM}           2105
    {HH} {MM} {SS}        시(24) / 분 / 초     21 05 44
    {account} {@account}  계정                 abc / @abc
    {n} {nn}              묶음 안 순번         3 / 03
    {type}                video / photo

대소문자를 구분한다 ({mm} 는 월, {MM} 는 분).

## 선택 구간 [...]

대괄호로 감싼 부분은 '새로 받는 것이 하나뿐이고 저장 폴더에 같은 묶음 파일도 없을 때'
통째로 빠진다. 데스크톱의 '한 개뿐이면 #번호를 안 붙인다' 규칙과 같다.

    "{date} @{account}[ #{n}]"  ->  260830 @abc          (하나뿐일 때)
                                    260830 @abc #1, #2   (여럿일 때)
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union

from .i18n import t
from .model import StoryItemInfo

# 데스크톱과 같은 모양을 원할 때 쓰라고 화면에 버튼으로 내주는 값.
# 설정의 기본값은 이것이 아니라 빈 문자열(= CDN 원본 이름)이다.
SUGGESTED_TEMPLATE = "{date} @{account}[ #{n}]"

# 번호가 들어갈 자리를 표시하는 임시 문자. 파일명에 절대 들어갈 수 없는 값이라야 한다.
_SENTINEL = "\x00N\x00"

_NUMBER_TOKENS = ("n", "nn")

# 윈도우에서 파일명에 못 쓰는 글자. 경로 탈출(`..\`)도 여기서 같이 막힌다.
_ILLEGAL = set('\\/:*?"<>|')

# 윈도우가 파일 이름으로 받아 주지 않는 장치 이름
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
    f"LPT{i}" for i in range(1, 10)
}

# 경로 길이 제한에 걸리지 않도록 넉넉히 잡은 상한
MAX_STEM = 150

# glob 에서 특별한 뜻을 갖는 글자. 접두사에 이런 게 섞이면 glob 을 포기하고 전부 훑는다.
_GLOB_MAGIC = set("*?[]")


class TemplateError(ValueError):
    """템플릿 자체가 말이 안 될 때. validate() 가 사람이 읽을 문장으로 바꿔 준다."""


# 화면의 토큰 칩을 만드는 데 쓰는 목록. 서버와 UI 가 같은 것을 보게 여기 하나만 둔다.
# (토큰, 묶음, 설명)
#
# 이 문구들은 i18n 의 **키가 된다** (한국어 원문이 곧 키다). 그래서 '시간', '일',
# '계정' 같은 짧고 흔한 낱말을 쓰면 안 된다 — exe 의 예약 창이 이미 '시간'을
# hours, '일'을 days 로 쓰고 있어서 조용히 덮어써 버린다.
# 짧게 줄이고 싶더라도 반드시 다른 곳과 겹치지 않는 문구로 둘 것.
# 같은 묶음끼리 붙여 둔다 — 화면이 묶음마다 한 칸으로 그리므로 흩어져 있으면
# 같은 이름의 묶음이 두 번 나온다.
TOKENS = (
    ("{date}", "날짜", "YYMMDD"),
    ("{yyyy}", "날짜", "년 (네 자리)"),
    ("{yy}", "날짜", "년 (두 자리)"),
    ("{mm}", "날짜", "월 (두 자리)"),
    ("{dd}", "날짜", "일 (두 자리)"),
    ("{time}", "시각", "HHMM"),
    ("{HH}", "시각", "시 (24시간)"),
    ("{MM}", "시각", "분 (두 자리)"),
    ("{SS}", "시각", "초 (두 자리)"),
    ("{account}", "계정 이름", "계정 아이디"),
    ("{@account}", "계정 이름", "@계정 아이디"),
    ("[#{n}]", "번호", "번호 (하나뿐이면 생략)"),
    ("{n}", "번호", "번호 (항상)"),
    ("{nn}", "번호", "번호 (항상, 두 자리)"),
    ("{orig}", "기타", "원본 이름"),
    ("{type}", "기타", "영상 또는 사진"),
)

# 알아듣는 토큰 이름. TOKENS 에서 뽑아내려 하지 말 것 — "[ #{n}]" 같은 항목이 섞여 있어
# 문자열을 벗겨 내는 방식으로는 제대로 나오지 않는다.
_KNOWN = {
    "orig", "date", "yyyy", "yy", "mm", "dd",
    "time", "HH", "MM", "SS",
    "account", "@account", "n", "nn", "type",
}


# ---------------------------------------------------------------- 기본 이름

def fallback_stem(item: StoryItemInfo) -> str:
    """원본 이름을 못 구했을 때 쓰는 이름. mediaid 가 있어 절대 겹치지 않는다."""
    return f"{item.taken_at:%y%m%d} @{item.account} {item.mediaid}"


def default_stem(item: StoryItemInfo) -> str:
    """템플릿을 쓰지 않을 때의 이름 — CDN 원본 그대로."""
    name = _sanitize(item.orig_name)
    return name or fallback_stem(item)


# ---------------------------------------------------------------- 템플릿 해석

def _parse(template: str) -> list:
    """템플릿을 노드 목록으로 바꾼다.

    노드는 ("lit", 글자) / ("tok", 이름) / ("opt", 하위노드목록) 셋 중 하나다.
    """
    root: list = []
    stack: list[list] = [root]
    buf: list[str] = []

    def flush() -> None:
        if buf:
            stack[-1].append(("lit", "".join(buf)))
            buf.clear()

    index = 0
    while index < len(template):
        char = template[index]
        if char == "{":
            end = template.find("}", index)
            if end == -1:
                raise TemplateError(t("'{' 를 닫는 '}' 가 없습니다."))
            name = template[index + 1:end]
            if not name or "{" in name:
                raise TemplateError(t("토큰 이름이 비어 있거나 잘못됐습니다."))
            flush()
            stack[-1].append(("tok", name))
            index = end + 1
        elif char == "}":
            raise TemplateError(t("짝이 없는 '}' 가 있습니다."))
        elif char == "[":
            if len(stack) > 1:
                raise TemplateError(t("'[' 안에 '[' 를 또 쓸 수 없습니다."))
            flush()
            inner: list = []
            stack[-1].append(("opt", inner))
            stack.append(inner)
            index += 1
        elif char == "]":
            if len(stack) == 1:
                raise TemplateError(t("짝이 없는 ']' 가 있습니다."))
            flush()
            stack.pop()
            index += 1
        else:
            buf.append(char)
            index += 1

    flush()
    if len(stack) > 1:
        raise TemplateError(t("'[' 를 닫는 ']' 가 없습니다."))
    return root


def _each(nodes: list, optional: bool = False):
    """모든 노드를 (종류, 값, 선택구간안인지) 로 펼친다."""
    for kind, value in nodes:
        if kind == "opt":
            yield from _each(value, True)
        else:
            yield kind, value, optional


def _number_tokens(nodes: list) -> list[tuple[str, bool]]:
    """(번호 토큰 이름, 선택 구간 안에 있는지) 목록."""
    return [
        (value, inside)
        for kind, value, inside in _each(nodes)
        if kind == "tok" and value in _NUMBER_TOKENS
    ]


# ---------------------------------------------------------------- 렌더

Number = Union[int, str]


def _token_value(name: str, item: StoryItemInfo, number: Number) -> str:
    when = item.taken_at
    if name == "orig":
        return item.orig_name or fallback_stem(item)
    if name == "date":
        return f"{when:%y%m%d}"
    if name == "yyyy":
        return f"{when:%Y}"
    if name == "yy":
        return f"{when:%y}"
    if name == "mm":
        return f"{when:%m}"
    if name == "dd":
        return f"{when:%d}"
    if name == "time":
        return f"{when:%H%M}"
    if name == "HH":
        return f"{when:%H}"
    if name == "MM":
        return f"{when:%M}"
    if name == "SS":
        return f"{when:%S}"
    if name == "account":
        return item.account
    if name == "@account":
        return f"@{item.account}"
    if name == "type":
        return "video" if item.is_video else "photo"
    if name in _NUMBER_TOKENS:
        # 자리를 재는 중이면 (센티널) 숫자로 만들지 않고 그대로 흘려보낸다
        if isinstance(number, str):
            return number
        return f"{number:02d}" if name == "nn" else str(number)
    raise TemplateError(t("모르는 토큰입니다: {token}", token="{" + name + "}"))


def _render(nodes: list, item: StoryItemInfo, number: Number, drop_optional: bool) -> str:
    out: list[str] = []
    for kind, value in nodes:
        if kind == "lit":
            out.append(value)
        elif kind == "tok":
            out.append(_token_value(value, item, number))
        elif not drop_optional:
            out.append(_render(value, item, number, drop_optional))
    return "".join(out)


def _sanitize(stem: str) -> str:
    """파일명으로 쓸 수 있는 꼴로 다듬는다. 도저히 못 쓰면 빈 문자열."""
    text = "".join(ch for ch in stem if ch not in _ILLEGAL and ch >= " ")
    # 윈도우는 끝의 공백과 마침표를 말없이 지운다. 우리가 먼저 지워 놓아야
    # '만든 이름'과 '실제 파일 이름'이 어긋나지 않는다.
    text = text.strip().rstrip(". ")
    if not text or text in {".", ".."} or text.upper() in _RESERVED:
        return ""
    return text[:MAX_STEM]


# ---------------------------------------------------------------- 기존 번호 잇기

def _existing_max(
    save_dir: Optional[Path], prefix: str, suffix: str, bare: Optional[str]
) -> int:
    """저장 폴더에 이미 있는 같은 묶음 파일 중 가장 큰 번호. 없으면 0.

    naming._highest_existing_number 를 임의 템플릿으로 일반화한 것이다.
    번호가 빠진 파일(bare) 하나는 1번을 차지한 것으로 본다.
    save_dir 이 None 이면 폴더를 보지 않는다 (미리보기).
    """
    if save_dir is None or not save_dir.is_dir():
        return 0

    numbered = re.compile(rf"^{re.escape(prefix)}(\d+){re.escape(suffix)}$")

    # glob 은 접두사로 후보를 좁히려고 쓸 뿐이다. 번호 없는 파일까지 걸리도록
    # prefix 와 bare 의 공통 부분을 쓴다 ("260830 @abc #" 와 "260830 @abc" -> "260830 @abc").
    head = os.path.commonprefix([prefix, bare]) if bare is not None else prefix
    pattern = f"{head}*" if head and not (_GLOB_MAGIC & set(head)) else "*"

    highest = 0
    for path in save_dir.glob(pattern):
        if not path.is_file():
            continue
        stem = path.stem
        if bare is not None and stem == bare:
            highest = max(highest, 1)
            continue
        match = numbered.match(stem)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def _deduplicate(names: dict[int, str]) -> dict[int, str]:
    """번호 토큰이 없는 템플릿에서 이름이 겹칠 때 뒤에 ' #2', ' #3' 을 붙인다.

    안 그러면 두 번째 항목이 저장되지 않고 '이미 있음' 으로 조용히 넘어간다.
    """
    seen: dict[str, int] = {}
    fixed: dict[int, str] = {}
    for mediaid, stem in names.items():
        count = seen.get(stem, 0) + 1
        seen[stem] = count
        fixed[mediaid] = stem if count == 1 else f"{stem} #{count}"
    return fixed


# ---------------------------------------------------------------- 공개 API

def build_names(
    items: list[StoryItemInfo],
    save_dir: Optional[Path],
    template: Optional[str] = None,
) -> dict[int, str]:
    """mediaid -> 확장자 없는 파일명.

    template 이 비어 있으면 CDN 원본 이름을 그대로 쓴다.
    save_dir 이 None 이면 기존 파일을 보지 않는다 (미리보기용).
    템플릿이 망가져 있으면 예외를 내지 않고 원본 이름으로 물러선다 — 설정이
    깨졌다고 저장 자체가 실패하면 사용자가 손쓸 방법이 없다. (설정 화면이
    validate() 로 미리 막으므로 여기까지 오는 일은 드물다.)
    """
    text = (template or "").strip()
    if not text:
        return {item.mediaid: default_stem(item) for item in items}

    try:
        nodes = _parse(text)
        has_optional_number = any(inside for _, inside in _number_tokens(nodes))
        # 토큰 이름이 맞는지 여기서 한 번 확인해 둔다 (아래 묶음 계산 전에 터지도록)
        if items:
            _render(nodes, items[0], _SENTINEL, drop_optional=False)
    except TemplateError:
        return {item.mediaid: default_stem(item) for item in items}

    # 번호 자리를 기준으로 (앞부분, 뒷부분) 을 가른다. 한 번 렌더하면 {n} 이
    # 맨 앞이든 중간이든 양쪽에 글자가 붙든 전부 커버된다.
    groups: dict[tuple[str, Optional[str]], list[StoryItemInfo]] = defaultdict(list)
    parts: dict[int, tuple[str, Optional[str], Optional[str]]] = {}
    for item in items:
        rendered = _render(nodes, item, _SENTINEL, drop_optional=False)
        prefix, found, suffix = rendered.partition(_SENTINEL)
        if not found:
            prefix, suffix = rendered, None
        bare = _render(nodes, item, 1, drop_optional=True) if has_optional_number else None
        parts[item.mediaid] = (prefix, suffix, bare)
        groups[(prefix, suffix)].append(item)

    names: dict[int, str] = {}
    for (prefix, suffix), group in groups.items():
        group.sort(key=lambda i: i.taken_at)
        bare = parts[group[0].mediaid][2]

        if suffix is None:
            # 번호 토큰이 없다 — 묶음 전체가 같은 이름이 된다. _deduplicate 가 뒤처리한다.
            for item in group:
                names[item.mediaid] = _render(nodes, item, 1, drop_optional=False)
            continue

        start = _existing_max(save_dir, prefix, suffix, bare)

        # 새로 받는 게 딱 하나이고 기존 파일도 없을 때만 선택 구간을 뺀다
        if start == 0 and len(group) == 1 and bare is not None:
            names[group[0].mediaid] = bare
            continue

        for offset, item in enumerate(group, start=start + 1):
            names[item.mediaid] = _render(nodes, item, offset, drop_optional=False)

    names = _deduplicate(names)

    # 마지막 안전장치. 설정이 어떻게 망가져도 save_dir 밖으로는 못 쓴다.
    by_id = {item.mediaid: item for item in items}
    return {
        mediaid: (_sanitize(stem) or default_stem(by_id[mediaid]))
        for mediaid, stem in names.items()
    }


def validate(template: str) -> tuple[list[str], list[str]]:
    """(막아야 할 문제, 알려만 줄 문제). 앞이 비어 있으면 쓸 수 있는 템플릿이다."""
    errors: list[str] = []
    warnings: list[str] = []

    text = (template or "").strip()
    if not text:
        return [t("이름 형식이 비어 있습니다.")], warnings

    try:
        nodes = _parse(text)
    except TemplateError as err:
        return [str(err)], warnings

    for kind, value, _ in _each(nodes):
        if kind == "tok":
            if value not in _KNOWN:
                errors.append(t("모르는 토큰입니다: {token}", token="{" + value + "}"))
        else:
            bad = sorted(_ILLEGAL & set(value))
            if bad:
                errors.append(t(
                    "파일명에 쓸 수 없는 글자가 있습니다: {chars}",
                    chars=" ".join(bad),
                ))

    numbers = _number_tokens(nodes)
    if len(numbers) > 1:
        errors.append(t("번호 토큰은 하나만 쓸 수 있습니다."))
    if not numbers:
        warnings.append(t(
            "번호 토큰이 없어 같은 이름이 여러 개 나올 수 있습니다. "
            "그럴 때는 뒤에 번호가 자동으로 붙습니다."
        ))

    # 선택 구간은 '번호를 감추는' 장치다. 번호가 없으면 아무 일도 안 한다.
    for kind, value in nodes:
        if kind == "opt" and not _number_tokens(value):
            errors.append(t("[ ] 안에는 번호 토큰이 있어야 합니다."))

    if errors:
        return errors, warnings

    # 실제로 그려 봐야 알 수 있는 문제들
    for sample in sample_items():
        try:
            stem = _render(nodes, sample, 1, drop_optional=False)
        except TemplateError as err:
            errors.append(str(err))
            break
        if _sanitize(stem) != stem:
            if len(stem) > MAX_STEM:
                errors.append(t("이름이 너무 깁니다 ({limit}자 이내).", limit=MAX_STEM))
            elif stem.upper() in _RESERVED:
                errors.append(t("윈도우가 예약해 둔 이름입니다: {name}", name=stem))
            else:
                errors.append(t("이름 앞뒤의 공백이나 끝의 마침표는 쓸 수 없습니다."))
            break

    return errors, warnings


def sample_items() -> list[StoryItemInfo]:
    """미리보기용 예시 세 건 — 사진 하나, 영상 하나, 같은 묶음의 두 번째."""
    base = datetime.now().replace(microsecond=0)
    return [
        StoryItemInfo(
            account="storyge", mediaid=1, taken_at=base - timedelta(hours=3),
            is_video=False, thumb_url="", media_url="",
            orig_name="481234567_1122334455_n",
        ),
        StoryItemInfo(
            account="storyge", mediaid=2, taken_at=base - timedelta(hours=2),
            is_video=True, thumb_url="", media_url="",
            orig_name="481234568_1122334456_n",
        ),
        StoryItemInfo(
            account="friend", mediaid=3, taken_at=base - timedelta(hours=1),
            is_video=False, thumb_url="", media_url="",
            orig_name="481234569_1122334457_n",
        ),
    ]


def preview_label(item: StoryItemInfo) -> str:
    """미리보기 줄 왼쪽의 설명.

    계정 이름은 넣지 않는다 — 줄 전체가 파일명처럼 읽혀서 '기본 이름에 계정이
    들어간다' 고 오해하게 된다. 파일명에는 원래 계정이 안 들어간다.
    web/api.py 도 이걸 쓴다. 두 벌로 두면 한쪽만 고치게 된다.
    """
    return "영상" if item.is_video else "사진"


def preview(template: str, items: Optional[list[StoryItemInfo]] = None) -> list[dict]:
    """설정 화면에 보여 줄 미리보기 줄들.

    저장 폴더는 보지 않는다 (미리보기가 폴더 상태에 따라 흔들리면 더 헷갈린다).
    실제 번호는 저장할 때 기존 파일 뒤로 이어 매긴다.
    """
    samples = list(items or [])[:3] or sample_items()
    names = build_names(samples, None, template)   # None = 기존 파일을 보지 않는다
    rows = []
    for item in samples:
        rows.append({
            "label": preview_label(item),
            "name": names.get(item.mediaid, ""),
            "ext": ".mp4" if item.is_video else ".jpg",
        })
    return rows
