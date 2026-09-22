"""GUI 메인 창.

콘솔 없이 이 창 하나로 계정 관리 · 즐겨찾기 · 저장 폴더 · 수집 · 선택 · 저장을 모두 한다.

스레드 규칙 (지키지 않으면 창이 얼거나 깨진다):
  - 네트워크 작업(로그인/수집/다운로드)은 워커 스레드에서 한다.
  - tkinter 위젯은 오직 메인 스레드에서만 건드린다.
    워커에서 화면을 바꾸고 싶으면 큐에 넣고, 메인 스레드가 주기적으로 꺼내 실행한다.
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk
from typing import Callable, Optional

from . import (
    config, download, fetch, history, i18n, net, paths, picker, runstate, schedule,
    session, staging, theme, widgets,
)
from .i18n import t

FONT = theme.FONT
FONT_BOLD = theme.FONT_BOLD
FONT_SMALL = theme.FONT_SMALL


def _style(style_name: str) -> dict:
    """색을 입히는 테마일 때만 ttk style 이름을 넘긴다.

    classic 에서는 style 을 지정하지 않아야 예전 모양 그대로 나온다.
    """
    return {"style": style_name} if theme.is_styled() else {}


def _paint(widget, **options) -> None:
    """ttk 가 아닌 위젯(Listbox·Text·Toplevel)에 색과 테두리를 지정한다.

    None 인 항목만 건너뛴다. 0 은 유효한 값이므로 반드시 살려야 한다
    (falsy 라고 걸러 버리면 highlightthickness=0 이 먹지 않아 밝은 테두리가 남는다).
    classic 에서는 호출하는 쪽이 전부 None 을 넘기므로 아무것도 바뀌지 않는다.
    """
    real = {key: value for key, value in options.items() if value is not None}
    if real:
        widget.configure(**real)


def _flat():
    """색을 입히는 테마에서만 테두리를 없앤다. classic 이면 None(건드리지 않음)."""
    return 0 if theme.is_styled() else None


# --- 숫자 입력칸 ------------------------------------------------------

_DIGITS = "0123456789"
# 숫자 키. 숫자 키패드(KP_0 ...)도 넣어야 오른쪽 키패드로 칠 때도 칸이 넘어간다.
_DIGIT_KEYS = frozenset(_DIGITS) | frozenset(f"KP_{d}" for d in _DIGITS)
# 라벨과 입력칸 사이 간격. 탭 한 칸쯤 되게 띄운다.
_TAB_GAP = 24


def _only_digits(entry: ttk.Entry, limit: int) -> None:
    """숫자만, limit 자리까지 받게 한다.

    str.isdigit() 을 쓰면 안 된다 — '²' 같은 글자에도 True 라서 나중에 int() 가 터진다.
    그래서 자릿수를 직접 확인한다.

    **검사 함수 안에서 위젯 내용을 바꾸면 tk 가 검사를 조용히 꺼 버린다.**
    여기서는 통과 여부만 답하고 아무것도 건드리지 않는다.
    """
    def ok(proposed: str) -> bool:
        return len(proposed) <= limit and all(ch in _DIGITS for ch in proposed)

    entry.configure(validate="key", validatecommand=(entry.register(ok), "%P"))


def _hop_when_full(first: ttk.Entry, second: ttk.Entry, limit: int = 2) -> None:
    """앞 칸을 다 채우면 뒤 칸으로 넘어간다.

    숫자를 넣었을 때만 넘어간다 (화살표나 지우기로는 움직이지 않는다).
    입력 검사 함수가 아니라 **키를 뗀 뒤에** 처리한다 — 위 설명대로 검사 함수 안에서
    위젯을 건드리면 검사가 꺼진다.

    누른 글자(event.char)가 아니라 키 이름(keysym)으로 판정한다 — 그래야 오른쪽
    숫자 키패드까지 잡힌다.
    """
    def hop(event) -> None:
        if event.keysym in _DIGIT_KEYS and len(first.get()) >= limit:
            second.focus_set()
            second.selection_range(0, "end")

    first.bind("<KeyRelease>", hop)


def _pad_two(entry: ttk.Entry, var: tk.StringVar) -> None:
    """칸을 벗어날 때 '5' 를 '05' 로 맞춘다.

    빈 칸은 그대로 둔다 — 저장할 때 걸러지므로 여기서 멋대로 채우지 않는다.
    """
    def fix(event) -> None:
        if len(var.get()) == 1:
            var.set(f"0{var.get()}")

    entry.bind("<FocusOut>", fix)


def _clock_box(parent, hour_var: tk.StringVar, minute_var: tk.StringVar) -> tuple:
    """[시] : [분] 한 묶음. ':' 은 글자라서 지울 방법이 없다.

    (묶음 프레임, 시 칸, ':' 라벨, 분 칸) 을 돌려준다. 부르는 쪽이 콜론과 분 칸을
    감출 수 있어야 해서(일/시간 방식) 각각을 다 넘긴다.

    분 칸은 두 자리로 정해져 있지만 **시 칸의 자릿수는 부르는 쪽이 정한다** —
    간격 묶음에서는 같은 칸이 '365일' 처럼 세 자리를 받아야 한다.
    셋 다 pack 해서 돌려주므로, 감추는 것은 부르는 쪽이 pack_forget 으로 한다.
    """
    box = ttk.Frame(parent)
    hour = ttk.Entry(box, textvariable=hour_var, width=4, font=FONT, justify="center")
    hour.pack(side="left")
    colon = ttk.Label(box, text=":", font=FONT)
    colon.pack(side="left", padx=3)
    minute = ttk.Entry(box, textvariable=minute_var, width=4, font=FONT, justify="center")
    minute.pack(side="left")

    _only_digits(minute, 2)
    _hop_when_full(hour, minute)
    _pad_two(minute, minute_var)
    return box, hour, colon, minute


class JobCancelled(Exception):
    """사용자가 '중지' 를 눌렀다. 워커가 조용히 빠져나오는 데 쓴다."""


def _write_error_log(detail: str) -> Optional[Path]:
    """예상치 못한 오류의 전체 내용을 data/error.log 에 남기고 경로를 돌려준다.

    exe 로 실행하면 콘솔이 없어 추적 내용을 볼 방법이 이것뿐이다.
    """
    try:
        log_path = paths.ensure_data_dir() / "error.log"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{detail}\n{'-' * 60}\n")
        return log_path
    except Exception:
        return None


# --- 로그인 입력 창 --------------------------------------------------


class LoginDialog(tk.Toplevel):
    """인스타그램 ID/비밀번호를 받는 모달 창.

    initial_user 를 주면 아이디를 미리 채워 둔다. 같은 계정이면 비밀번호만 치면 되고,
    다른 계정으로 바꿀 거면 지우고 새로 넣으면 된다.
    """

    def __init__(self, parent: tk.Misc, initial_user: str = "", on_forget=None):
        super().__init__(parent)
        self.result: Optional[tuple[str, str]] = None
        self.forgot = False
        self._on_forget = on_forget

        self.title(t("인스타그램 로그인"))
        self.resizable(False, False)
        self.transient(parent)
        _paint(self, bg=theme.color("bg"))

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text=t("스토리를 가져오려면 로그인이 필요합니다.\n"
                   "한 번만 하면 세션이 저장되어 다음부터는 묻지 않습니다."),
            font=FONT,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(frame, text=t("아이디"), font=FONT).grid(row=1, column=0, sticky="w", pady=4)
        self.user_entry = ttk.Entry(frame, width=28, font=FONT)
        self.user_entry.grid(row=1, column=1, pady=4)

        ttk.Label(frame, text=t("비밀번호"), font=FONT).grid(row=2, column=0, sticky="w", pady=4)
        self.pw_entry = ttk.Entry(frame, width=28, show="●", font=FONT)
        self.pw_entry.grid(row=2, column=1, pady=4)

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        if on_forget is not None:
            ttk.Button(buttons, text=t("로그인 정보 초기화"), command=self._forget).pack(side="left")
        ttk.Button(buttons, text=t("취소"), command=self._cancel).pack(side="right", padx=4)
        ttk.Button(buttons, text=t("로그인"), command=self._ok, **_style("Accent.TButton")).pack(
            side="right", padx=4
        )

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        # 아이디를 미리 채워 두면 같은 계정일 때 비밀번호만 치면 된다
        if initial_user:
            self.user_entry.insert(0, initial_user)
            self.pw_entry.focus_set()
        else:
            self.user_entry.focus_set()
        self.grab_set()
        parent.wait_window(self)

    def _ok(self) -> None:
        user = self.user_entry.get().strip().lstrip("@")
        password = self.pw_entry.get()
        if not user or not password:
            messagebox.showwarning(
                t("입력 필요"), t("아이디와 비밀번호를 모두 입력하세요."), parent=self
            )
            return
        self.result = (user, password)
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    def _forget(self) -> None:
        """저장된 세션·비밀번호·기억한 아이디를 모두 지운다."""
        if not messagebox.askyesno(
            t("확인"),
            t("이 PC 에 저장된 로그인 정보를 지울까요?\n다음 실행부터 다시 입력해야 합니다."),
            parent=self,
        ):
            return
        if self._on_forget:
            self._on_forget()
        self.forgot = True
        self.user_entry.delete(0, "end")
        self.pw_entry.delete(0, "end")
        self.user_entry.focus_set()
        messagebox.showinfo(t("완료"), t("저장된 로그인 정보를 지웠습니다."), parent=self)


class ScheduleEditDialog(tk.Toplevel):
    """예약 하나를 만들거나 고친다.

    닫힌 뒤 saved 로 저장 여부를 확인한다. 저장하면 넘겨받은 spec 이 그 자리에서 바뀌고
    (새 예약이면 cfg.schedules 에 들어가고) 윈도우 작업까지 맞춰진다.
    """

    def __init__(self, parent: tk.Misc, cfg: config.Config,
                 spec: config.Schedule, is_new: bool):
        super().__init__(parent)
        self.cfg = cfg
        self.spec = spec
        self.is_new = is_new
        self.saved = False

        self.title(t("새 예약") if is_new else t("예약 수정"))
        self.resizable(False, False)
        self.transient(parent)
        _paint(self, bg=theme.color("bg"))

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        self.enabled_var = tk.BooleanVar(value=spec.enabled)
        ttk.Checkbutton(frame, text=t("예약 사용"), variable=self.enabled_var).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )

        # 실행 — 이번만이면 반복 설정이 통째로 의미가 없어지므로 아래 줄들을 감춘다
        ttk.Label(frame, text=t("실행"), font=FONT).grid(row=1, column=0, sticky="w")
        once_row = ttk.Frame(frame)
        once_row.grid(row=1, column=1, columnspan=2, sticky="w", padx=(4, 0))
        self.once_var = tk.BooleanVar(value=spec.once)
        for label, value in ((t("반복"), False), (t("이번만"), True)):
            ttk.Radiobutton(once_row, text=label, variable=self.once_var, value=value,
                            command=self._refresh_fields).pack(side="left", padx=(0, 10))

        # 반복 방식 — 보이는 글자는 번역되므로 mode 는 반드시 **순번**으로 짝짓는다
        self.mode_label = ttk.Label(frame, text=t("반복"), font=FONT)
        self.mode_label.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.mode_box = ttk.Combobox(
            frame, state="readonly", width=14, font=FONT,
            values=[t("매일"), t("일마다"), t("시간마다"), t("사용자 지정")],
        )
        self.mode_box.current(
            config.SCHEDULE_MODES.index(spec.mode) if spec.mode in config.SCHEDULE_MODES else 0
        )
        self.mode_box.grid(row=2, column=1, sticky="w", padx=(4, 0), pady=(6, 0))
        self.mode_box.bind("<<ComboboxSelected>>", lambda e: self._refresh_fields())

        # 간격 (매일이면 숨긴다). 사용자 지정일 때만 ':' 과 분 칸이 함께 보인다.
        self.interval_label = ttk.Label(frame, text=t("간격"), font=FONT)
        self.interval_label.grid(row=3, column=0, sticky="w", pady=(6, 0))

        custom_hour, custom_min = schedule.parse_hhmm(spec.custom, (1, 0))
        self.interval_var = tk.StringVar(
            value=str(custom_hour) if spec.mode == "custom" else str(spec.interval)
        )
        self.interval_min_var = tk.StringVar(value=f"{custom_min:02d}")
        (self.interval_box, self.interval_entry,
         self.interval_colon, self.interval_min) = _clock_box(
            frame, self.interval_var, self.interval_min_var
        )
        _only_digits(self.interval_entry, 3)      # 일은 365 까지 받는다
        self.interval_box.grid(row=3, column=1, sticky="w", padx=(4, 0), pady=(6, 0))
        self.interval_hint = ttk.Label(frame, text="", font=FONT_SMALL, **_style("Sub.TLabel"))
        self.interval_hint.grid(row=3, column=2, sticky="w", padx=(6, 0), pady=(6, 0))

        # 시각 (시간마다 / 사용자 지정이면 숨긴다)
        self.time_label = ttk.Label(frame, text=t("시각"), font=FONT)
        self.time_label.grid(row=4, column=0, sticky="w", pady=(6, 0))

        hour, minute = schedule.parse_hhmm(spec.time, (21, 0))
        self.time_hour_var = tk.StringVar(value=str(hour))
        self.time_min_var = tk.StringVar(value=f"{minute:02d}")
        self.time_box, self.time_hour, _colon, self.time_min = _clock_box(
            frame, self.time_hour_var, self.time_min_var
        )
        _only_digits(self.time_hour, 2)
        self.time_box.grid(row=4, column=1, sticky="w", padx=(4, 0), pady=(6, 0))
        self.time_hint = ttk.Label(frame, text=t("예) 9:30"), font=FONT_SMALL,
                                   **_style("Sub.TLabel"))
        self.time_hint.grid(row=4, column=2, sticky="w", padx=(6, 0), pady=(6, 0))

        # 대상 계정
        ttk.Label(frame, text=t("대상 계정"), font=FONT).grid(
            row=5, column=0, sticky="nw", pady=(12, 0)
        )
        self.accounts_var = tk.StringVar(value=" ".join(spec.accounts))
        ttk.Entry(frame, textvariable=self.accounts_var, width=34, font=FONT).grid(
            row=5, column=1, columnspan=2, sticky="we", pady=(12, 0)
        )

        picks = ttk.Frame(frame)
        picks.grid(row=6, column=1, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(picks, text=t("목록에서 가져오기"),
                   command=lambda: self._take_from_list(False)).pack(side="left")
        ttk.Button(picks, text=t("즐겨찾기만 가져오기"),
                   command=lambda: self._take_from_list(True)).pack(side="left", padx=6)

        ttk.Label(frame, text=t("비워 두면 등록된 계정 전체를 확인합니다."),
                  font=FONT_SMALL, **_style("Sub.TLabel")).grid(
            row=7, column=1, columnspan=2, sticky="w", pady=(2, 0)
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text=t("닫기"), command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text=t("저장"), command=self._save,
                   **_style("Accent.TButton")).pack(side="right", padx=4)

        # 지금 화면에 그려진 방식. 방식이 바뀔 때만 간격 값을 되돌리는 데 쓴다
        # (첫 호출에서 방금 채운 값이 지워지지 않게 미리 맞춰 둔다).
        self._shown_mode = self._mode()
        self._refresh_fields()
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        parent.wait_window(self)

    # --- 동작 ---

    def _mode(self) -> str:
        index = self.mode_box.current()
        return config.SCHEDULE_MODES[index if 0 <= index < len(config.SCHEDULE_MODES) else 0]

    def _refresh_fields(self) -> None:
        """실행 옵션과 반복 방식에 따라 필요한 칸만 보여 준다."""
        once = bool(self.once_var.get())
        mode = self._mode()
        # 이번만이면 반복 설정은 통째로 의미가 없고, 시각 하나만 받으면 된다
        interval_on = not once and mode != "daily"
        time_on = once or mode in ("daily", "days")

        for widget in (self.mode_label, self.mode_box):
            widget.grid_remove() if once else widget.grid()
        for widget in (self.interval_label, self.interval_box, self.interval_hint):
            widget.grid() if interval_on else widget.grid_remove()
        for widget in (self.time_label, self.time_box, self.time_hint):
            widget.grid() if time_on else widget.grid_remove()

        # 일·시간은 숫자 하나면 되므로 ':' 과 분 칸을 치운다.
        # 항상 콜론 다음에 분 칸을 pack 하므로 다시 켜도 순서가 어긋나지 않는다.
        if mode == "custom":
            self.interval_colon.pack(side="left", padx=3)
            self.interval_min.pack(side="left")
        else:
            self.interval_colon.pack_forget()
            self.interval_min.pack_forget()

        self.interval_hint.configure(text={
            "days": t("일"),
            "hours": t("시간"),
            "custom": t("예) 1:30"),
        }.get(mode, ""))

        # 방식을 바꾸면 간격 칸에 남은 숫자의 뜻이 달라진다(3일 vs 3시간 간격).
        # 그래서 방식이 실제로 바뀔 때만 그 방식의 저장값으로 되돌린다.
        if mode != self._shown_mode:
            if mode == "custom":
                hour, _minute = schedule.parse_hhmm(self.spec.custom, (1, 0))
                self.interval_var.set(str(hour))
            elif self._shown_mode == "custom":
                self.interval_var.set(str(self.spec.interval))
            self._shown_mode = mode

    def _take_from_list(self, only_fav: bool) -> None:
        self.accounts_var.set(" ".join(self.cfg.targets(only_fav=only_fav)))

    def _warn(self, message: str) -> None:
        messagebox.showwarning(t("예약 수집"), message, parent=self)

    @staticmethod
    def _read_clock(hour_var: tk.StringVar,
                    minute_var: tk.StringVar) -> Optional[tuple[int, int]]:
        """두 칸에서 (시, 분). 비었거나 범위를 벗어나면 None.

        칸이 숫자만 받으므로 실패하는 경우는 '빈 칸' 과 '범위 초과' 뿐이다.
        """
        try:
            hour, minute = int(hour_var.get()), int(minute_var.get())
        except ValueError:          # 칸이 비어 있으면 여기로 온다
            return None
        return (hour, minute) if 0 <= hour <= 23 and 0 <= minute <= 59 else None

    def _read_interval(self, mode: str) -> Optional[tuple[int, str]]:
        """(일/시간 값, 사용자 지정 문구). 잘못됐으면 알리고 None."""
        if mode == "custom":
            parsed = self._read_clock(self.interval_var, self.interval_min_var)
            total = parsed[0] * 60 + parsed[1] if parsed else 0
            if not (config.MIN_CUSTOM_MINUTES <= total <= config.MAX_CUSTOM_MINUTES):
                self._warn(t("간격은 {low}~{high} 사이여야 합니다.", low="0:10", high="23:59"))
                return None
            return self.spec.interval, f"{parsed[0]}:{parsed[1]:02d}"

        high = config.MAX_DAYS if mode == "days" else config.MAX_HOURS
        try:
            value = int(self.interval_var.get())
        except ValueError:
            value = 0
        if not (1 <= value <= high):
            self._warn(t("간격은 {low}~{high} 사이여야 합니다.", low=1, high=high))
            return None
        return value, self.spec.custom

    def _save(self) -> None:
        once = bool(self.once_var.get())
        mode = self._mode()

        clock = self.spec.time
        if once or mode in ("daily", "days"):
            parsed = self._read_clock(self.time_hour_var, self.time_min_var)
            if parsed is None:
                self._warn(t("시각은 0:00~23:59 사이여야 합니다."))
                return
            clock = f"{parsed[0]}:{parsed[1]:02d}"

        interval = (self.spec.interval, self.spec.custom)
        if not once and mode != "daily":
            read = self._read_interval(mode)
            if read is None:
                return
            interval = read

        spec = self.spec
        spec.enabled = bool(self.enabled_var.get())
        spec.once = once
        spec.mode = mode
        spec.time = clock
        spec.interval, spec.custom = interval
        spec.accounts = [
            config.normalize_id(part)
            for part in self.accounts_var.get().replace(",", " ").split()
            if part
        ]
        # is 비교로 찾는다 — 값 비교(==)는 필드가 같은 다른 예약과 헷갈릴 수 있다
        if self.is_new and not any(s is spec for s in self.cfg.schedules):
            self.cfg.schedules.append(spec)

        config.save(self.cfg)

        if spec.enabled:
            ok, message = schedule.register(spec)
            text = t("예약을 등록했습니다.") if ok else t(
                "예약 등록에 실패했습니다: {reason}", reason=message
            )
        else:
            schedule.unregister(spec.id)
            text = t("예약을 해제했습니다.")

        self.saved = True
        messagebox.showinfo(t("예약 수집"), text, parent=self)
        self.destroy()


class ScheduleListDialog(tk.Toplevel):
    """예약 목록 · 보관함 · 실행 상태 · 실행 기록.

    닫힌 뒤 호출한 쪽이 확인할 것:
      review     — '저장하기' 를 눌렀는지. 선택 창은 이 창이 닫힌 뒤에 띄운다
                   (모달 창 위에 모달 창을 겹치면 잠금이 꼬인다)
      clear_pick — '비우기 > 직접 선택' 을 눌렀는지. 같은 이유로 창이 닫힌 뒤에 띄운다
    """

    def __init__(self, parent: tk.Misc, cfg: config.Config):
        super().__init__(parent)
        self.cfg = cfg
        self.review = False
        self.clear_pick = False
        self._tick_id: Optional[str] = None
        self._task_info: dict = {}

        self.title(t("예약 수집"))
        self.resizable(False, False)
        self.transient(parent)
        _paint(self, bg=theme.color("bg"))

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        row = 0

        # --- 예약 목록 ---
        ttk.Label(frame, text=t("예약 목록"), font=FONT_BOLD).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        row += 1

        list_row = ttk.Frame(frame)
        list_row.grid(row=row, column=0, columnspan=2, sticky="we")
        self.listbox = tk.Listbox(list_row, font=FONT, height=6, width=64, activestyle="none")
        _paint(
            self.listbox,
            bg=theme.color("surface_alt"), fg=theme.color("text"),
            selectbackground=theme.color("list_select_bg"),
            selectforeground=theme.color("list_select_fg"),
            highlightthickness=_flat(), bd=_flat(),
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", lambda e: self._edit())

        side = ttk.Frame(list_row, padding=(10, 0, 0, 0))
        side.pack(side="left", fill="y")
        ttk.Button(side, text=t("새 예약"), command=self._add).pack(fill="x", pady=2)
        ttk.Button(side, text=t("수정"), command=self._edit).pack(fill="x", pady=2)
        ttk.Button(side, text=t("켜기/끄기"), command=self._toggle).pack(fill="x", pady=2)
        ttk.Button(side, text=t("삭제"), command=self._delete).pack(fill="x", pady=2)
        row += 1

        # --- 실행 상태 ---
        state_row = ttk.Frame(frame)
        state_row.grid(row=row, column=0, columnspan=2, sticky="we", pady=(10, 0))
        self.state_label = ttk.Label(state_row, text="", font=FONT)
        self.state_label.pack(side="left")
        self.stop_button = ttk.Button(state_row, text=t("중지"), command=self._stop_running)
        row += 1

        # --- 보관 ---
        # 라벨과 입력칸을 한 프레임에 나란히 둔다. 격자 열에 따로 놓으면 위쪽 목록 행이
        # (columnspan 으로) 벌려 놓은 열 너비 때문에 입력칸이 오른쪽으로 밀린다.
        keep_row = ttk.Frame(frame)
        keep_row.grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Label(keep_row, text=t("보관 기간(일)"), font=FONT).pack(side="left")
        self.retention_var = tk.StringVar(value=str(cfg.staging_retention_days))
        retention_entry = ttk.Entry(keep_row, textvariable=self.retention_var,
                                    width=5, font=FONT, justify="center")
        retention_entry.pack(side="left", padx=(_TAB_GAP, 0))
        _only_digits(retention_entry, 3)
        row += 1

        stored = ttk.Frame(frame)
        stored.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.stored_label = ttk.Label(stored, text="", font=FONT)
        self.stored_label.pack(side="left", padx=(0, 8))
        ttk.Button(stored, text=t("저장하기"), command=self._review).pack(side="left")
        ttk.Button(stored, text=t("비우기"), command=self._clear_staging).pack(
            side="left", padx=6
        )
        row += 1

        # --- 최근 실행 기록 ---
        log_head = ttk.Frame(frame)
        log_head.grid(row=row, column=0, columnspan=2, sticky="we", pady=(12, 2))
        ttk.Label(log_head, text=t("최근 실행 기록"), font=FONT).pack(side="left")
        ttk.Button(log_head, text=t("기록 지우기"), command=self._clear_log).pack(side="right")
        row += 1

        self.log_box = tk.Text(frame, height=5, width=64, font=theme.log_font(), wrap="none")
        _paint(self.log_box, bg=theme.color("surface_alt"), fg=theme.color("text_dim"),
               bd=_flat(), highlightthickness=_flat())
        self.log_box.configure(state="disabled")
        self.log_box.grid(row=row, column=0, columnspan=2, sticky="we")
        row += 1

        note = t("절전에서 깨워 실행합니다. 완전히 끈 상태에서는 동작하지 않습니다.")
        if not schedule.is_frozen():
            note += "\n" + t(
                "소스로 실행 중이라 파이썬 경로로 등록됩니다. exe 로 빌드한 뒤 다시 등록하는 편이 안전합니다."
            )
        ttk.Label(frame, text=note, font=FONT_SMALL, justify="left",
                  **_style("Sub.TLabel")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        row += 1

        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text=t("닫기"), command=self._close,
                   **_style("Accent.TButton")).pack(side="right", padx=4)

        self._refresh_all()
        # 설정과 실제 등록 상태를 맞춘다 (예전 'Storyge' 작업과 고아 작업도 여기서 사라진다).
        # schtasks 를 여러 번 부르므로 창이 먼저 뜬 뒤에 한다.
        self.after(50, self._sync_tasks)
        self._tick_id = self.after(2000, self._tick)

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda e: self._close())
        self.grab_set()
        parent.wait_window(self)

    # --- 목록 --------------------------------------------------------

    def _selected(self) -> Optional[config.Schedule]:
        picked = self.listbox.curselection()
        if not picked:
            return None
        index = picked[0]
        if 0 <= index < len(self.cfg.schedules):
            return self.cfg.schedules[index]
        return None

    def _row_text(self, spec: config.Schedule) -> str:
        mark = "✓" if spec.enabled else "  "
        targets = " ".join("@" + a for a in spec.accounts) or t("전체 계정")
        when = self._task_info.get(schedule.task_name(spec.id), (None, None))[0]
        if not spec.enabled:
            tail = t("꺼짐")
        elif when:
            tail = t("다음 {when}", when=when)
        else:
            tail = t("등록 안 됨")
        last = runstate.last_for(spec.id)
        if last.get("finished_at"):
            tail += " · " + t("마지막 {when}", when=last["finished_at"][5:16].replace("T", " "))
        return f"{mark} {schedule.describe(spec)}  ·  {targets}  ·  {tail}"

    def _refresh_list(self) -> None:
        keep = self.listbox.curselection()
        self.listbox.delete(0, "end")
        for spec in self.cfg.schedules:
            self.listbox.insert("end", self._row_text(spec))
        if not self.cfg.schedules:
            self.listbox.insert("end", t("  (예약이 없습니다. '새 예약'을 눌러 만드세요.)"))
        elif keep and keep[0] < len(self.cfg.schedules):
            self.listbox.selection_set(keep[0])

    def _refresh_all(self) -> None:
        self._task_info = schedule.task_info()
        self._refresh_list()
        self._refresh_stored()
        self._refresh_log()
        self._refresh_state()

    def _sync_tasks(self) -> None:
        for problem in schedule.sync(self.cfg):
            messagebox.showwarning(t("예약 수집"), problem, parent=self)
        self._task_info = schedule.task_info()
        self._refresh_list()

    def _add(self) -> None:
        spec = config.Schedule()
        dialog = ScheduleEditDialog(self, self.cfg, spec, is_new=True)
        self._after_edit(dialog.saved)

    def _edit(self) -> None:
        spec = self._selected()
        if spec is None:
            messagebox.showinfo(t("선택 없음"), t("수정할 예약을 고르세요."), parent=self)
            return
        dialog = ScheduleEditDialog(self, self.cfg, spec, is_new=False)
        self._after_edit(dialog.saved)

    def _after_edit(self, saved: bool) -> None:
        # 겹쳐 뜬 창이 닫히면 잠금이 그 창과 함께 풀린다. 이 창이 다시 가져와야 한다.
        self.grab_set()
        if saved:
            self._task_info = schedule.task_info()
            self._refresh_list()

    def _toggle(self) -> None:
        spec = self._selected()
        if spec is None:
            messagebox.showinfo(t("선택 없음"), t("켜거나 끌 예약을 고르세요."), parent=self)
            return
        spec.enabled = not spec.enabled
        config.save(self.cfg)
        if spec.enabled:
            schedule.register(spec)
        else:
            schedule.unregister(spec.id)
        self._task_info = schedule.task_info()
        self._refresh_list()

    def _delete(self) -> None:
        spec = self._selected()
        if spec is None:
            messagebox.showinfo(t("선택 없음"), t("삭제할 예약을 고르세요."), parent=self)
            return
        if not messagebox.askyesno(
            t("예약 삭제"),
            t("이 예약을 삭제할까요?\n\n{what}", what=schedule.describe(spec)),
            parent=self,
        ):
            return
        self.cfg.schedules.remove(spec)
        config.save(self.cfg)
        schedule.unregister(spec.id)
        self._task_info = schedule.task_info()
        self._refresh_list()

    # --- 실행 상태 ---------------------------------------------------

    def _refresh_state(self) -> None:
        # 예약 창이므로 **예약** 수집만 본다. 창에서 돌린 수집도 진행 기록을 덮어쓰지만
        # 그건 여기서 보여 줄 것이 아니다.
        self.state_label.configure(text=runstate.describe_scheduled())
        if runstate.scheduled_running():
            self.stop_button.pack(side="left", padx=(10, 0))
        else:
            self.stop_button.pack_forget()

    def _tick(self) -> None:
        """예약 수집은 다른 프로세스라 알려 주지 않는다. 주기적으로 들여다본다."""
        self._tick_id = None
        if not self.winfo_exists():
            return
        self._refresh_state()
        self._tick_id = self.after(2000, self._tick)

    def _stop_running(self) -> None:
        if not messagebox.askyesno(
            t("예약 수집"), t("실행 중인 수집을 중지할까요?"), parent=self
        ):
            return
        runstate.request_cancel()
        schedule.log_line(t("다음 계정 확인 전에 멈춥니다."))
        self._refresh_state()

    # --- 보관함 ------------------------------------------------------

    def _refresh_stored(self) -> None:
        self.stored_label.configure(text=f"{t('보관 중')}: {staging.count()}")

    def _review(self) -> None:
        if staging.count() == 0:
            messagebox.showinfo(t("예약 수집"), t("보관 중인 스토리가 없습니다."), parent=self)
            return
        self.review = True
        self._close()

    def _clear_staging(self) -> None:
        total = staging.count()
        if total == 0:
            messagebox.showinfo(t("예약 수집"), t("보관 중인 스토리가 없습니다."), parent=self)
            return

        choice = ClearStagedDialog(self, total).choice
        self.grab_set()          # 겹쳐 뜬 창이 닫히며 놓은 잠금을 되찾는다
        if choice is None:
            return

        if choice == "pick":
            # 고르는 창은 이 창이 닫힌 **뒤에** 띄운다 ('저장하기' 와 같은 이유 —
            # 모달을 겹치면 잠금이 꼬인다). 메인 창이 이어받아 처리한다.
            self.clear_pick = True
            self._close()
            return

        if not messagebox.askyesno(
            t("보관함 비우기"), t("보관 중인 스토리 {count}개를 지울까요?", count=total), parent=self
        ):
            return
        removed = staging.clear_all()
        self._refresh_stored()
        messagebox.showinfo(
            t("예약 수집"), t("보관함을 비웠습니다. ({count}개)", count=removed), parent=self
        )

    # --- 기록 --------------------------------------------------------

    def _refresh_log(self) -> None:
        lines = schedule.last_lines() or [t("아직 실행 기록이 없습니다.")]
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.insert("1.0", "\n".join(lines))
        self.log_box.configure(state="disabled")

    def _clear_log(self) -> None:
        """실행 기록과 진행 상태를 함께 지운다."""
        # 실행 중인 기록을 지우면 겹침 방지(is_running)가 풀려 예약이 하나 더 시작될 수 있다
        if runstate.is_running():
            messagebox.showinfo(
                t("예약 수집"), t("수집이 실행 중입니다. 끝난 뒤에 지워 주세요."), parent=self
            )
            return
        if not messagebox.askyesno(
            t("기록 지우기"),
            t("실행 기록과 진행 상태를 지울까요?\n예약별 '마지막 실행' 표시도 사라집니다."),
            parent=self,
        ):
            return
        schedule.clear_log()
        runstate.clear()
        self._refresh_log()
        self._refresh_state()
        self._refresh_list()
        messagebox.showinfo(t("예약 수집"), t("실행 기록을 지웠습니다."), parent=self)

    # --- 닫기 --------------------------------------------------------

    def _close(self) -> None:
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except tk.TclError:
                pass
            self._tick_id = None

        # 보관 기간은 따로 저장 버튼이 없으므로 닫을 때 챙긴다
        try:
            days = max(0, int(self.retention_var.get()))
        except ValueError:
            days = 7
        if days != self.cfg.staging_retention_days:
            self.cfg.staging_retention_days = days
            config.save(self.cfg)
        self.destroy()


class CodeDialog(tk.Toplevel):
    """2단계 인증 코드를 받는 모달 창."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.result: Optional[str] = None

        self.title(t("2단계 인증"))
        self.resizable(False, False)
        self.transient(parent)
        _paint(self, bg=theme.color("bg"))

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=t("인증 앱 또는 문자로 받은 코드를 입력하세요."), font=FONT).pack(anchor="w")
        self.entry = ttk.Entry(frame, width=20, font=FONT)
        self.entry.pack(pady=10)

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e")
        ttk.Button(buttons, text=t("취소"), command=self._cancel).pack(side="right", padx=4)
        ttk.Button(buttons, text=t("확인"), command=self._ok).pack(side="right", padx=4)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.entry.focus_set()
        self.grab_set()
        parent.wait_window(self)

    def _ok(self) -> None:
        self.result = self.entry.get().strip() or None
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class ClearStagedDialog(tk.Toplevel):
    """보관함을 전체로 비울지, 골라서 비울지 묻는다.

    닫힌 뒤 choice 를 본다: "all" / "pick" / None(취소).
    (messagebox 로는 단추 세 개를 제 이름으로 달 수 없어 작은 창을 따로 둔다)
    """

    def __init__(self, parent: tk.Misc, total: int):
        super().__init__(parent)
        self.choice: Optional[str] = None

        self.title(t("보관함 비우기"))
        self.resizable(False, False)
        self.transient(parent)
        _paint(self, bg=theme.color("bg"))

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=t("보관 중인 스토리 {count}개가 있습니다.", count=total),
                  font=FONT).pack(anchor="w")
        ttk.Label(frame, text=t("어떻게 비울까요?"), font=FONT_SMALL,
                  **_style("Sub.TLabel")).pack(anchor="w", pady=(2, 0))

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e", pady=(14, 0))
        ttk.Button(buttons, text=t("취소"), command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text=t("직접 선택"),
                   command=lambda: self._pick("pick")).pack(side="right", padx=4)
        ttk.Button(buttons, text=t("전체"), command=lambda: self._pick("all"),
                   **_style("Accent.TButton")).pack(side="right", padx=4)

        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        parent.wait_window(self)

    def _pick(self, choice: str) -> None:
        self.choice = choice
        self.destroy()


