"""썸네일을 보고 저장할 스토리를 고르는 창.

메인 창이 있으면 그 위에 모달 창(Toplevel)으로 뜨고,
콘솔에서 단독으로 쓸 때는 자기 자신이 최상위 창이 된다.

색을 입히는 테마에서는 고른 항목에 인스타그램 스토리처럼 그라데이션 링이 생긴다.
classic 에서는 예전처럼 단색 테두리로만 표시한다.
"""

from __future__ import annotations

import io
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

from . import config, theme
from .fetch import StoryItemInfo
from .i18n import t

THUMB_SIZE = (150, 260)   # 스토리는 세로 9:16
COLUMNS = 5

RING_THICKNESS = 3
RING_GAP = 0        # 링이 사진에 바로 붙는다
RING_RADIUS = 10    # 사진 모서리도 이 반지름으로 깎아 링과 맞춘다

ProgressFn = Callable[[int, int], None]

# 계정 목록을 받아 (새 항목, 새 썸네일, 안내 문구) 를 돌려주는 콜백.
# 네트워크를 쓰므로 선택 창이 별도 스레드에서 부른다.
FetchMoreFn = Callable[
    [list[str]],
    tuple[list[StoryItemInfo], dict[int, Optional[Image.Image]], list[str]],
]


def load_thumbnails(
    items: list[StoryItemInfo],
    fetch_bytes: Callable[[str], bytes],
    progress: Optional[ProgressFn] = None,
) -> dict[int, Optional[Image.Image]]:
    """창을 띄우기 전에 썸네일을 먼저 받아 둔다. mediaid -> PIL 이미지.

    네트워크를 쓰므로 GUI 에서는 반드시 별도 스레드에서 부를 것.
    """
    thumbs: dict[int, Optional[Image.Image]] = {}
    total = len(items)
    for index, item in enumerate(items, start=1):
        if progress:
            progress(index, total)
        try:
            image = Image.open(io.BytesIO(fetch_bytes(item.thumb_url)))
            image.thumbnail(THUMB_SIZE)
            thumbs[item.mediaid] = image.convert("RGB")
        except Exception:
            thumbs[item.mediaid] = None   # 실패하면 회색 칸으로 표시한다
    return thumbs


