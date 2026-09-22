"""exe 두 개가 공유하는 시작 절차.

  - igstory.exe        : launch("classic")  -> 예전 그대로의 화면
  - igstory_insta.exe  : launch()           -> 인스타그램 디자인 (config 의 밝기 설정을 따름)

콘솔이 없는 창 프로그램이라 오류를 볼 방법이 없으므로, 여기서 파일과 창으로 알린다.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from typing import Optional


def guard_stdio() -> None:
    """콘솔 없는 exe(--windowed)에서는 sys.stdout 이 None 이라 print 가 예외를 낸다.

    화면에 로그를 찍는 GUI 라 표준 출력은 쓰지 않지만, 라이브러리가 무심코
    print 를 부를 수 있으므로 빈 곳으로 흘려보낸다.
    """
    for stream_name in ("stdout", "stderr"):
        if getattr(sys, stream_name, None) is None:
            setattr(sys, stream_name, open(os.devnull, "w", encoding="utf-8"))


def report(detail: str) -> None:
    """오류를 data/error.log 에 남기고 창으로 알린다."""
    log_path: Optional[Path]
    try:
        from . import paths

        log_path = paths.ensure_data_dir() / "error.log"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(detail + "\n" + "-" * 60 + "\n")
    except Exception:
        log_path = None

    try:
        import tkinter as tk
        from tkinter import messagebox

        from .i18n import t

        root = tk.Tk()
        root.withdraw()
        where = t("\n\n자세한 내용: {path}", path=log_path) if log_path else ""
        messagebox.showerror("Storyge 오류", detail[-1500:] + where)
        root.destroy()
    except Exception:
        pass


def run_scheduled(schedule_id: Optional[str] = None) -> int:
    """창을 띄우지 않고 예약 수집만 하고 끝낸다 (작업 스케줄러가 부른다).

    **어떤 경우에도 입력을 요청하면 안 된다.** 창이 없는 실행에서 로그인 대화창이나
    콘솔 input() 이 뜨면 프로세스가 그대로 멈춰 다음 예약까지 물고 늘어진다.
    그래서 자격증명을 물어보는 콜백에 '항상 None' 을 넘긴다.

    schedule_id 는 어느 예약이 불렀는지를 가리킨다(작업마다 --task 로 넘어온다).
    진행 상태는 runstate 에 남겨 창에서 볼 수 있게 하고, 창이 중지를 요청하면
    계정 사이에서 멈춘다.
    """
    guard_stdio()
    from . import config, fetch, history, i18n, runstate, schedule, session, staging
    from .i18n import t

    try:
        cfg = config.load()
        i18n.set_lang(cfg.lang)
    except Exception:
        cfg = None

    if cfg is None:
        schedule.log_line(t("설정을 읽지 못해 건너뜁니다."))
        return 1

    if schedule_id:
        spec = cfg.find_schedule(schedule_id)
        if spec is None:
            # 설정에서 지워진 예약이 부른 것이다. 작업만 남아 있으니 여기서 정리한다.
            schedule.log_line(t("등록되지 않은 예약이라 작업을 해제합니다."))
            schedule.unregister(schedule_id)
            return 0
    else:
        # --task 없이 불렸다 = 예약이 하나뿐이던 시절에 등록된 'Storyge' 작업.
        # 창을 아직 안 열었다면 새 작업이 없을 수 있으므로 여기서 그 작업을 지우지 않는다.
        # (정리는 창에서 schedule.sync() 가 새 작업을 등록한 뒤에 한다)
        spec = cfg.first_enabled_schedule()

    # 기록에는 **받은 스토리 개수와 문제만** 남긴다. 시작 배너 같은 진행 문구는 적지 않는다
    # (어느 예약이 언제 돌았는지는 예약 목록의 '마지막 …' 이 보여 준다).
    if runstate.is_running():
        schedule.log_line(t("다른 수집이 이미 실행 중이라 이번 실행을 건너뜁니다."))
        return 0

    targets = cfg.schedule_targets(spec)
    if not targets:
        schedule.log_line(t("예약 대상 계정이 없어 건너뜁니다."))
        return 0

    # 지난 실행에서 남은 중지 요청이 이번 실행까지 죽이면 안 된다
    runstate.clear_cancel()
    runstate.start("scheduled", spec.id if spec else None, targets)
    kept = 0

    try:
        client = session.get_client(
            cfg,
            force_login=False,
            # 로그인 진행 문구는 기록에 남기지 않는다. 실패는 LoginFailed 로 잡아 따로 적으므로
            # 정작 필요한 내용은 사라지지 않는다.
            log=lambda _message: None,
            ask_credentials=lambda: None,      # 절대 묻지 않는다
            ask_two_factor=lambda: None,
        )

        skip = history.load() | staging.staged_ids()
        items, notes = fetch.fetch_stories(
            client, targets, skip_mediaids=skip,
            should_stop=runstate.cancel_requested,
            on_account=lambda name, index, total: runstate.update(done_accounts=index),
        )
        for note in notes:
            schedule.log_line("  " + note)

        for item in items:
            if runstate.cancel_requested():
                break
            if staging.add(item, schedule.log_line):
                kept += 1
                runstate.update(items=kept)
        schedule.log_line(t("보관함에 {count}개를 넣었습니다.", count=kept))

        # 오래된 보관분 정리는 기록에 남기지 않는다 (스토리 정보가 아니다)
        staging.purge_older_than(cfg.staging_retention_days)

        if runstate.cancel_requested():
            schedule.log_line(t("취소 요청으로 중지했습니다."))
            runstate.finish("cancelled", items=kept)
        else:
            runstate.finish("done", items=kept, done_accounts=len(targets))
        return 0

    except session.LoginFailed as err:
        # 자격증명이 없거나 2단계 인증이 필요한 경우. 창을 띄울 수 없으니 기록만 남긴다.
        schedule.log_line(t("로그인하지 못했습니다: {reason}", reason=err))
        runstate.finish("error", items=kept)
        return 1
    except Exception:
        schedule.log_line(traceback.format_exc(limit=3).strip())
        runstate.finish("error", items=kept)
        return 1
    finally:
        runstate.clear_cancel()
        # '이번만' 예약은 한 번 돌았으면 (성공이든 아니든) 스스로 꺼진다.
        # 목록에는 '꺼짐 · 마지막 …' 으로 남아, 다시 켜면 그대로 또 쓸 수 있다.
        if spec is not None and spec.once:
            try:
                spec.enabled = False
                config.save(cfg)
                schedule.unregister(spec.id)
            except Exception:
                pass          # 창 없는 실행이라 여기서 죽으면 안 된다


def launch(theme_name: Optional[str] = None, scheduled: bool = False,
           schedule_id: Optional[str] = None) -> int:
    """GUI 를 띄운다. theme_name 이 None 이면 저장된 밝기 설정을 따른다."""
    if scheduled:
        return run_scheduled(schedule_id)

    guard_stdio()
    try:
        from . import config, gui, i18n, theme

        # 설정을 못 읽어도 창은 떠야 하므로 실패하면 기본값으로 간다
        try:
            saved = config.load()
        except Exception:
            saved = None

        if theme_name is None:
            theme_name = (saved.theme if saved else "dark")
            if theme_name not in ("dark", "light"):
                theme_name = "dark"
            # 언어 전환은 새 화면(insta exe)에서만 쓴다. 기본 화면은 한국어 고정.
            i18n.set_lang(saved.lang if saved else "ko")

        theme.set_theme(theme_name)
        return gui.main()
    except Exception:
        report(traceback.format_exc())
        return 1
