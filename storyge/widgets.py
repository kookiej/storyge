"""직접 그린 작은 위젯들.

tkinter 기본 위젯으로는 만들 수 없는 모양이라 Canvas 와 Label 로 직접 그린다.
색은 넘겨받아 쓰므로 테마가 바뀌면 새로 만들어 주면 된다.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from . import theme

# 애니메이션: 약 14프레임 x 16ms = 0.22초
_FRAMES = 14
_FRAME_MS = 16


class ToggleSwitch(tk.Canvas):
    """알약 모양 on/off 스위치. 글자 없이 손잡이 안의 아이콘으로 상태를 보여 준다.

    누르면 손잡이가 부드럽게 미끄러지고, **움직임이 끝난 뒤에** command 를 부른다.
    (command 가 창을 다시 그리는 경우가 있어서, 먼저 부르면 애니메이션이 잘려 버린다)
    """

    def __init__(
        self,
        parent,
        is_on: bool = False,
        command: Optional[Callable[[bool], None]] = None,
        on_icon: str = "☀",
        off_icon: str = "☾",
        on_color: str = "#0095F6",
        off_color: str = "#8E8E8E",
        knob_color: str = "#FFFFFF",
        icon_color: str = "#262626",
        bg: Optional[str] = None,
        width: int = 52,
        height: int = 28,
        icon_size: Optional[int] = None,
    ):
        super().__init__(parent, width=width, height=height, highlightthickness=0, bd=0, takefocus=0)
        if bg:
            self.configure(bg=bg)

        self.is_on = bool(is_on)
        self.command = command
        self.on_icon, self.off_icon = on_icon, off_icon
        self.on_color, self.off_color = on_color, off_color
        self._enabled = True
        self._after: Optional[str] = None
        self._pos = 1.0 if self.is_on else 0.0   # 손잡이 위치 0.0~1.0

        pad = 2
        track_h = height - pad * 2
        knob_r = track_h / 2 - 2
        center_y = height / 2

        # 알약 = 양끝 원 두 개 + 가운데 사각형 (Canvas 는 둥근 사각형을 못 그린다)
        #
        # 사각형 아래를 1 더 준다. 같은 좌표를 줘도 Tk 는 **사각형은 마지막 행을 빼고,
        # 타원은 넣어서** 칠한다. 그대로 두면 가운데가 양끝 반원보다 1px 얇아
        # 알약 허리가 잘록해 보인다.
        self._track = [
            self.create_oval(pad, pad, pad + track_h, pad + track_h, width=0),
            self.create_oval(width - pad - track_h, pad, width - pad, pad + track_h, width=0),
            self.create_rectangle(pad + track_h / 2, pad,
                                  width - pad - track_h / 2, pad + track_h + 1, width=0),
        ]
        self._knob = self.create_oval(0, 0, 0, 0, fill=knob_color, width=0)
        # 'KR'/'EN' 처럼 두 글자를 넣을 때는 기본 크기로는 손잡이를 넘치므로 조절할 수 있게 둔다
        self._icon = self.create_text(
            0, 0, text="", fill=icon_color,
            font=("Segoe UI Symbol", icon_size if icon_size else int(knob_r) + 1),
        )

        self._knob_r = knob_r
        self._center_y = center_y
        self._min_x = pad + track_h / 2
        self._max_x = width - pad - track_h / 2

        self.bind("<Button-1>", self._on_click)
        self.configure(cursor="hand2")
        self._render()

    # --- 그리기 ---

    def _render(self) -> None:
        color = theme.mix_hex(self.off_color, self.on_color, self._pos)
        for item in self._track:
            self.itemconfig(item, fill=color)

        x = self._min_x + (self._max_x - self._min_x) * self._pos
        r = self._knob_r
        self.coords(self._knob, x - r, self._center_y - r, x + r, self._center_y + r)
        self.coords(self._icon, x, self._center_y)
        self.itemconfig(self._icon, text=self.on_icon if self._pos > 0.5 else self.off_icon)

    # --- 동작 ---

    def _on_click(self, _event=None) -> None:
        if not self._enabled or self._after is not None:
            return          # 움직이는 중에는 무시 (연타해도 손잡이가 튀지 않게)
        self.toggle()

    def toggle(self) -> None:
        self.set_state(not self.is_on, animate=True, notify=True)

    def set_state(self, is_on: bool, animate: bool = True, notify: bool = False) -> None:
        self.is_on = bool(is_on)
        target = 1.0 if self.is_on else 0.0
        if not animate:
            self._pos = target
            self._render()
            if notify and self.command:
                self.command(self.is_on)
            return
        self._start, self._target = self._pos, target
        self._frame = 0
        self._notify = notify
        self._step()

    def _step(self) -> None:
        self._frame += 1
        t = self._frame / _FRAMES
        eased = 1 - (1 - t) ** 3            # 끝에서 부드럽게 멎는 곡선
        self._pos = self._start + (self._target - self._start) * eased
        self._render()

        if self._frame < _FRAMES:
            self._after = self.after(_FRAME_MS, self._step)
            return

        self._pos = self._target
        self._render()
        self._after = None
        if self._notify and self.command:
            self.command(self.is_on)

    # --- 기존 코드가 쓰던 configure(state=...) 를 받아 준다 ---

    def configure(self, cnf=None, **kw):
        state = kw.pop("state", None)
        if state is not None:
            self._enabled = str(state) == "normal"
            self.configure(cursor="hand2" if self._enabled else "arrow")
        if cnf is None and not kw:
            return None
        return super().configure(cnf, **kw)

    config = configure


class FlatToggle(tk.Label):
    """배경 없이 글자만 보이는 토글 버튼.

    ttk 체크박스는 clam 테마에서 표식 모양(체크/X)을 바꿀 수 없어서
    (indicator 엘리먼트가 색 옵션만 받는다) 직접 그린다.
    누르면 variable 이 뒤집히고, 상태에 따라 글자와 색이 바뀐다.
    """

    def __init__(
        self,
        parent,
        variable: tk.BooleanVar,
        on_text: str,
        off_text: str,
        on_color: str = "#0095F6",
        off_color: str = "#8E8E8E",
        bg: Optional[str] = None,
        size: int = 11,
        font: Optional[tuple] = None,
        command: Optional[Callable[[bool], None]] = None,
    ):
        super().__init__(
            parent,
            font=font or ("Segoe UI Symbol", size),
            bd=0,
            highlightthickness=0,
            padx=6,
            pady=0,
            cursor="hand2",
        )
        if bg:
            self.configure(bg=bg, activebackground=bg)

        self.variable = variable
        self.on_text, self.off_text = on_text, off_text
        self.on_color, self.off_color = on_color, off_color
        self.command = command
        self._enabled = True

        self.bind("<Button-1>", self._on_click)
        variable.trace_add("write", lambda *_: self._render())
        self._render()

    def _on_click(self, _event=None) -> None:
        if not self._enabled:
            return
        self.variable.set(not self.variable.get())
        if self.command:
            self.command(bool(self.variable.get()))

    def _render(self) -> None:
        on = bool(self.variable.get())
        self.configure(
            text=self.on_text if on else self.off_text,
            fg=self.on_color if on else self.off_color,
        )

    def configure(self, cnf=None, **kw):
        state = kw.pop("state", None)
        if state is not None:
            self._enabled = str(state) == "normal"
        if cnf is None and not kw:
            return None
        return super().configure(cnf, **kw)

    config = configure


class StarButton(FlatToggle):
    """배경 없이 별 모양만 보이는 토글 버튼. 체크박스를 대신한다."""

    def __init__(
        self,
        parent,
        variable: tk.BooleanVar,
        on_color: str = "#0095F6",
        off_color: str = "#8E8E8E",
        bg: Optional[str] = None,
        size: int = 15,
    ):
        super().__init__(
            parent,
            variable=variable,
            on_text="★",
            off_text="☆",
            on_color=on_color,
            off_color=off_color,
            bg=bg,
            size=size,
        )