class _Picker:
    def __init__(
        self,
        items: list[StoryItemInfo],
        thumbs: dict[int, Optional[Image.Image]],
        parent: Optional[tk.Misc] = None,
        fetch_more: Optional[FetchMoreFn] = None,
        known_accounts: tuple = (),
        title: Optional[str] = None,
        confirm_text: Optional[str] = None,
    ):
        self.items = items
        self.thumbs = thumbs
        self.selected: dict[int, bool] = {i.mediaid: False for i in items}
        self.cells: dict[int, tk.Frame] = {}
        # 링이 있는 테마에서는 고를 때 이미지를 갈아 끼운다: mediaid -> (평소, 링)
        self.cell_images: dict[int, tuple] = {}
        self.thumb_labels: dict[int, tk.Label] = {}
        self.photos: list[ImageTk.PhotoImage] = []   # 참조를 유지해야 이미지가 안 사라진다
        self.confirmed = False
        self.parent = parent
        # 콜백을 주지 않으면 '더 가져오기' 버튼 자체가 생기지 않는다
        # (보관분 다시 보기에는 로그인된 연결이 없어 넘기지 않는다)
        self.fetch_more = fetch_more
        self.known_accounts = list(known_accounts)
        self.fetching = False
        self._hint_id: Optional[str] = None
        # 같은 창을 저장용과 삭제용으로 쓰므로 제목과 확인 단추 문구를 받는다
        self._confirm_text = confirm_text or t("저장")

        self.styled = theme.is_styled()
        p = theme.palette()
        self.bg = p["bg"]
        self.surface = p["surface"]

        if parent is None:
            # 단독으로 뜰 때는 ttk 스타일을 여기서 준비해야 한다
            # (메인 창에서 부를 때는 이미 적용돼 있다)
            self.win: tk.Misc = tk.Tk()
            theme.apply(self.win)
        else:
            # transient 로 두지 않는다. Tk 는 transient 창에서 최소화·최대화 단추와
            # 작업 표시줄 항목을 없애 버려서, 고르는 도중에 잠깐 내려 둘 수가 없다.
            # (대신 메인 창 위에 항상 떠 있지는 않는다 — 작업 표시줄에서 다시 부르면 된다)
            self.win = tk.Toplevel(parent)

        self.win.title(title or t("저장할 스토리 선택"))
        self.win.geometry("980x760")
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)   # X = 취소
        if self.bg:
            self.win.configure(bg=self.bg)

        # 최소화한 동안에는 잠금을 풀어 준다. 안 그러면 창이 내려간 채 메인 창이 잠겨 있어
        # 프로그램이 멈춘 것처럼 보인다.
        self.win.bind("<Unmap>", self._on_unmap)
        self.win.bind("<Map>", self._on_map)

        self._build_toolbar()
        self._build_scroll_area()
        self._build_grid()
        self._build_footer()
        self._refresh_count()

    # --- 최소화 -------------------------------------------------------

    def _on_unmap(self, event) -> None:
        """작업 표시줄로 내려갔으면 잠금을 푼다.

        자식 위젯의 Unmap 도 여기로 올라오므로 창 자신일 때만 본다.
        """
        if event.widget is self.win and self.win.state() == "iconic":
            try:
                self.win.grab_release()
            except tk.TclError:
                pass

    def _on_map(self, event) -> None:
        """다시 올라왔으면 잠금을 되찾는다 (단독 실행일 때는 잠글 것이 없다)."""
        if event.widget is self.win and self.parent is not None:
            try:
                self.win.grab_set()
            except tk.TclError:
                pass

    # --- 화면 구성 ---------------------------------------------------

    def _style(self, style_name: str) -> dict:
        return {"style": style_name} if self.styled else {}

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.win, padding=(14, 12))
        bar.pack(fill="x")
        self.hint_label = ttk.Label(
            bar, text=t("항목을 클릭해서 선택하세요."), **self._style("Sub.TLabel")
        )
        self.hint_label.pack(side="left")
        ttk.Button(bar, text=t("전체 해제"), command=lambda: self._set_all(False)).pack(side="right", padx=4)
        ttk.Button(bar, text=t("전체 선택"), command=lambda: self._set_all(True)).pack(side="right", padx=4)
        if self.fetch_more is not None:
            self.more_button = ttk.Button(
                bar, text=t("더 가져오기"), command=self._on_fetch_more
            )
            self.more_button.pack(side="right", padx=(4, 16))

    def _say(self, message: str) -> None:
        """안내 문구를 잠깐 보여 주고 원래 문구로 되돌린다 (창에는 로그가 없다)."""
        if self._hint_id is not None:
            try:
                self.win.after_cancel(self._hint_id)
            except tk.TclError:
                pass
            self._hint_id = None
        self.hint_label.configure(text=message)

        def restore() -> None:
            self._hint_id = None
            if self.win.winfo_exists():
                self.hint_label.configure(text=t("항목을 클릭해서 선택하세요."))

        self._hint_id = self.win.after(5000, restore)

    def _build_scroll_area(self) -> None:
        container = ttk.Frame(self.win)
        container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(container, highlightthickness=0)
        if self.bg:
            self.canvas.configure(bg=self.bg)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)

        self.body.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        # bind_all 은 부모 창까지 영향을 주므로 이 창에만 건다
        self.win.bind("<MouseWheel>", self._on_wheel)

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def _build_grid(self) -> None:
        # 계정별로 묶어서 섹션을 만든다
        by_account: dict[str, list[StoryItemInfo]] = {}
        for item in self.items:
            by_account.setdefault(item.account, []).append(item)

        for account, group in by_account.items():
            header = ttk.Frame(self.body, padding=(14, 14, 14, 4))
            header.pack(fill="x")

            ttk.Label(
                header,
                text=f"@{account}",
                font=theme.FONT_BOLD if self.styled else ("Malgun Gothic", 12, "bold"),
            ).pack(side="left")
            ttk.Label(
                header, text="  " + t("{count}개", count=len(group)), **self._style("Sub.TLabel")
            ).pack(side="left")
            ttk.Button(
                header,
                text=t("이 계정 전체 선택"),
                command=lambda g=group: self._set_group(g, True),
            ).pack(side="left", padx=10)

            grid = ttk.Frame(self.body, padding=(14, 0, 14, 10))
            grid.pack(fill="x")
            for index, item in enumerate(group):
                self._build_cell(grid, item, row=index // COLUMNS, column=index % COLUMNS)

    def _rebuild_grid(self) -> None:
        """항목이 늘어난 뒤 격자를 처음부터 다시 그린다.

        _build_grid 는 계정별로 묶어 순서대로 붙이기만 하므로, 새 항목을 뒤에 덧붙이면
        같은 계정이 두 군데로 갈라진다. 통째로 다시 그리는 편이 확실하다.
        고른 상태는 self.selected 에 있어 다시 그려도 그대로 살아 있다.
        """
        for child in self.body.winfo_children():
            child.destroy()
        self.cells.clear()
        self.cell_images.clear()
        self.thumb_labels.clear()
        self.photos.clear()      # 옛 이미지는 칸과 함께 사라졌다

        self._build_grid()
        for mediaid, on in self.selected.items():
            if on and mediaid in self.cells:
                self._paint(mediaid)
        self._refresh_count()

    def _make_cell_images(self, thumb: Image.Image) -> tuple:
        """(평소 이미지, 링 두른 이미지).

        같은 함수로 만들어 크기와 모서리 모양을 맞춘다.
        그래야 고를 때 칸이 움찔거리거나 귀퉁이가 어긋나지 않는다.
        """
        options = dict(thickness=RING_THICKNESS, gap=RING_GAP, radius=RING_RADIUS)
        return (
            theme.framed(thumb, ring=False, **options),
            theme.framed(thumb, ring=True, **options),
        )

    def _build_cell(self, parent: ttk.Frame, item: StoryItemInfo, row: int, column: int) -> None:
        p = theme.palette()
        cell_bg = self.surface if self.styled else None

        cell = tk.Frame(
            parent,
            bd=0,
            # 링이 표시를 맡으므로 색 테마에서는 테두리를 쓰지 않는다
            highlightthickness=0 if self.styled else 3,
            highlightbackground=p["cell_border_off"],
            highlightcolor=p["cell_border_off"],
            padx=4,
            pady=4,
        )
        if cell_bg:
            cell.configure(bg=cell_bg)
        cell.grid(row=row, column=column, padx=6, pady=6)

        image = self.thumbs.get(item.mediaid)
        if image is not None:
            if self.styled:
                plain_img, ringed_img = self._make_cell_images(image)
                plain = ImageTk.PhotoImage(plain_img)
                ringed = ImageTk.PhotoImage(ringed_img)
                self.photos.extend((plain, ringed))
                self.cell_images[item.mediaid] = (plain, ringed)
                thumb = tk.Label(cell, image=plain, bd=0)
            else:
                photo = ImageTk.PhotoImage(image)
                self.photos.append(photo)
                thumb = tk.Label(cell, image=photo)
            self.thumb_labels[item.mediaid] = thumb
        else:
            thumb = tk.Label(cell, text=t("(미리보기 실패)"), width=20, height=13, bg=p["thumb_fail_bg"])
        if cell_bg:
            thumb.configure(bg=cell_bg)
        thumb.pack()

        caption = f"{'▶ ' if item.is_video else ''}{item.label}"
        text = tk.Label(cell, text=caption, font=("Malgun Gothic", 9))
        if cell_bg:
            text.configure(bg=cell_bg, fg=p["text_dim"])
        text.pack(pady=(4, 0))

        for widget in (cell, thumb, text):
            widget.bind("<Button-1>", lambda e, m=item.mediaid: self._toggle(m))

        self.cells[item.mediaid] = cell

    def _build_footer(self) -> None:
        footer = ttk.Frame(self.win, padding=(14, 12))
        footer.pack(fill="x")
        self.save_button = ttk.Button(
            footer, text=self._confirm_text, command=self._confirm,
            **self._style("Accent.TButton")
        )
        self.save_button.pack(side="right", padx=4)
        ttk.Button(footer, text=t("취소"), command=self.win.destroy).pack(side="right", padx=4)
        self.count_label = ttk.Label(footer, text="", **self._style("Sub.TLabel"))
        self.count_label.pack(side="left")

    # --- 동작 -------------------------------------------------------

    def _paint(self, mediaid: int) -> None:
        on = self.selected[mediaid]
        p = theme.palette()

        images = self.cell_images.get(mediaid)
        if images:
            # 링이 있는 테마 — 이미지를 갈아 끼우는 것이 곧 선택 표시다
            self.thumb_labels[mediaid].configure(image=images[1] if on else images[0])
            return

        cell = self.cells[mediaid]
        cell.configure(
            highlightbackground=p["cell_border_on"] if on else p["cell_border_off"],
            highlightcolor=p["cell_border_on"] if on else p["cell_border_off"],
            bg=p["cell_bg_on"] if on else (self.surface or self.win.cget("bg")),
        )

    def _toggle(self, mediaid: int) -> None:
        self.selected[mediaid] = not self.selected[mediaid]
        self._paint(mediaid)
        self._refresh_count()

    def _set_all(self, on: bool) -> None:
        for mediaid in self.selected:
            self.selected[mediaid] = on
            self._paint(mediaid)
        self._refresh_count()

    def _set_group(self, group: list[StoryItemInfo], on: bool) -> None:
        for item in group:
            self.selected[item.mediaid] = on
            self._paint(item.mediaid)
        self._refresh_count()

    def _refresh_count(self) -> None:
        count = sum(self.selected.values())
        self.count_label.configure(
            text=t("{done} / {total}개 선택됨", done=count, total=len(self.items))
        )
        # '저장 (3)' / '지우기 (3)' — 문구가 무엇이든 개수만 뒤에 붙인다
        self.save_button.configure(
            text=f"{self._confirm_text} ({count})" if count else self._confirm_text
        )

    # --- 더 가져오기 -------------------------------------------------

    def _on_fetch_more(self) -> None:
        """계정을 고른 뒤 그 계정들을 다시 조회해 새 항목만 격자에 더한다.

        조회는 이 창이 가진 별도 스레드에서 한다. 원래 워커는 이 창이 닫히기를
        기다리며 멈춰 있으므로, 인스타그램 연결을 두 스레드가 동시에 쓰는 일은 없다.
        """
        if self.fetching or self.fetch_more is None:
            return
        chosen = ask_accounts(self.win, self.known_accounts,
                              prompt=t("다시 확인할 계정을 고르세요."), styled=self.styled)
        if not chosen:
            return

        self.fetching = True
        self.more_button.configure(state="disabled", text=t("가져오는 중..."))
        self._say(t("가져오는 중..."))

        box: dict = {}
        done = threading.Event()

        def work() -> None:
            try:
                box["result"] = self.fetch_more(chosen)
            except Exception as err:
                box["error"] = err
            finally:
                done.set()

        threading.Thread(target=work, daemon=True).start()
        self.win.after(100, lambda: self._poll_fetch(done, box))

    def _poll_fetch(self, done: threading.Event, box: dict) -> None:
        """메인 스레드에서 결과를 기다린다. 위젯은 여기서만 건드린다."""
        if not self.win.winfo_exists():
            return
        if not done.is_set():
            self.win.after(100, lambda: self._poll_fetch(done, box))
            return

        self.fetching = False
        self.more_button.configure(state="normal", text=t("더 가져오기"))

        if "error" in box:
            self._say(t("더 가져오지 못했습니다."))
            messagebox.showwarning(
                t("더 가져오기"), str(box["error"]), parent=self.win
            )
            return

        new_items, new_thumbs, notes = box.get("result") or ([], {}, [])
        self._add_items(new_items, new_thumbs)
        if notes:
            messagebox.showinfo(t("더 가져오기"), "\n".join(notes), parent=self.win)

    def _add_items(self, new_items: list[StoryItemInfo],
                   new_thumbs: dict[int, Optional[Image.Image]]) -> None:
        fresh = [i for i in new_items if i.mediaid not in self.selected]
        if not fresh:
            self._say(t("추가된 새 스토리가 없습니다."))
            return

        self.items.extend(fresh)
        self.items.sort(key=lambda i: (i.account, i.taken_at))
        for item in fresh:
            self.selected[item.mediaid] = False
            self.thumbs[item.mediaid] = new_thumbs.get(item.mediaid)

        self._rebuild_grid()
        self._say(t("새 스토리 {count}개를 추가했습니다.", count=len(fresh)))

    def _confirm(self) -> None:
        self.confirmed = True
        self.win.destroy()

    def run(self) -> list[StoryItemInfo]:
        if self.parent is None:
            self.win.mainloop()
        else:
            self.win.grab_set()          # 모달 — 고르는 동안 메인 창 잠금
            self.parent.wait_window(self.win)
        if not self.confirmed:
            return []
        return [i for i in self.items if self.selected[i.mediaid]]


class _AccountPickDialog(tk.Toplevel):
    """'더 가져오기' 에서 어느 계정을 다시 볼지 고르는 작은 모달 창."""

    def __init__(self, parent: tk.Misc, known: list[str], prompt: str, styled: bool):
        super().__init__(parent)
        self.result: list[str] = []
        self.known = list(known)

        self.title(t("계정 선택"))
        self.resizable(False, False)
        self.transient(parent)
        p = theme.palette()
        if p["bg"]:
            self.configure(bg=p["bg"])

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=prompt, font=theme.FONT).pack(anchor="w")

        # 메인 창 계정 목록과 같은 조작: 여러 개 고르기·끌어서 고르기·더블클릭 해제.
        # 고르는 즉시 아래 입력칸에 더해진다.
        list_row = ttk.Frame(frame)
        list_row.pack(fill="both", expand=True, pady=(8, 0))
        self.listbox = tk.Listbox(
            list_row, selectmode="extended", font=theme.FONT, height=8,
            activestyle="none", exportselection=False,
        )
        for name in self.known:
            self.listbox.insert("end", f"@{name}")
        options = dict(
            bg=p["surface_alt"], fg=p["text"],
            selectbackground=p["list_select_bg"], selectforeground=p["list_select_fg"],
            highlightthickness=0 if styled else None, bd=0 if styled else None,
        )
        real = {key: value for key, value in options.items() if value is not None}
        if real:
            self.listbox.configure(**real)
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._take_selected)
        self.listbox.bind("<Double-Button-1>", self._on_double_click)

        side = ttk.Frame(list_row, padding=(10, 0, 0, 0))
        side.pack(side="left", fill="y")
        self.select_all_button = ttk.Button(
            side, text=t("전체 선택"), command=self._toggle_select_all
        )
        self.select_all_button.pack(fill="x")

        ttk.Label(frame, text=t("가져올 계정"), font=theme.FONT).pack(anchor="w", pady=(10, 2))
        self.typed = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self.typed, width=32, font=theme.FONT)
        entry.pack(fill="x")
        ttk.Label(frame, text=t("여러 개는 띄어쓰기로 구분하세요."), font=theme.FONT_SMALL,
                  **({"style": "Sub.TLabel"} if styled else {})).pack(anchor="w", pady=(2, 0))

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e", pady=(14, 0))
        ttk.Button(buttons, text=t("취소"), command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text=t("가져오기"), command=self._ok,
                   **({"style": "Accent.TButton"} if styled else {})).pack(side="right", padx=4)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        entry.focus_set()
        self.grab_set()
        parent.wait_window(self)

    def _names(self) -> list[str]:
        """입력칸에 적힌 계정들. 여기 보이는 것이 곧 가져올 것이다."""
        names: list[str] = []
        for part in self.typed.get().replace(",", " ").split():
            name = config.normalize_id(part)
            if name and name not in names:
                names.append(name)
        return names

    def _take_selected(self, event=None) -> None:
        """지금 골라진 계정을 모두 입력칸에 더한다 (이미 있는 것은 그대로 둔다).

        끄는 동안에도 계속 불리므로, 지나친 계정이 차곡차곡 쌓인다.
        선택을 풀어도 입력칸에서는 지우지 않는다 — 필요 없으면 입력칸에서 지우면 된다.
        입력칸에는 '@' 없이 이름만 넣는다.
        """
        have = self._names()
        added = [
            self.known[i] for i in self.listbox.curselection()
            if 0 <= i < len(self.known) and self.known[i] not in have
        ]
        if added:
            current = self.typed.get().strip()
            joined = " ".join(added)
            self.typed.set(f"{current} {joined}" if current else joined)
        self._refresh_select_all()

    def _on_double_click(self, event):
        """이미 고른 항목을 더블클릭하면 선택을 푼다 (메인 창 계정 목록과 같다)."""
        index = self.listbox.nearest(event.y)
        if index >= 0 and index in self.listbox.curselection():
            self.listbox.selection_clear(index)
            self._refresh_select_all()
        return "break"          # 기본 동작이 뒤따르지 않게

    def _toggle_select_all(self) -> None:
        total = self.listbox.size()
        if total == 0:
            return
        if len(self.listbox.curselection()) == total:
            self.listbox.selection_clear(0, "end")
            self._refresh_select_all()      # 푼 것은 입력칸에서 지우지 않는다
        else:
            self.listbox.selection_set(0, "end")
            self._take_selected()

    def _refresh_select_all(self) -> None:
        """모두 골라져 있으면 '전체 해제', 아니면 '전체 선택'."""
        total = self.listbox.size()
        all_selected = total > 0 and len(self.listbox.curselection()) == total
        self.select_all_button.configure(
            text=t("전체 해제") if all_selected else t("전체 선택")
        )

    def _ok(self) -> None:
        chosen = self._names()
        if not chosen:
            messagebox.showinfo(
                t("계정 선택"), t("가져올 계정을 고르거나 입력하세요."), parent=self
            )
            return
        self.result = chosen
        self.destroy()


