"""윈도우 작업 스케줄러 등록/해제.

명령줄 플래그(`schtasks /create /sc daily ...`)만으로는 **절전에서 깨우기**를 켤 수 없다.
그래서 작업 정의 XML 을 직접 만들어 `/XML` 로 등록한다.

넣는 설정과 이유:
  WakeToRun                    절전 상태에서 깨워 실행
  StartWhenAvailable           놓친 실행을 다음에 따라잡기
  DisallowStartIfOnBatteries   배터리로 돌 때도 실행 (기본값은 실행 안 함)
  LogonType=InteractiveToken   로그온만 돼 있으면 되고 비밀번호 저장이 필요 없다.
                               잠금 화면에서도 세션이 살아 있어 실행된다.
  RunLevel=LeastPrivilege      관리자 권한 불필요
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from . import config, paths
from .i18n import t

# 예약이 하나뿐이던 시절의 작업 이름. 새 설정으로 옮긴 뒤 sync() 가 지운다.
LEGACY_TASK_NAME = "Storyge"
_PREFIX = "Storyge_"

# GUI 에서 부르므로 콘솔 창이 번쩍이지 않게 한다
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def task_name(schedule_id: str) -> str:
    """예약 하나에 대응하는 윈도우 작업 이름."""
    return f"{_PREFIX}{schedule_id}"


def command_parts(schedule_id: str = "") -> tuple[str, str]:
    """(실행 파일, 인자). 빌드된 exe 면 그 자신을, 소스면 pythonw + run_insta.py.

    어느 예약이 부른 것인지 알 수 있게 --task 로 식별자를 함께 넘긴다.
    """
    tail = f" --task {schedule_id}" if schedule_id else ""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve()), f"--scheduled{tail}"

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else Path(sys.executable)
    script = (Path(__file__).resolve().parent.parent / "run_insta.py")
    return str(runner), f'"{script}" --scheduled{tail}'


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def parse_hhmm(text, default: Optional[tuple[int, int]] = None) -> Optional[tuple[int, int]]:
    """"H:MM" 을 (시, 분) 으로. int() 로 읽으므로 앞자리 0 은 없어도 된다.

    형식이 틀리면 default 를 돌려준다. 창의 입력 검사와 XML 만들기가 같이 쓴다.
    """
    if not isinstance(text, str):
        return default
    parts = text.strip().split(":")
    if len(parts) != 2:
        return default
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return default
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return default
    return hour, minute


def custom_minutes(spec: config.Schedule) -> int:
    """사용자 지정 간격을 분으로. 범위를 벗어나면 잘라 낸다."""
    hour, minute = parse_hhmm(spec.custom, (1, 0))
    total = hour * 60 + minute
    return max(config.MIN_CUSTOM_MINUTES, min(config.MAX_CUSTOM_MINUTES, total))


def _duration(minutes: int) -> str:
    """분을 ISO 8601 기간(PT1H30M)으로."""
    hours, mins = divmod(minutes, 60)
    text = "PT" + (f"{hours}H" if hours else "") + (f"{mins}M" if mins else "")
    return text if text != "PT" else f"PT{config.MIN_CUSTOM_MINUTES}M"


def _start_time(spec: config.Schedule, when: datetime) -> datetime:
    hour, minute = parse_hhmm(spec.time, (21, 0))
    return when.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _trigger(spec: config.Schedule, when: datetime) -> str:
    """반복 방식에 맞는 트리거 XML 한 덩어리.

    '몇 시간마다' 와 '사용자 지정' 은 Duration 없는 Repetition 을 쓴다.
    Duration 을 빼면 기간 제한 없이 계속 반복한다 (예전에는 P1D 라 하루마다 끊겼다).
    시작 시각을 지금 + 간격 으로 두는 이유: 등록하자마자 한 번 도는 것을 막기 위해서다
    (그 순간 사용자가 창에서 직접 수집을 돌리고 있을 수 있다).
    """
    if spec.once:
        # 반복 없는 TimeTrigger 하나. 오늘 그 시각이 이미 지났으면 내일 돈다.
        start = _start_time(spec, when)
        if start <= when:
            start += timedelta(days=1)
        return f"""    <TimeTrigger>
      <StartBoundary>{start:%Y-%m-%dT%H:%M:%S}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>"""

    if spec.mode == "days":
        start = _start_time(spec, when)
        days = max(1, min(config.MAX_DAYS, int(spec.interval)))
        return f"""    <CalendarTrigger>
      <StartBoundary>{start:%Y-%m-%dT%H:%M:%S}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>{days}</DaysInterval></ScheduleByDay>
    </CalendarTrigger>"""

    if spec.mode in ("hours", "custom"):
        if spec.mode == "hours":
            minutes = max(1, min(config.MAX_HOURS, int(spec.interval))) * 60
        else:
            minutes = custom_minutes(spec)
        start = (when + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
        return f"""    <TimeTrigger>
      <StartBoundary>{start:%Y-%m-%dT%H:%M:%S}</StartBoundary>
      <Repetition>
        <Interval>{_duration(minutes)}</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <Enabled>true</Enabled>
    </TimeTrigger>"""

    start = _start_time(spec, when)
    return f"""    <CalendarTrigger>
      <StartBoundary>{start:%Y-%m-%dT%H:%M:%S}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>"""


def describe(spec: config.Schedule) -> str:
    """'매일 21:00' 처럼 사람이 읽을 문구. 목록과 기록에 쓴다."""
    hour, minute = parse_hhmm(spec.time, (21, 0))
    clock = f"{hour}:{minute:02d}"
    if spec.once:
        return t("{time} 에 한 번", time=clock)
    if spec.mode == "days":
        return t("{n}일마다 {time}", n=max(1, int(spec.interval)), time=clock)
    if spec.mode == "hours":
        return t("{n}시간마다", n=max(1, int(spec.interval)))
    if spec.mode == "custom":
        total = custom_minutes(spec)
        return t("{interval} 간격", interval=f"{total // 60}:{total % 60:02d}")
    return t("매일 {time}", time=clock)


def build_xml(spec: config.Schedule, when: Optional[datetime] = None) -> str:
    """작업 정의 XML. 등록하지 않고 내용만 만들 수 있어 테스트하기 쉽다."""
    when = when or datetime.now()
    exe, args = command_parts(spec.id)
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
    trigger = _trigger(spec, when)

    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Storyge - scheduled Instagram story collection</Description>
    <Author>{_escape(user)}</Author>
  </RegistrationInfo>
  <Triggers>
{trigger}
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{_escape(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{_escape(exe)}</Command>
      <Arguments>{_escape(args)}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _run(args: list[str]) -> subprocess.CompletedProcess:
    # errors="replace": 한국어 윈도우의 schtasks 출력은 CP949 라 예상 밖 바이트가 섞이면
    # 디코딩에서 예외가 난다. 여기서 죽으면 예약 등록 전체가 실패한다.
    return subprocess.run(
        args, capture_output=True, text=True, errors="replace",
        creationflags=_NO_WINDOW, check=False,
    )


def is_registered(schedule_id: str) -> bool:
    return _run(["schtasks", "/Query", "/TN", task_name(schedule_id)]).returncode == 0


def register(spec: config.Schedule) -> tuple[bool, str]:
    """(성공 여부, 메시지). 실패해도 예외를 내지 않는다."""
    xml = build_xml(spec)
    temp = Path(tempfile.gettempdir()) / f"storyge_task_{os.getpid()}_{spec.id}.xml"
    try:
        # schtasks 는 작업 XML 을 UTF-16 으로 읽는다. UTF-8 로 주면 형식 오류가 난다.
        temp.write_text(xml, encoding="utf-16")
        result = _run(
            ["schtasks", "/Create", "/TN", task_name(spec.id), "/XML", str(temp), "/F"]
        )
    except OSError as err:
        return False, str(err)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass

    if result.returncode == 0:
        return True, ""
    return False, (result.stderr or result.stdout or "").strip()


def unregister(schedule_id: str) -> tuple[bool, str]:
    return _delete_task(task_name(schedule_id))


def _delete_task(name: str) -> tuple[bool, str]:
    result = _run(["schtasks", "/Delete", "/TN", name, "/F"])
    if result.returncode == 0:
        return True, ""
    return False, (result.stderr or result.stdout or "").strip()


def _is_ours(name: str) -> bool:
    base = name.rsplit("\\", 1)[-1]
    return base == LEGACY_TASK_NAME or base.startswith(_PREFIX)


def registered_task_names() -> list[str]:
    """등록돼 있는 Storyge 작업 이름 목록. 실패하면 빈 목록."""
    result = _run(["schtasks", "/Query", "/FO", "CSV", "/NH"])
    if result.returncode != 0:
        return []
    names = []
    for row in csv.reader((result.stdout or "").splitlines()):
        if row and _is_ours(row[0]):
            names.append(row[0])
    return names


def task_info() -> dict[str, tuple[str, str]]:
    """등록된 Storyge 작업의 {이름: (다음 실행 시각, 상태)}.

    시각은 윈도우가 준 문자열을 **그대로** 쓴다. 지역 형식(연/월/일 순서, 오전/오후)이
    PC 마다 달라 우리가 해석하면 오히려 틀린다.
    """
    result = _run(["schtasks", "/Query", "/FO", "CSV", "/NH"])
    if result.returncode != 0:
        return {}
    info: dict[str, tuple[str, str]] = {}
    for row in csv.reader((result.stdout or "").splitlines()):
        if len(row) >= 3 and _is_ours(row[0]):
            info[row[0].rsplit("\\", 1)[-1]] = (row[1].strip(), row[2].strip())
    return info


def sync(cfg: config.Config) -> list[str]:
    """설정과 실제 등록 상태를 맞춘다. 실패 메시지 목록을 돌려준다.

    켜 둔 예약은 등록하고, 끈 예약과 지워진 예약(그리고 예약이 하나뿐이던 시절의
    'Storyge' 작업)은 지운다. **창에서만 부른다** — 창 없는 예약 실행이 이걸 부르면
    아직 새 작업이 등록되기 전에 예전 작업을 지워 예약이 통째로 끊길 수 있다.
    """
    problems: list[str] = []
    wanted = set()

    for spec in cfg.schedules:
        if spec.enabled:
            wanted.add(task_name(spec.id))
            ok, message = register(spec)
            if not ok:
                problems.append(t("예약 등록에 실패했습니다: {reason}", reason=message))
        else:
            unregister(spec.id)

    for name in registered_task_names():
        if name.rsplit("\\", 1)[-1] not in wanted:
            _delete_task(name)
    return problems


# --- 예약 실행 기록 ---------------------------------------------------


def log_line(message: str) -> None:
    """창이 없는 예약 실행의 진행 내용을 파일에 남긴다."""
    try:
        paths.ensure_data_dir()
        with paths.SCHEDULE_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    except OSError:
        pass


def last_lines(limit: int = 6) -> list[str]:
    """마지막 실행 기록 몇 줄. 예약 설정 창에 보여 준다."""
    try:
        text = paths.SCHEDULE_LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-limit:]


def clear_log() -> None:
    """실행 기록 파일을 지운다 (예약 창의 '기록 지우기')."""
    try:
        paths.SCHEDULE_LOG.unlink(missing_ok=True)
    except OSError:
        pass
