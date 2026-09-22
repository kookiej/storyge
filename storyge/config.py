"""계정 목록과 저장 폴더 설정을 data/config.json 에 읽고 쓴다."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from . import paths

# 반복 방식. 창의 콤보 상자 순서와 같다.
SCHEDULE_MODES = ("daily", "days", "hours", "custom")

# 웹 버전이 스토리를 가져올 곳. "auto" 는 순서대로 써 보고 막히면 다음으로 넘어간다.
# 화면에는 이 선택지가 없다 — 문제를 좇을 때 config.json 에서만 고정한다.
WEB_SOURCES = ("auto", "instagrapi", "saveinsta", "fastdl", "igram")

# 각 방식의 간격 한계 (창의 검사와 작업 XML 이 같이 쓴다)
MAX_DAYS = 365
MAX_HOURS = 23
# 너무 잦으면 인스타그램이 막으므로 사용자 지정 간격의 하한을 둔다
MIN_CUSTOM_MINUTES = 10
# 예약 수집이 모아 둔 파일을 며칠 두고 지울지. save() 가 이 값일 때는 키를 아예 쓰지 않는다.
DEFAULT_RETENTION_DAYS = 7
MAX_CUSTOM_MINUTES = 23 * 60 + 59


def new_schedule_id() -> str:
    """작업 스케줄러 이름에 들어갈 짧은 식별자."""
    return uuid.uuid4().hex[:8]


@dataclass
class Account:
    id: str
    fav: bool = False


@dataclass
class Schedule:
    """예약 수집 설정 하나. 창을 닫아도 윈도우 작업 스케줄러가 대신 실행한다.

    여러 개를 만들 수 있고, 각각이 별도의 윈도우 작업(Storyge_<id>)이 된다.
    """

    id: str = field(default_factory=new_schedule_id)
    enabled: bool = True
    # True 면 time 시각에 딱 한 번만 실행하고, 끝나면 스스로 꺼진다 (mode 는 무시한다).
    once: bool = False
    # "daily"  매일 time 시각
    # "days"   interval 일마다 time 시각
    # "hours"  interval 시간마다
    # "custom" custom("H:MM") 간격마다
    mode: str = "daily"
    time: str = "21:00"
    interval: int = 1
    custom: str = "1:00"
    # 예약 수집 대상. 비어 있으면 등록된 계정 전체를 쓴다.
    accounts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "enabled": self.enabled,
            "once": self.once,
            "mode": self.mode,
            "time": self.time,
            "interval": self.interval,
            "custom": self.custom,
            "accounts": list(self.accounts),
        }


@dataclass
class Config:
    save_dir: Optional[str] = None
    login_user: Optional[str] = None
    # 인스타 디자인 exe 에서만 쓰는 밝기 설정 ("dark" 또는 "light").
    # 기존 exe 는 이 값을 무시하고 항상 classic 으로 뜬다.
    theme: str = "dark"
    # 화면 언어 ("ko" 또는 "en"). 기존 exe 는 이 값을 무시하고 한국어로 뜬다.
    lang: str = "ko"
    # 계정을 지우기 전에 물어볼지
    confirm_delete: bool = True
    # 예약 수집으로 모아 둔 파일을 며칠 두고 지울지
    staging_retention_days: int = DEFAULT_RETENTION_DAYS

    # --- 아래 셋은 웹 버전만 쓴다. exe 는 읽지도 쓰지도 않는다 -----------------
    # 파일명을 직접 정할지. 꺼 두면 CDN 원본 이름을 그대로 쓴다.
    use_filename_template: bool = False
    # 이름 형식. 껐다 켜도 초안이 남도록 use_filename_template 과 따로 둔다.
    # 기본값은 filename.SUGGESTED_TEMPLATE 이 아니라 빈 문자열이다.
    # (여기서 filename.py 를 import 하지 않는다 — config 는 paths 만 의존한다.)
    filename_template: str = ""
    # 수집 경로. WEB_SOURCES 중 하나.
    web_source: str = "auto"
    schedules: list[Schedule] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)

    def schedule_targets(self, spec: Optional[Schedule] = None) -> list[str]:
        """그 예약이 볼 계정. 따로 정하지 않았으면 등록된 계정 전체."""
        if spec is None:
            return self.targets()
        return list(spec.accounts) or self.targets()

    def find_schedule(self, schedule_id: str) -> Optional[Schedule]:
        for spec in self.schedules:
            if spec.id == schedule_id:
                return spec
        return None

    def first_enabled_schedule(self) -> Optional[Schedule]:
        """예약 식별자 없이 불렸을 때(업데이트 전에 등록된 작업) 쓸 예약."""
        for spec in self.schedules:
            if spec.enabled:
                return spec
        return None

    def find(self, account_id: str) -> Optional[Account]:
        for acc in self.accounts:
            if acc.id == account_id:
                return acc
        return None

    def targets(self, only_fav: bool = False) -> list[str]:
        """이번 실행에서 스토리를 확인할 계정 ID 목록."""
        return [a.id for a in self.accounts if a.fav or not only_fav]


_URL_RE = re.compile(r"instagram\.com/([^/?#]+)", re.IGNORECASE)


def normalize_id(raw: str) -> str:
    """'@ABC', 'abc/', 프로필 URL 등을 전부 'abc' 형태로 통일한다."""
    text = raw.strip()
    url_match = _URL_RE.search(text)
    if url_match:
        text = url_match.group(1)
    return text.lstrip("@").strip("/").strip().lower()


def _clamp(value, low: int, high: int, fallback: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return fallback


def _to_schedule(raw: dict) -> Schedule:
    """설정 파일의 예약 한 건을 읽는다. 모르는 값은 기본값으로 되돌린다.

    여기서 죽으면 프로그램이 아예 안 뜨므로 어떤 값이 들어와도 예외를 내지 않는다.
    """
    spec = Schedule(id=str(raw.get("id") or "").strip() or new_schedule_id())
    spec.enabled = bool(raw.get("enabled", True))
    spec.once = bool(raw.get("once", False))
    if raw.get("mode") in SCHEDULE_MODES:
        spec.mode = raw["mode"]
    if isinstance(raw.get("time"), str):
        spec.time = raw["time"]
    if isinstance(raw.get("custom"), str):
        spec.custom = raw["custom"]
    high = MAX_DAYS if spec.mode == "days" else MAX_HOURS
    spec.interval = _clamp(raw.get("interval", 1), 1, high, 1)
    spec.accounts = [
        normalize_id(a) for a in raw.get("accounts", []) if isinstance(a, str)
    ]
    return spec


def _migrate_schedule(raw: dict) -> Schedule:
    """예약이 하나뿐이던 시절의 설정({"schedule": {...}})을 새 형식으로 옮긴다.

    옛 "interval" 모드는 '몇 시간마다' 였으므로 "hours" 가 된다.
    24시간 이상이었다면 일 단위로 바꿔 준다.
    """
    spec = Schedule()
    spec.enabled = bool(raw.get("enabled", False))
    if isinstance(raw.get("time"), str):
        spec.time = raw["time"]
    spec.accounts = [
        normalize_id(a) for a in raw.get("accounts", []) if isinstance(a, str)
    ]

    if raw.get("mode") == "interval":
        hours = _clamp(raw.get("interval_hours", 6), 1, 24 * MAX_DAYS, 6)
        if hours >= 24:
            spec.mode = "days"
            spec.interval = min(MAX_DAYS, hours // 24)
        else:
            spec.mode = "hours"
            spec.interval = hours
    return spec


def _load_schedules(raw: dict) -> list[Schedule]:
    listed = raw.get("schedules")
    if isinstance(listed, list):
        return [_to_schedule(entry) for entry in listed if isinstance(entry, dict)]

    old = raw.get("schedule")
    if isinstance(old, dict):
        return [_migrate_schedule(old)]
    return []


def _set_aside_broken_config() -> None:
    """읽을 수 없는 설정 파일을 옆으로 치워 둔다. 지우지는 않는다."""
    broken = paths.CONFIG_FILE.with_suffix(".broken.json")
    try:
        if broken.exists():
            broken.unlink()
        paths.CONFIG_FILE.rename(broken)
    except OSError:
        pass


def load() -> Config:
    if not paths.CONFIG_FILE.exists():
        return Config()

    try:
        # utf-8-sig: 메모장이나 PowerShell 로 저장하면 BOM 이 붙는데,
        # 그냥 utf-8 로 읽으면 그 BOM 때문에 파일을 못 읽는다.
        with paths.CONFIG_FILE.open(encoding="utf-8-sig") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("설정 파일의 형식이 올바르지 않습니다")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError):
        # 설정이 깨졌다고 프로그램이 아예 안 뜨면 사용자가 손쓸 방법이 없다.
        # 깨진 파일은 남겨 두고 빈 설정으로 시작한다.
        _set_aside_broken_config()
        return Config()

    accounts = [
        Account(id=normalize_id(a["id"]), fav=bool(a.get("fav", False)))
        for a in raw.get("accounts", [])
    ]

    schedules = _load_schedules(raw)

    try:
        retention = max(0, int(raw.get("staging_retention_days", DEFAULT_RETENTION_DAYS)))
    except (TypeError, ValueError):
        retention = DEFAULT_RETENTION_DAYS

    # 웹 전용 키. exe 가 쓴 예전 설정 파일에는 아예 없으므로 없어도 돌아가야 하고,
    # 이상한 값이 들어와도 예외를 내지 않는다 (_to_schedule 과 같은 원칙).
    template = raw.get("filename_template")
    if not isinstance(template, str):
        template = ""
    source = raw.get("web_source")
    if source not in WEB_SOURCES:
        source = "auto"

    return Config(
        save_dir=raw.get("save_dir"),
        login_user=raw.get("login_user"),
        theme=raw.get("theme") or "dark",
        staging_retention_days=retention,
        schedules=schedules,
        lang=raw.get("lang") or "ko",
        confirm_delete=bool(raw.get("confirm_delete", True)),
        use_filename_template=bool(raw.get("use_filename_template", False)),
        filename_template=template,
        web_source=source,
        accounts=accounts,
    )


def save(cfg: Config) -> None:
    paths.ensure_data_dir()
    raw = {
        "save_dir": cfg.save_dir,
        "login_user": cfg.login_user,
        "theme": cfg.theme,
        "lang": cfg.lang,
        "confirm_delete": cfg.confirm_delete,
        "use_filename_template": cfg.use_filename_template,
        "filename_template": cfg.filename_template,
        "web_source": cfg.web_source,
        "accounts": [{"id": a.id, "fav": a.fav} for a in cfg.accounts],
    }

    # 예약 수집은 exe 전용이다. 웹만 쓰는 설정 파일에 빈 예약 목록과 기본 보관 기간이
    # 남아 있으면 '여기서도 예약을 쓰나' 싶게 만든다. 그래서 **내용이 있을 때만** 쓴다.
    #
    # 비었을 때만 빼는 것이 중요하다. load() 가 파일에 있던 예약을 이미 cfg 에 담아
    # 두므로, exe 와 폴더를 함께 쓰더라도(serve --data) 진짜 예약이 지워지지 않는다.
    # 키가 없으면 load() 가 각각 [] 와 7 로 돌려준다.
    # (예전 "schedule" 키는 여기서 사라진다 — load 가 이미 새 형식으로 옮겨 놓았다.)
    if cfg.schedules:
        raw["schedules"] = [s.as_dict() for s in cfg.schedules]
    if cfg.staging_retention_days != DEFAULT_RETENTION_DAYS:
        raw["staging_retention_days"] = cfg.staging_retention_days

    with paths.CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)


def add_accounts(cfg: Config, raw_ids: list[str], fav: bool = False) -> tuple[list[str], list[str]]:
    """여러 계정을 한 번에 추가한다. (추가된 목록, 이미 있던 목록)을 돌려준다."""
    added, existing = [], []
    for raw in raw_ids:
        account_id = normalize_id(raw)
        if not account_id:
            continue
        found = cfg.find(account_id)
        if found:
            if fav and not found.fav:
                found.fav = True
            existing.append(account_id)
        else:
            cfg.accounts.append(Account(id=account_id, fav=fav))
            added.append(account_id)
    cfg.accounts.sort(key=lambda a: a.id)
    return added, existing


def remove_accounts(cfg: Config, raw_ids: list[str]) -> tuple[list[str], list[str]]:
    """여러 계정을 한 번에 삭제한다. (삭제된 목록, 등록돼 있지 않던 목록)."""
    removed, missing = [], []
    for raw in raw_ids:
        account_id = normalize_id(raw)
        found = cfg.find(account_id)
        if found:
            cfg.accounts.remove(found)
            removed.append(account_id)
        else:
            missing.append(account_id)
    return removed, missing


def set_fav(cfg: Config, raw_ids: list[str], on: bool) -> tuple[list[str], list[str]]:
    """즐겨찾기를 켜거나 끈다. (바뀐 목록, 등록돼 있지 않던 목록)."""
    changed, missing = [], []
    for raw in raw_ids:
        account_id = normalize_id(raw)
        found = cfg.find(account_id)
        if found:
            found.fav = on
            changed.append(account_id)
        else:
            missing.append(account_id)
    return changed, missing