def ask_accounts(parent: tk.Misc, known, prompt: Optional[str] = None,
                 styled: Optional[bool] = None) -> list[str]:
    """가져올 계정을 받는 작은 모달 창. 취소하면 빈 목록.

    선택 창의 '더 가져오기' 와 메인 창의 '직접 입력' 이 같이 쓴다.
    반드시 메인 스레드에서 부를 것.
    """
    return _AccountPickDialog(
        parent,
        list(known),
        prompt or t("가져올 계정을 입력하세요."),
        theme.is_styled() if styled is None else styled,
    ).result


def open_picker(
    parent: tk.Misc,
    items: list[StoryItemInfo],
    thumbs: dict[int, Optional[Image.Image]],
    fetch_more: Optional[FetchMoreFn] = None,
    known_accounts: tuple = (),
    title: Optional[str] = None,
    confirm_text: Optional[str] = None,
) -> list[StoryItemInfo]:
    """이미 받아 둔 썸네일로 선택 창을 띄운다 (GUI 용). 반드시 메인 스레드에서 호출.

    fetch_more 를 주면 창 안에서 계정을 골라 더 가져올 수 있다.
    title·confirm_text 를 주면 저장이 아닌 다른 일(예: 보관분 골라 지우기)에도 쓸 수 있다.
    """
    return _Picker(
        items, thumbs, parent=parent, fetch_more=fetch_more, known_accounts=known_accounts,
        title=title, confirm_text=confirm_text,
    ).run()


def pick(items: list[StoryItemInfo], fetch_bytes: Callable[[str], bytes]) -> list[StoryItemInfo]:
    """썸네일을 받아 선택 창을 띄운다 (콘솔 용). 취소하면 빈 목록."""
    def show(done: int, total: int) -> None:
        print("\r" + t("썸네일 불러오는 중... {done}/{total}", done=done, total=total),
              end="", flush=True)

    thumbs = load_thumbnails(items, fetch_bytes, progress=show)
    print()
    return _Picker(items, thumbs).run()