# --- 메인 창 --------------------------------------------------------


class MainWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        # 기본 화면(classic)은 처음 만든 판이라 demo 로 구분한다
        self.root.title("Storyge" if theme.is_styled() else "Storyge (demo)")
        # 색 테마는 로그창을 넓게 쓰므로 창을 조금 더 높게 연다
        self.root.geometry("760x700" if theme.is_styled() else "760x640")
        self.root.minsize(680, 560)

        self.cfg = config.load()
        self.busy = False
        # 실행 중인 작업을 멈추는 신호. 워커가 안전한 자리에서만 확인한다.
        # (평범한 파이썬 속성이라 테마·언어를 바꿔 창을 다시 그려도 살아남는다)
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        # 작업을 버릴 때마다 올린다. 버려진 워커는 번호가 달라진 것을 보고 물러나므로,
        # 곧바로 시작한 새 작업의 상태·기록·화면을 건드리지 않는다.
        self.job_gen = 0
        # 워커 스레드 -> 메인 스레드로 넘길 작업들
        self.ui_queue: queue.Queue = queue.Queue()
        # 테마를 바꾸면 창을 다시 그리므로, 로그 내용을 따로 들고 있어야 한다
        self.log_lines: list[str] = []
        self._drain_id: Optional[str] = None
        self.root.bind("<Destroy>", self._on_destroy)

        theme.apply(self.root)
        self._build()
        self._refresh_accounts()
        self._refresh_savedir()
        self._drain_queue()

        self.log(t("준비됐습니다. 저장 폴더와 계정을 확인한 뒤 '스토리 가져오기'를 누르세요."))
        self.log(t("설정 위치: {path}", path=paths.DATA_DIR))

    # --- 화면 구성 ---------------------------------------------------

    def _card(self, parent, title: str, **pack_opts):
        """제목이 붙은 구획. 내용을 담을 프레임을 돌려준다.

        classic 은 예전처럼 홈이 파인 LabelFrame 을 쓰고,
        색을 입히는 테마에서는 인스타그램처럼 테두리만 있는 납작한 카드를 쓴다.
        """
        if not theme.is_styled():
            box = ttk.LabelFrame(parent, text=f" {title} ", padding=10)
            box.pack(**pack_opts)
            return box

        p = theme.palette()
        wrap = tk.Frame(
            parent, bg=p["surface"], bd=0,
            highlightbackground=p["border"], highlightcolor=p["border"], highlightthickness=1,
        )
        wrap.pack(**pack_opts)
        inner = ttk.Frame(wrap, style="Card.TFrame", padding=12)
        inner.pack(fill="both", expand=True)
        ttk.Label(inner, text=title, style="Head.TLabel").pack(anchor="w", pady=(0, 8))
        return inner

    def _build_topbar(self, parent) -> None:
        """앱 이름 · 로그인 계정 · 밝기 스위치. 색을 입히는 테마에서만 보인다."""
        p = theme.palette()
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(0, 12))
        ttk.Label(bar, text="Storyge", style="Title.TLabel").pack(side="left")
        ttk.Label(bar, text=t("  인스타그램 스토리 저장"), style="Sub.TLabel").pack(
            side="left", pady=(6, 0)
        )

        # 오른쪽부터 pack 하므로 먼저 넣은 것이 가장 오른쪽에 놓인다.
        # 손잡이 안의 아이콘만으로 지금 테마를 알린다 (글자 없음)
        self.theme_button = widgets.ToggleSwitch(
            bar,
            is_on=(theme.name() == "light"),
            command=lambda _on: self._toggle_theme(),
            on_icon="☀",
            off_icon="☾",
            on_color=p["accent"],
            off_color=p["border"],
            bg=p["bg"],
        )
        self.theme_button.pack(side="right")

        # 언어는 밝기 스위치 왼쪽. 배경 없이 **지금 언어만** 글자로 보여 주고 눌러서 바꾼다.
        self.lang_var = tk.BooleanVar(value=i18n.is_english())
        self.lang_button = widgets.FlatToggle(
            bar,
            variable=self.lang_var,
            on_text="EN",
            off_text="KR",
            on_color=p["text_dim"],
            off_color=p["text_dim"],
            bg=p["bg"],
            font=FONT_BOLD,
            command=lambda _on: self._toggle_lang(),
        )
        self.lang_button.pack(side="right", padx=(0, 10))

        self.account_label = ttk.Label(bar, text="", style="Sub.TLabel")
        self.account_label.pack(side="right", padx=(0, 12), pady=(6, 0))
        self._refresh_account_label()

    def _refresh_account_label(self) -> None:
        """상단 바에 지금 로그인된 계정을 보여 준다."""
        label = getattr(self, "account_label", None)
        if label is None:
            return
        user = self.cfg.login_user
        label.configure(text=f"@{user}" if user else t("로그인 안 됨"))

    def _build(self) -> None:
        p = theme.palette()
        card_label = _style("Card.TLabel")

        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        if theme.is_styled():
            self._build_topbar(outer)

        # 저장 폴더
        box_dir = self._card(outer, t("저장 폴더"), fill="x")
        dir_row = ttk.Frame(box_dir, **_style("Card.TFrame"))
        dir_row.pack(fill="x")
        self.dir_var = tk.StringVar()
        ttk.Entry(dir_row, textvariable=self.dir_var, state="readonly", font=FONT).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ttk.Button(dir_row, text=t("폴더 선택"), command=self._choose_dir).pack(side="left")

        # 계정
        # 색 테마에서는 계정 카드를 목록 높이만큼만 두고, 남는 세로 공간은 로그창이 가져간다
        acc_pack = dict(fill="x", pady=10) if theme.is_styled() else dict(fill="both", expand=True, pady=10)
        box_acc = self._card(outer, t("계정"), **acc_pack)

        list_row = ttk.Frame(box_acc, **_style("Card.TFrame"))
        list_row.pack(fill="both", expand=True)

        self.account_list = tk.Listbox(
            list_row, selectmode="extended", font=FONT, height=8, activestyle="none",
        )
        _paint(
            self.account_list,
            bg=p["surface_alt"], fg=p["text"],
            selectbackground=p["list_select_bg"], selectforeground=p["list_select_fg"],
            highlightthickness=_flat(), bd=_flat(),
        )
        self.account_list.pack(side="left", fill="both", expand=True)
        # Del 키로도 지울 수 있게
        self.account_list.bind("<Delete>", lambda e: self._remove_selected())
        # 이미 고른 항목을 더블클릭하면 선택이 풀린다
        self.account_list.bind("<Double-Button-1>", self._on_double_click)
        # 선택이 바뀌면 '전체 선택/해제' 버튼 문구를 맞춘다
        self.account_list.bind("<<ListboxSelect>>", lambda e: self._refresh_select_all())
        acc_scroll = ttk.Scrollbar(list_row, orient="vertical", command=self.account_list.yview)
        acc_scroll.pack(side="left", fill="y")
        self.account_list.configure(yscrollcommand=acc_scroll.set)

        side = ttk.Frame(list_row, padding=(10, 0, 0, 0), **_style("Card.TFrame"))
        side.pack(side="left", fill="y")
        ttk.Button(side, text=t("즐겨찾기 켜기/끄기"), command=self._toggle_fav).pack(fill="x", pady=2)
        ttk.Button(side, text=t("선택 삭제"), command=self._remove_selected).pack(fill="x", pady=2)
        self.select_all_button = ttk.Button(side, text=t("전체 선택"), command=self._toggle_select_all)
        self.select_all_button.pack(fill="x", pady=2)
        ttk.Label(side, text=t("(여러 개 선택 가능)"), font=FONT_SMALL, **_style("Dim.TLabel")).pack(
            pady=(6, 0)
        )

        # 삭제할 때마다 물어볼지 (기본은 물어봄)
        self.confirm_delete_var = tk.BooleanVar(value=self.cfg.confirm_delete)
        self.confirm_delete_button = ttk.Checkbutton(
            side,
            text=t("삭제 전 확인"),
            variable=self.confirm_delete_var,
            command=self._save_confirm_delete,
            **_style("Card.TCheckbutton"),
        )
        self.confirm_delete_button.pack(anchor="w", pady=(4, 0))

        add_row = ttk.Frame(box_acc, **_style("Card.TFrame"))
        add_row.pack(fill="x", pady=(10, 0))
        if not theme.is_styled():
            ttk.Label(add_row, text="추가", font=FONT, **card_label).pack(side="left", padx=(0, 6))
        self.add_var = tk.StringVar()
        add_entry = ttk.Entry(add_row, textvariable=self.add_var, font=FONT)
        add_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        add_entry.bind("<Return>", lambda e: self._add_accounts())

        self.add_fav_var = tk.BooleanVar(value=False)
        if theme.is_styled():
            # 배경 없는 별 아이콘 + 옆에 글자 (체크박스 대신)
            self.fav_button = widgets.StarButton(
                add_row,
                variable=self.add_fav_var,
                on_color=p["accent"],
                off_color=p["text_dim"],
                bg=p["surface"],
            )
            self.fav_button.pack(side="left", padx=(4, 0))
            # 아이콘만 누르게 하면 맞추기 번거로우니 글자도 같이 눌리게 한다
            self.fav_label = ttk.Label(add_row, text=t("즐겨찾기"), **_style("Dim.TLabel"))
            self.fav_label.pack(side="left", padx=(2, 8))
            self.fav_label.bind("<Button-1>", lambda e: self.fav_button._on_click())
        else:
            self.fav_button = ttk.Checkbutton(add_row, text=t("즐겨찾기"), variable=self.add_fav_var)
            self.fav_button.pack(side="left", padx=4)
        ttk.Button(add_row, text=t("추가"), command=self._add_accounts).pack(side="left")
        ttk.Label(
            box_acc,
            text=t("여러 개는 띄어쓰기로 구분하세요.  예)  abc def ghi   /   @abc   /   프로필 URL"),
            font=FONT_SMALL,
            **_style("Dim.TLabel"),
        ).pack(anchor="w", pady=(4, 0))

        # 실행 — 범위와 버튼을 **두 줄로** 나눈다. 한 줄에 다 넣으면 기본 창 너비에서
        # 오른쪽 버튼들이 잘려 나가 '취소' 를 누를 수조차 없다.
        box_run = ttk.Frame(outer)
        box_run.pack(fill="x")

        scope_row = ttk.Frame(box_run)
        scope_row.pack(fill="x")
        self.scope_var = tk.StringVar(value="all")
        # '직접 입력' 은 등록하지 않은 계정을 한 번만 확인할 때 쓴다 (설정에 저장하지 않는다)
        for label, value in (("전체 계정", "all"), ("즐겨찾기만", "fav"),
                             ("선택한 계정만", "sel"), ("직접 입력", "typed")):
            ttk.Radiobutton(scope_row, text=t(label), variable=self.scope_var, value=value).pack(
                side="left", padx=(0, 8)
            )

        action_row = ttk.Frame(box_run)
        action_row.pack(fill="x", pady=(6, 0))
        self.run_button = ttk.Button(
            action_row, text=t("스토리 가져오기"), command=self._on_run, **_style("Accent.TButton")
        )
        self.run_button.pack(side="left", padx=(0, 8))

        # 실행 중 멈추기 옵션은 '일시정지' 와 '취소' 둘. 작업 중에만 보인다
        # (여기서는 만들기만 하고 pack 하지 않는다). 기능이므로 classic 에서도 나온다.
        self.pause_button = ttk.Button(action_row, text=t("일시정지"), command=self._toggle_pause)
        self.cancel_button = ttk.Button(action_row, text=t("취소"), command=self._cancel_job)

        # 예약 (색 테마에만). 보관 중인 게 있으면 개수를 붙인다.
        # 오른쪽에 붙여 두어, 작업 중에 나타나는 일시정지·취소와 자리를 다투지 않게 한다.
        if theme.is_styled():
            self.schedule_button = ttk.Button(
                action_row, text=t("예약"), command=self._on_schedule
            )
            self.schedule_button.pack(side="right", padx=(8, 0))
            self._refresh_schedule_button()

        # 저장된 정보를 무시하고 창을 띄우므로, 계정을 바꾸는 통로이기도 하다
        self.relogin_button = ttk.Button(action_row, text=t("로그인"), command=self._on_relogin)
        self.relogin_button.pack(side="right")

        # 진행 상황
        box_log = self._card(outer, t("진행 상황"), fill="both", expand=True, pady=(10, 0))

        self.status_var = tk.StringVar(value="")
        if theme.is_styled():
            # 진행 문구를 로그창 글자와 같은 크기로 (굵기만 남긴다)
            family, size = theme.log_font()[0], theme.log_font()[1]
            status_font = (family, size, "bold")
            # 문구와 텍스트박스 사이 간격 = 한 줄 높이의 절반 (폰트가 바뀌어도 따라간다)
            line_height = tkfont.Font(root=self.root, font=theme.log_font()).metrics("linespace")
            status_gap = max(1, line_height // 2)
        else:
            status_font = FONT_BOLD
            status_gap = 6

        # 진행 문구는 왼쪽, '기록 지우기' 는 오른쪽. 카드 제목 줄은 classic(LabelFrame)과
        # 색 테마에서 구조가 달라 버튼을 올릴 수 없으므로 이 줄에 둔다.
        status_row = ttk.Frame(box_log, **_style("Card.TFrame"))
        status_row.pack(fill="x", pady=(0, status_gap))
        self.status_label = ttk.Label(
            status_row, textvariable=self.status_var, font=status_font, **card_label
        )
        self.status_label.pack(side="left")
        ttk.Button(status_row, text=t("기록 지우기"), command=self._clear_log_view).pack(
            side="right"
        )

        log_row = ttk.Frame(box_log, **_style("Card.TFrame"))
        log_row.pack(fill="both", expand=True)
        # classic 은 Consolas(한글 글리프 없음), 색 테마는 Malgun Gothic
        self.log_text = tk.Text(
            log_row,
            height=14 if theme.is_styled() else 10,
            font=theme.log_font(),
            wrap="word",
            state="disabled",
        )
        _paint(
            self.log_text,
            bg=p["surface_alt"], fg=p["text"], insertbackground=p["text"],
            selectbackground=p["list_select_bg"], highlightthickness=_flat(), bd=_flat(),
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(log_row, orient="vertical", command=self.log_text.yview)
        log_scroll.pack(side="left", fill="y")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    # --- 밝기 / 언어 전환 ---------------------------------------------

    def _toggle_theme(self) -> None:
        if self.busy:
            return
        new_theme = theme.other_theme()
        theme.set_theme(new_theme)
        self.cfg.theme = new_theme
        config.save(self.cfg)
        self._rebuild()

    def _toggle_lang(self) -> None:
        """한국어 <-> 영어. 색을 바꿀 때와 같이 창을 다시 그린다."""
        if self.busy:
            return
        new_lang = "en" if i18n.lang() == "ko" else "ko"
        i18n.set_lang(new_lang)
        self.cfg.lang = new_lang
        config.save(self.cfg)
        self._rebuild()

    def _rebuild(self) -> None:
        """색을 바꾸려면 창을 다시 그리는 것이 가장 확실하다.

        ttk 스타일은 이미 만들어진 위젯에 전부 다시 먹지 않기 때문이다.
        로그와 상태는 문자열로 들고 있다가 새 위젯에 다시 채운다.
        """
        kept_log = list(self.log_lines)
        kept_status = self.status_var.get()

        for child in self.root.winfo_children():
            child.destroy()

        theme.apply(self.root)
        self._build()
        self._refresh_accounts()
        self._refresh_savedir()

        self.log_lines = []
        for line in kept_log:
            self._append_log(line)
        self.status_var.set(kept_status)
        self._refresh_select_all()

    # --- 워커 -> 메인 스레드 다리 ------------------------------------

    def _drain_queue(self) -> None:
        """워커가 큐에 넣은 작업을 메인 스레드에서 처리한다."""
        while True:
            try:
                job = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                job()
            except Exception:
                pass
        try:
            self._drain_id = self.root.after(80, self._drain_queue)
        except tk.TclError:
            # 창이 이미 닫힌 뒤라면 더 예약하지 않는다
            self._drain_id = None

    def _on_destroy(self, event) -> None:
        """창이 닫히면 예약된 반복 작업을 취소한다.

        취소하지 않으면 닫힌 뒤에 콜백이 한 번 더 깨어나
        'invalid command name ..._drain_queue' 오류가 뜬다.
        (테마를 바꿀 때는 자식만 지우므로 root 가 대상일 때만 처리한다)
        """
        if event.widget is not self.root or self._drain_id is None:
            return
        try:
            self.root.after_cancel(self._drain_id)
        except tk.TclError:
            pass
        self._drain_id = None

    def ui(self, func: Callable[[], None]) -> None:
        """화면 갱신을 메인 스레드에 맡긴다 (기다리지 않음)."""
        self.ui_queue.put(func)

    def ui_wait(self, func: Callable):
        """메인 스레드에서 실행하고 결과가 나올 때까지 기다린다 (창을 띄울 때 사용)."""
        box: dict = {}
        done = threading.Event()

        def wrapper() -> None:
            try:
                box["result"] = func()
            except Exception as err:
                box["error"] = err
            finally:
                done.set()

        self.ui_queue.put(wrapper)
        done.wait()
        if "error" in box:
            raise box["error"]
        return box.get("result")

    def log(self, message: str) -> None:
        """어느 스레드에서 불러도 안전하다."""
        self.ui(lambda: self._append_log(message))

    def _append_log(self, message: str) -> None:
        # 테마를 바꾸면 창을 다시 그리므로 내용을 따로 보관한다 (너무 쌓이지 않게 최근 것만)
        self.log_lines.append(message)
        del self.log_lines[:-500]

        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log_view(self) -> None:
        """'진행 상황' 칸을 비운다. 화면에만 있는 내용이라 파일은 건드리지 않는다.

        log_lines 도 함께 비워야 한다 — 테마·언어를 바꾸면 _rebuild 가 그 목록으로
        로그를 되살리므로, 남겨 두면 지운 내용이 다시 나타난다.
        """
        self.log_lines = []
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def status(self, message: str) -> None:
        self.ui(lambda: self.status_var.set(message))

    # --- 계정/폴더 관리 ----------------------------------------------

    def _refresh_accounts(self) -> None:
        self.account_list.delete(0, "end")
        for acc in self.cfg.accounts:
            self.account_list.insert("end", f"{'★' if acc.fav else '  '} @{acc.id}")

    def _refresh_savedir(self) -> None:
        self.dir_var.set(self.cfg.save_dir or t("(아직 정하지 않음)"))

    def _selected_ids(self) -> list[str]:
        return [self.cfg.accounts[i].id for i in self.account_list.curselection()]

    # --- 목록 선택 ---------------------------------------------------

    def _on_double_click(self, event):
        """이미 고른 항목을 더블클릭하면 선택을 푼다.

        첫 클릭이 그 항목을 선택하고 이어진 더블클릭이 해제하므로,
        결과적으로 '더블클릭하면 선택이 풀린다' 가 된다.
        """
        index = self.account_list.nearest(event.y)
        if index >= 0 and index in self.account_list.curselection():
            self.account_list.selection_clear(index)
            self._refresh_select_all()
        return "break"          # 기본 동작이 뒤따르지 않게

    def _toggle_select_all(self) -> None:
        total = self.account_list.size()
        if total == 0:
            return
        if len(self.account_list.curselection()) == total:
            self.account_list.selection_clear(0, "end")
        else:
            self.account_list.selection_set(0, "end")
        self._refresh_select_all()

    def _refresh_select_all(self) -> None:
        """모두 골라져 있으면 '전체 해제', 아니면 '전체 선택'."""
        button = getattr(self, "select_all_button", None)
        if button is None:
            return
        total = self.account_list.size()
        all_selected = total > 0 and len(self.account_list.curselection()) == total
        button.configure(text=t("전체 해제") if all_selected else t("전체 선택"))

    def _save_confirm_delete(self) -> None:
        self.cfg.confirm_delete = bool(self.confirm_delete_var.get())
        config.save(self.cfg)

    def _choose_dir(self) -> None:
        chosen = filedialog.askdirectory(title=t("스토리를 저장할 폴더 선택"))
        if not chosen:
            return
        self.cfg.save_dir = str(Path(chosen).resolve())
        config.save(self.cfg)
        self._refresh_savedir()
        self.log(t("저장 폴더: {path}", path=self.cfg.save_dir))

    def _add_accounts(self) -> None:
        typed = self.add_var.get()
        ids = [part for part in typed.replace(",", " ").split() if part]
        if not ids:
            return
        added, existing = config.add_accounts(self.cfg, ids, fav=self.add_fav_var.get())
        config.save(self.cfg)
        self.add_var.set("")
        self._refresh_accounts()
        if added:
            self.log(t("추가함: {names}", names=", ".join("@" + a for a in added)))
        if existing:
            self.log(t("이미 등록돼 있음: {names}", names=", ".join("@" + a for a in existing)))
        self._refresh_select_all()

    def _remove_selected(self) -> None:
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo(
                t("선택 없음"), t("삭제할 계정을 목록에서 고르세요."), parent=self.root
            )
            return
        # '삭제 전 확인' 을 꺼 두면 묻지 않고 바로 지운다
        if self.confirm_delete_var.get() and not messagebox.askyesno(
            t("삭제 확인"),
            t("{count}개 계정을 목록에서 삭제할까요?\n\n{names}\n\n(이미 저장한 파일은 지워지지 않습니다)",
              count=len(ids), names=", ".join("@" + i for i in ids)),
            parent=self.root,
        ):
            return
        removed, _ = config.remove_accounts(self.cfg, ids)
        config.save(self.cfg)
        self._refresh_accounts()
        self.log(t("삭제함: {names}", names=", ".join("@" + a for a in removed)))
        self._refresh_select_all()

    def _toggle_fav(self) -> None:
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo(
                t("선택 없음"), t("즐겨찾기를 바꿀 계정을 목록에서 고르세요."), parent=self.root
            )
            return
        for account_id in ids:
            found = self.cfg.find(account_id)
            if found:
                found.fav = not found.fav
        config.save(self.cfg)
        self._refresh_accounts()
        self.log(t("즐겨찾기 변경: {names}", names=", ".join("@" + a for a in ids)))

    # --- 로그인 창을 워커에서 요청할 때 ------------------------------

    def _ask_credentials(self) -> Optional[tuple[str, str]]:
        def show():
            return LoginDialog(
                self.root,
                initial_user=self.cfg.login_user or "",
                on_forget=self._forget_login,
            ).result

        return self.ui_wait(show)

    def _reload_login_display(self) -> None:
        """설정을 다시 읽어 로그인 계정 표시를 맞춘다 (메인 스레드에서 부를 것)."""
        self.cfg = config.load()
        self._refresh_account_label()

    def _forget_login(self) -> None:
        """저장된 로그인 정보를 지운다 (로그인 창에서 부른다 — 메인 스레드)."""
        session.forget_login(self.cfg)
        self._append_log(t("저장된 로그인 정보를 지웠습니다."))
        self._refresh_account_label()

    def _ask_two_factor(self) -> Optional[str]:
        return self.ui_wait(lambda: CodeDialog(self.root).result)

    # --- 실행 --------------------------------------------------------

    def _set_busy(self, busy: bool, cancellable: bool = True) -> None:
        """작업 중 표시. cancellable 이 False 면 일시정지·중지 버튼을 띄우지 않는다
        (로그인은 중간에 끊을 자리가 없어 버튼만 보이면 눌러도 반응이 없다)."""
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.run_button.configure(state=state)
        self.relogin_button.configure(state=state)
        button = getattr(self, "schedule_button", None)
        if button is not None:
            button.configure(state=state)
        # 밝기·언어 전환은 창을 다시 그리므로 작업 중에는 막는다
        for name in ("theme_button", "lang_button"):
            toggle = getattr(self, name, None)
            if toggle is not None:
                toggle.configure(state=state)

        if busy:
            # 지난 작업에서 눌러 둔 신호가 새 작업을 곧바로 죽이면 안 된다
            self.cancel_event.clear()
            self.pause_event.clear()
            if cancellable:
                # 작업 중에는 '스토리 가져오기' 가 어차피 눌리지 않으므로 그 자리를
                # 멈추기 버튼에 내준다. 한 줄에 다 넣으면 기본 창 너비에서 잘려
                # '취소' 를 누를 수 없게 된다.
                self.run_button.pack_forget()
                self.pause_button.configure(text=t("일시정지"), state="normal")
                self.cancel_button.configure(state="normal")
                self.pause_button.pack(side="left", padx=(0, 8))
                self.cancel_button.pack(side="left", padx=(0, 8))
        else:
            self.pause_button.pack_forget()
            self.cancel_button.pack_forget()
            if not self.run_button.winfo_manager():
                self.run_button.pack(side="left", padx=(0, 8))
            self.status_var.set("")

    # --- 일시정지 / 취소 ----------------------------------------------

    def _toggle_pause(self) -> None:
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_button.configure(text=t("일시정지"))
            self.status_var.set(t("계속하는 중..."))
        else:
            self.pause_event.set()
            self.pause_button.configure(text=t("계속"))
            self.status_var.set(t("일시정지됨"))

    def _cancel_job(self) -> None:
        """'취소' — 기다리지 않고 작업을 버린 뒤 창을 바로 돌려준다.

        워커 스레드를 죽이지는 않는다. 파이썬에서 스레드를 안전하게 죽일 방법이 없고,
        흔히 쓰는 PyThreadState_SetAsyncExc 는 정작 문제인 '막혀 있는 소켓 읽기' 를
        깨우지 못하면서 위험만 진다. 대신 **세대 번호를 올려 작업을 버린다** — 버려진
        워커는 아래 _alive 검사에 걸려 화면·기록에 손대지 못하고, 다음 확인 지점에서
        조용히 끝난다. 받던 파일은 net.download_to 가 .part 로 받아 옮기므로
        반쪽짜리로 남지 않는다.
        """
        self.job_gen += 1
        self.cancel_event.set()
        self.pause_event.clear()      # 멈춰 있던 워커도 풀어 줘야 빠져나온다
        runstate.finish("cancelled")  # 버려진 워커는 이제 이 기록에 손대지 않는다
        self._set_busy(False)
        self._append_log(t("작업을 취소했습니다."))

    def _alive(self, gen: int) -> bool:
        """이 워커가 아직 '지금 작업' 인지. 버려졌으면 False."""
        return gen == self.job_gen

    def _should_stop(self, gen: Optional[int] = None) -> bool:
        """워커가 안전한 자리마다 부른다. 일시정지 중이면 여기서 붙잡고 있는다.

        붙잡는 쪽이 워커 스레드이므로 창은 그동안에도 멀쩡히 움직인다.
        버려진 작업(세대가 다름)도 True 를 받아 스스로 빠져나간다.
        """
        while self.pause_event.is_set() and not self.cancel_event.is_set():
            time.sleep(0.2)
        if gen is not None and not self._alive(gen):
            return True
        return self.cancel_event.is_set()

    def _checkpoint(self, gen: Optional[int] = None) -> None:
        """취소했으면 여기서 작업을 끝낸다 (fetch/download 바깥의 단계용)."""
        if self._should_stop(gen):
            raise JobCancelled()

    # --- 예약 수집 ---------------------------------------------------

    def _refresh_schedule_button(self) -> None:
        """보관 중인 스토리 개수를 버튼에 붙인다."""
        button = getattr(self, "schedule_button", None)
        if button is None:
            return
        waiting = staging.count()
        button.configure(text=t("예약 ({count})", count=waiting) if waiting else t("예약"))

    def _on_schedule(self) -> None:
        if self.busy:
            return
        dialog = ScheduleListDialog(self.root, self.cfg)
        # 대화창에서 저장했을 수 있으니 설정을 다시 읽는다
        self.cfg = config.load()
        self._refresh_schedule_button()
        # 고르는 창은 예약 창이 닫힌 **뒤에** 띄운다 (모달을 겹치면 잠금이 꼬인다)
        if dialog.review:
            self._review_staged()
        elif dialog.clear_pick:
            self._clear_staged_pick()

    def _review_staged(self) -> None:
        """예약으로 모아 둔 스토리를 골라 저장 폴더로 옮긴다."""
        items = staging.items()
        if not items:
            messagebox.showinfo(t("예약 수집"), t("보관 중인 스토리가 없습니다."), parent=self.root)
            return

        if not self.cfg.save_dir:
            messagebox.showinfo(
                t("저장 폴더 필요"), t("먼저 저장 폴더를 정해 주세요."), parent=self.root
            )
            self._choose_dir()
            if not self.cfg.save_dir:
                return

        self.log(t("예약 수집으로 모아 둔 스토리 {count}개가 있습니다.", count=len(items)))
        # 보관분은 로컬 파일이라 주소 대신 파일을 읽는다 (인스타 주소는 이미 죽어 있다)
        thumbs = picker.load_thumbnails(items, staging.read_bytes)
        chosen = picker.open_picker(self.root, items, thumbs)
        if not chosen:
            self.log(t("선택한 항목이 없습니다. (저장된 파일 없음)"))
            return

        self.log(t("보관분 {count}개를 저장 폴더로 옮깁니다.", count=len(chosen)))
        ok, failed = staging.move_to(chosen, Path(self.cfg.save_dir), log=self._append_log)
        self.log(t("완료: {ok}개 저장, {failed}개 실패", ok=ok, failed=failed))
        self._refresh_schedule_button()

    def _clear_staged_pick(self) -> None:
        """보관분을 눈으로 보고 골라 지운다 ('비우기 > 직접 선택').

        무엇을 지우는지 썸네일로 보고 고르므로 따로 확인을 또 묻지 않는다.
        """
        items = staging.items()
        if not items:
            messagebox.showinfo(t("예약 수집"), t("보관 중인 스토리가 없습니다."), parent=self.root)
            return

        # 보관분은 로컬 파일이라 주소 대신 파일을 읽는다 (인스타 주소는 이미 죽어 있다)
        thumbs = picker.load_thumbnails(items, staging.read_bytes)
        chosen = picker.open_picker(
            self.root, items, thumbs,
            title=t("지울 스토리 선택"), confirm_text=t("지우기"),
        )
        if not chosen:
            self.log(t("지운 항목이 없습니다."))
            return

        removed = staging.remove(i.mediaid for i in chosen)
        self.log(t("보관함에서 {count}개를 지웠습니다.", count=removed))
        self._refresh_schedule_button()

    def _on_relogin(self) -> None:
        self._login_only()

    def _on_run(self) -> None:
        self._start()

    def _login_only(self) -> None:
        """'로그인' 버튼.

        계정 목록이나 저장 폴더와 **무관하게** 로그인 창만 띄운다.
        예전에는 이 버튼도 _start() 를 거쳤는데, 거기서 '등록된 계정 없음' 검사에
        먼저 걸려 계정을 하나도 등록하지 않으면 로그인 자체를 할 수 없었다.
        """
        if self.busy:
            return
        self._set_busy(True, cancellable=False)
        self.status_var.set(t("로그인 중..."))
        threading.Thread(target=self._work_login, daemon=True).start()

    def _work_login(self) -> None:
        """로그인만 하는 워커. 스토리는 가져오지 않는다."""
        try:
            cfg = config.load()
            client = session.get_client(
                cfg,
                force_login=True,
                log=self.log,
                ask_credentials=self._ask_credentials,
                ask_two_factor=self._ask_two_factor,
            )
            self.ui(self._reload_login_display)
            self.log(t("로그인됨: @{user}",
                       user=getattr(client, "username", None) or cfg.login_user or ""))
        except session.LoginFailed as err:
            self.log(str(err))
        except Exception as err:
            log_path = _write_error_log(traceback.format_exc())
            self.log(t("오류가 생겼습니다: {reason}", reason=session.describe_error(err)))
            if log_path:
                self.log(t("  자세한 내용을 남겼습니다: {path}", path=log_path))
        finally:
            self.ui(lambda: self._set_busy(False))

    def _start(self) -> None:
        """'스토리 가져오기' 버튼. 계정과 저장 폴더가 있어야 진행한다."""
        if self.busy:
            return

        scope = self.scope_var.get()
        selected = self._selected_ids()      # 목록을 다시 읽기 전에 골라 둔 것을 챙긴다
        self.cfg = config.load()

        if scope == "typed":
            # 등록하지 않은 계정을 한 번만 확인한다. 설정에는 저장하지 않는다.
            targets = picker.ask_accounts(
                self.root, [a.id for a in self.cfg.accounts],
                prompt=t("가져올 계정을 입력하세요."),
            )
            if not targets:
                return                      # 취소했거나 비어 있다
        elif scope == "sel":
            targets = selected
            if not targets:
                messagebox.showinfo(
                    t("선택 없음"), t("목록에서 가져올 계정을 고르세요."), parent=self.root
                )
                return
        else:
            only_fav = scope == "fav"
            targets = self.cfg.targets(only_fav=only_fav)
            if not targets:
                messagebox.showinfo(
                    t("계정 없음"),
                    t("즐겨찾기로 등록된 계정이 없습니다.") if only_fav
                    else t("등록된 계정이 없습니다.\n먼저 계정을 추가하세요."),
                    parent=self.root,
                )
                return

        if not self.cfg.save_dir:
            messagebox.showinfo(
                t("저장 폴더 필요"), t("먼저 저장 폴더를 정해 주세요."), parent=self.root
            )
            self._choose_dir()
            if not self.cfg.save_dir:
                return

        self._set_busy(True)
        self.status_var.set(t("확인 중..."))
        threading.Thread(
            target=self._work,
            args=(targets, Path(self.cfg.save_dir)),
            daemon=True,
        ).start()

    def _work(self, targets: list[str], save_dir: Path) -> None:
        """워커 스레드. 여기서는 위젯을 직접 건드리지 않는다.

        로그인은 저장된 세션·자격증명을 먼저 쓴다(force_login 아님).
        계정을 바꾸려면 '로그인' 버튼을 쓴다 — 그쪽은 _work_login 이 맡는다.
        """
        # '취소' 를 누르면 이 번호가 올라가고 이 워커는 버려진다. 그 뒤로는 화면도 기록도
        # 건드리지 않는다 — 사용자가 곧바로 시작한 **새 작업**을 망치면 안 되기 때문이다.
        gen = self.job_gen

        def alive() -> bool:
            return self._alive(gen)

        def log(message: str) -> None:
            if alive():
                self.log(message)

        def status(message: str) -> None:
            if alive():
                self.status(message)

        runstate.start("gui", None, targets)
        # try 안에서 바로 return 하는 길이 여럿이라 미리 정해 둔다 (finally 가 쓴다)
        outcome = "done"
        try:
            cfg = config.load()
            status(t("로그인 확인 중..."))
            client = session.get_client(
                cfg,
                force_login=False,
                log=log,
                ask_credentials=self._ask_credentials,
                ask_two_factor=self._ask_two_factor,
            )
            self._checkpoint(gen)
            # 로그인하면서 계정이 바뀌었을 수 있으니 상단 표시를 갱신한다
            self.ui(self._reload_login_display)

            status(t("스토리 확인 중..."))
            # 반복 변수 이름은 t 를 피한다 — 번역 함수와 겹쳐 헷갈린다
            log(t("스토리 확인 중: {names}",
                  names=", ".join("@" + name for name in targets)))
            items, notes = fetch.fetch_stories(
                client, targets, skip_mediaids=history.load(),
                should_stop=lambda: self._should_stop(gen),
                on_account=lambda name, index, total: (
                    runstate.update(done_accounts=index) if alive() else None
                ),
            )
            for note in notes:
                log(f"  - {note}")
            self._checkpoint(gen)

            if not items:
                log(t("새로 저장할 스토리가 없습니다."))
                return

            log(t("새 스토리 {count}개를 찾았습니다.", count=len(items)))

            def on_thumb(done: int, total: int) -> None:
                self._checkpoint(gen)
                status(t("썸네일 불러오는 중... {done}/{total}", done=done, total=total))

            thumbs = picker.load_thumbnails(items, net.fetch_bytes, progress=on_thumb)
            self._checkpoint(gen)

            def fetch_more(accounts: list[str]):
                """선택 창의 '더 가져오기'. 그 창의 스레드에서 불린다.

                이 워커는 ui_wait 안에서 멈춰 있으므로 연결(client)을 두 스레드가
                동시에 쓰지 않는다. 이미 본 것과 저장한 것은 건너뛴다.
                """
                more, more_notes = fetch.fetch_stories(
                    client, accounts,
                    skip_mediaids=history.load() | {i.mediaid for i in items},
                    should_stop=lambda: self._should_stop(gen),
                )
                return more, picker.load_thumbnails(more, net.fetch_bytes), more_notes

            status(t("고르는 중..."))
            chosen = self.ui_wait(lambda: picker.open_picker(
                self.root, items, thumbs,
                fetch_more=fetch_more,
                known_accounts=[a.id for a in self.cfg.accounts],
            ))
            if not chosen:
                log(t("선택한 항목이 없습니다. (저장된 파일 없음)"))
                return

            status(t("{count}개 저장 중...", count=len(chosen)))
            log(t("{count}개를 {folder} 에 저장합니다.", count=len(chosen), folder=save_dir))
            ok, failed = download.download_items(
                chosen, save_dir, log=log, should_stop=lambda: self._should_stop(gen)
            )
            log(t("완료: {ok}개 저장, {failed}개 실패", ok=ok, failed=failed))
            if alive():
                runstate.update(items=ok)
                self.ui(lambda: messagebox.showinfo(
                    t("완료"),
                    t("{ok}개를 저장했습니다.\n실패 {failed}개.", ok=ok, failed=failed),
                    parent=self.root,
                ))

        except JobCancelled:
            log(t("작업을 중지했습니다."))
            outcome = "cancelled"
        except session.LoginFailed as err:
            log(str(err))
            outcome = "error"
        except Exception as err:
            # 콘솔이 없으므로, 원인을 찾을 수 있게 전체 내용을 파일로 남긴다
            log_path = _write_error_log(traceback.format_exc())
            log(t("오류가 생겼습니다: {reason}", reason=session.describe_error(err)))
            if log_path:
                log(t("  자세한 내용을 남겼습니다: {path}", path=log_path))
            outcome = "error"
        finally:
            # 버려진 워커라면 여기서 아무것도 하지 않는다. 새 작업이 이미 시작됐을 수 있고,
            # 그 작업의 busy 상태와 진행 기록을 옛 워커가 건드리면 안 된다.
            if alive():
                if self.cancel_event.is_set():
                    outcome = "cancelled"
                runstate.finish(outcome)
                self.ui(lambda: self._set_busy(False))

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    MainWindow().run()
    return 0
