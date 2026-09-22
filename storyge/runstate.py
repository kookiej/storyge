"""수집 작업의 진행 상태와 중지 요청을 파일로 주고받는다.

창(GUI)과 창 없는 예약 실행은 **서로 다른 프로세스**라 메모리를 공유할 수 없다.
그래서 상태는 data\\run_state.json 에, 중지 요청은 data\\cancel.flag 파일로 남긴다.

  run_state.json
    current      지금(또는 마지막) 실행 한 건. status/source/schedule_id/started_at/...
    by_schedule  예약별 마지막 실행 요약. 예약 목록에 '마지막 실행' 을 보여 주는 데 쓴다.

**여기의 모든 함수는 예외를 내지 않는다.** 창 없는 예약 실행에서 불리므로,
상태를 못 남긴다고 수집 자체가 죽으면 안 된다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Iterable, Optional

from . import paths
from .i18n import t

# 작업 스케줄러의 ExecutionTimeLimit 이 PT30M 이라, 그보다 오래된 '실행 중' 기록은
# 프로세스가 비정상 종료하며 남긴 찌꺼기로 본다 (psutil 없이 판단하는 방법).
STALE_AFTER = timedelta(minutes=35)

_ISO = "%Y-%m-%dT%H:%M:%S"


def _now_text() -> str:
    return datetime.now().strftime(_ISO)


def _parse(text) -> Optional[datetime]:
    if not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text[:19], _ISO)
    except ValueError:
        return None


def read() -> dict:
    """전체 상태. 파일이 없거나 깨졌으면 빈 dict."""
    try:
        with paths.RUN_STATE.open(encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return {}


def _write(data: dict) -> None:
    try:
        paths.ensure_data_dir()
        with paths.RUN_STATE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError, ValueError):
        pass


def current() -> dict:
    found = read().get("current")
    return found if isinstance(found, dict) else {}


def start(source: str, schedule_id: Optional[str] = None,
          targets: Iterable[str] = ()) -> None:
    """수집을 시작했다고 남긴다. source 는 "gui" 또는 "scheduled"."""
    names = [str(name) for name in targets]
    data = read()
    data["current"] = {
        "status": "running",
        "source": source,
        "schedule_id": schedule_id,
        "pid": os.getpid(),
        "started_at": _now_text(),
        "finished_at": None,
        "targets": names,
        "total_accounts": len(names),
        "done_accounts": 0,
        "items": 0,
    }
    _write(data)


def update(**fields) -> None:
    """진행 중인 값(done_accounts, items ...)을 덮어쓴다."""
    data = read()
    running = data.get("current")
    if not isinstance(running, dict):
        return
    running.update(fields)
    data["current"] = running
    _write(data)


def finish(status: str, **fields) -> None:
    """끝났다고 남기고, 예약이었으면 예약별 요약에도 복사한다."""
    data = read()
    running = data.get("current")
    if not isinstance(running, dict):
        running = {}
    running.update(fields)
    running["status"] = status
    running["finished_at"] = _now_text()
    data["current"] = running

    summary = {
        "status": status,
        "finished_at": running["finished_at"],
        "items": running.get("items", 0),
    }

    schedule_id = running.get("schedule_id")
    if schedule_id:
        by_schedule = data.get("by_schedule")
        if not isinstance(by_schedule, dict):
            by_schedule = {}
        by_schedule[str(schedule_id)] = dict(summary)
        data["by_schedule"] = by_schedule

    # 예약 창은 창에서 돌린 수집이 아니라 **예약** 이 마지막으로 언제 돌았는지를 보여 줘야 한다.
    # current 는 두 출처가 함께 쓰므로(겹침 방지에 필요) 예약 것만 따로 남긴다.
    if running.get("source") == "scheduled":
        data["last_scheduled"] = dict(summary, started_at=running.get("started_at"))
    _write(data)


def last_for(schedule_id: str) -> dict:
    """예약 하나의 마지막 실행 요약. 없으면 빈 dict."""
    by_schedule = read().get("by_schedule")
    if not isinstance(by_schedule, dict):
        return {}
    found = by_schedule.get(str(schedule_id))
    return found if isinstance(found, dict) else {}


def is_running() -> bool:
    """지금 수집이 도는 중인지.

    '실행 중' 인 채로 죽은 기록이 남으면 다음 예약이 영영 건너뛰어진다.
    그래서 시작 시각이 너무 오래됐으면 실행 중이 아닌 것으로 본다.
    """
    running = current()
    if running.get("status") != "running":
        return False
    started = _parse(running.get("started_at"))
    if started is None:
        return False
    return datetime.now() - started < STALE_AFTER


def scheduled_running() -> bool:
    """지금 도는 것이 **예약** 수집인지. 창에서 돌리는 수집은 False."""
    return is_running() and current().get("source") == "scheduled"


def clear() -> None:
    """진행 기록을 지운다 (예약 창의 '기록 지우기' 가 실행 기록과 함께 지운다)."""
    try:
        paths.RUN_STATE.unlink(missing_ok=True)
    except OSError:
        pass


# --- 중지 요청 -------------------------------------------------------


def request_cancel() -> None:
    """다른 프로세스에서 도는 수집에 중지를 요청한다."""
    try:
        paths.ensure_data_dir()
        paths.CANCEL_FLAG.write_text(_now_text(), encoding="utf-8")
    except OSError:
        pass


def cancel_requested() -> bool:
    try:
        return paths.CANCEL_FLAG.exists()
    except OSError:
        return False


def clear_cancel() -> None:
    try:
        paths.CANCEL_FLAG.unlink(missing_ok=True)
    except OSError:
        pass


# --- 화면 표시 -------------------------------------------------------


def describe(state: Optional[dict] = None) -> str:
    """예약 창에 보여 줄 한 줄 요약."""
    running = state if isinstance(state, dict) else current()
    if not running:
        return t("실행 중인 작업이 없습니다.")

    started = _parse(running.get("started_at"))
    when = started.strftime("%m-%d %H:%M") if started else "?"
    done = running.get("done_accounts", 0)
    total = running.get("total_accounts", 0)
    items = running.get("items", 0)

    if is_running():
        where = t("예약") if running.get("source") == "scheduled" else t("창")
        return t(
            "{where} 수집 실행 중 — {when} 시작, 계정 {done}/{total}, {items}개 보관",
            where=where, when=when, done=done, total=total, items=items,
        )

    return _last_run_text(running, when)


def _label_for(status) -> str:
    return {
        "done": t("완료"),
        "cancelled": t("중지됨"),
        "error": t("오류"),
        "running": t("중단됨"),
    }.get(status, str(status))


def _last_run_text(record: dict, fallback_when: str = "?") -> str:
    finished = _parse(record.get("finished_at"))
    end = finished.strftime("%m-%d %H:%M") if finished else fallback_when
    return t("마지막 실행: {end} {label}, {items}개 보관",
             end=end, label=_label_for(record.get("status")),
             items=record.get("items", 0))


def describe_scheduled() -> str:
    """예약 창에 보여 줄 한 줄. **예약 수집만** 본다.

    창에서 돌린 수집도 current 를 덮어쓰므로, 그걸 그대로 보여 주면
    예약 창인데 창에서 한 작업이 '마지막 실행' 으로 뜬다.
    """
    if scheduled_running():
        return describe()
    last = read().get("last_scheduled")
    if not isinstance(last, dict) or not last:
        # 다른 문장으로 갈아 끼우지 않는다. 같은 자리에 늘 같은 라벨이 있고 값만 빈다.
        return t("마지막 실행:")
    return _last_run_text(last)
