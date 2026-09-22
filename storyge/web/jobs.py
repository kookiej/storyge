"""웹 버전의 오래 걸리는 일 (가져오기 / 저장).

창 버전은 워커 스레드 + 80ms 큐 펌프(gui._drain_queue)로 이 문제를 푼다.
웹도 같은 모양이다 — 백그라운드 스레드가 일하고, 브라우저가 0.5초마다 물어본다.

SSE 를 쓰지 않는 이유: Flask 개발 서버는 열린 스트림마다 워커 스레드를 붙잡고,
연결이 끊기면 조용히 멈춘 채로 남는다. 진행 보고가 계정 단위라 계정 12개면
의미 있는 갱신이 12번뿐이므로 폴링으로 충분하다.

화면을 새로 열면(새로고침) 돌던 작업을 이어받지 않고 **멈추고 처음부터** 시작한다
(/api/reset). 작업을 이어받을 수는 있지만, 반쯤 찬 격자를 물려받는 것보다
깨끗한 화면에서 다시 누르는 쪽이 헷갈리지 않는다는 판단이다.

**job.items 가 유일한 진실이다.** 브라우저는 주소를 절대 보지 못하고 mediaid 만
돌려준다. 썸네일도 저장도 전부 여기 있는 목록에서 찾아 쓴다.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .. import download, filename, history, sources
from ..model import StoryItemInfo

# 끝난 작업을 붙들고 있는 시간. 썸네일 주소가 여기 있으므로 화면이 살아 있는
# 동안에는 남아 있어야 하지만, 영원히 쌓이면 안 된다.
KEEP_FINISHED = 30 * 60
MAX_JOBS = 8


def item_json(item: StoryItemInfo) -> dict:
    """브라우저로 넘길 모양.

    **mediaid 는 반드시 문자열이다.** 진짜 인스타 pk 는 10^18 규모라
    자바스크립트 Number(2^53)로는 정확히 표현되지 않는다.
    주소(thumb_url / media_url)는 넘기지 않는다 — 썸네일은 프록시로만 나간다.
    어느 사이트에서 왔는지(item.source)도 넘기지 않는다 — 사용자가 사이트를
    고르지 않으므로 화면에 쓸 데가 없다. 서버 쪽 자료형에는 그대로 남아 있다.
    """
    return {
        "mediaid": str(item.mediaid),
        "account": item.account,
        "label": item.label,
        "taken_at": item.taken_at.isoformat(timespec="seconds"),
        "time_basis": item.time_basis,
        "is_video": item.is_video,
    }


@dataclass
class Job:
    id: str
    kind: str                                   # "fetch" | "save"
    state: str = "running"                      # running | done | cancelled | error
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    accounts: list[str] = field(default_factory=list)
    done_accounts: int = 0
    current_account: Optional[str] = None

    items: list[StoryItemInfo] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    total: int = 0                              # 저장 작업의 전체 개수
    results: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    # 수집 사이트를 다 해 보고도 못 가져왔는지. 화면은 이것으로 '사이트가 막혔다' 와
    # '올라온 스토리가 없다' 를 갈라 말한다.
    blocked: bool = False

    cancel: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    _index: dict[int, StoryItemInfo] = field(default_factory=dict)

    # --- 워커가 쓰는 자리 ---------------------------------------------

    def add_items(self, items: Iterable[StoryItemInfo]) -> None:
        """이미 들어 있는 것은 건너뛴다 (계정별 콜백과 마지막 반환이 겹쳐도 안전)."""
        with self.lock:
            for item in items:
                if item.mediaid in self._index:
                    continue
                self._index[item.mediaid] = item
                self.items.append(item)

    def finish(self, state: str, error: Optional[str] = None) -> None:
        with self.lock:
            self.state = state
            self.error = error
            self.finished_at = time.time()
            self.current_account = None

    # --- 요청 스레드가 읽는 자리 ---------------------------------------

    def by_mediaid(self, mediaid: int) -> Optional[StoryItemInfo]:
        with self.lock:
            return self._index.get(mediaid)

    def pick(self, mediaids: Iterable[int]) -> list[StoryItemInfo]:
        with self.lock:
            found = [self._index.get(m) for m in mediaids]
        return [i for i in found if i is not None]

    @property
    def running(self) -> bool:
        return self.state == "running"

    def snapshot(self) -> dict:
        with self.lock:
            base = {
                "job_id": self.id,
                "kind": self.kind,
                "state": self.state,
                "notes": list(self.notes),
                "error": self.error,
            }
            if self.kind == "fetch":
                base.update({
                    "total": len(self.accounts),
                    "done": self.done_accounts,
                    "current_account": self.current_account,
                    "blocked": self.blocked,
                    "items": [item_json(i) for i in self.items],
                })
            else:
                done = len(self.results)
                base.update({
                    "total": self.total,
                    "done": done,
                    "ok": sum(1 for r in self.results if r["status"] == "saved"),
                    "existed": sum(1 for r in self.results if r["status"] == "exists"),
                    "failed": sum(1 for r in self.results if r["status"] == "failed"),
                    "results": list(self.results),
                })
            return base


class JobRegistry:
    """이 서버가 들고 있는 작업들. 1인용이라 프로세스 안에만 둔다."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, kind: str, accounts: Iterable[str] = ()) -> Job:
        job = Job(id=uuid.uuid4().hex[:8], kind=kind, accounts=list(accounts))
        with self._lock:
            self._prune()
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def running(self, kind: str) -> Optional[Job]:
        """같은 종류로 지금 돌고 있는 작업. 두 번 누르는 것을 막는 데 쓴다."""
        with self._lock:
            for job in self._jobs.values():
                if job.kind == kind and job.state == "running":
                    return job
        return None

    def running_all(self) -> list[Job]:
        """지금 돌고 있는 작업 전부. 화면을 새로 열 때 싹 멈추는 데 쓴다."""
        with self._lock:
            return [job for job in self._jobs.values() if job.state == "running"]

    def _prune(self) -> None:
        """끝난 지 오래된 것부터 버린다. 호출하는 쪽이 이미 lock 을 들고 있다."""
        now = time.time()
        stale = [
            key for key, job in self._jobs.items()
            if job.finished_at and now - job.finished_at > KEEP_FINISHED
        ]
        for key in stale:
            del self._jobs[key]

        if len(self._jobs) >= MAX_JOBS:
            done = sorted(
                (j for j in self._jobs.values() if not j.running),
                key=lambda j: j.finished_at or j.started_at,
            )
            for job in done[: len(self._jobs) - MAX_JOBS + 1]:
                self._jobs.pop(job.id, None)


# ---------------------------------------------------------------- 워커

def run_fetch_job(job: Job, targets: list[str], skip_mediaids: set[int],
                  source_id: str) -> None:
    """스토리 가져오기. 별도 스레드에서 돈다."""

    def on_account(account: str, index: int, total: int) -> None:
        with job.lock:
            job.current_account = account
            job.done_accounts = index

    def on_items(_account: str, found: list[StoryItemInfo]) -> None:
        job.add_items(found)

    try:
        source = sources.get(source_id)
        items, notes = source.fetch(
            targets,
            skip_mediaids=skip_mediaids,
            should_stop=job.cancel.is_set,
            on_account=on_account,
            on_items=on_items,
        )
        # on_items 로 이미 들어왔지만, 콜백을 안 쓰는 소스도 있을 수 있으므로 맞춰 둔다
        job.add_items(items)
        with job.lock:
            job.notes = list(notes)
            job.done_accounts = len(job.accounts)
            # 선택 속성이라 없는 소스도 있을 수 있다 (테스트의 가짜 소스 등)
            job.blocked = bool(getattr(source, "blocked", False))
        job.finish("cancelled" if job.cancel.is_set() else "done")
    except Exception as err:  # noqa: BLE001 - 워커에서 새어 나가면 작업이 영원히 running 이다
        traceback.print_exc()
        job.finish("error", str(err) or type(err).__name__)


def run_save_job(job: Job, chosen: list[StoryItemInfo], save_dir: Path,
                 template: Optional[str]) -> None:
    """고른 것을 저장 폴더에 내려받는다. 별도 스레드에서 돈다.

    download.download_items 를 쓰지 않고 save_one 을 직접 부른다 — 번역된 로그
    문장을 되파싱하는 대신 항목마다 구조화된 결과를 만들기 위해서다.
    """
    try:
        save_dir.mkdir(parents=True, exist_ok=True)
        names = filename.build_names(chosen, save_dir, template)

        saved_ids: list[int] = []
        for item in sorted(chosen, key=lambda i: (i.account, i.taken_at)):
            if job.cancel.is_set():
                break
            stem = names[item.mediaid]
            row = {"mediaid": str(item.mediaid), "account": item.account, "name": stem}
            try:
                path, downloaded = download.save_one(item, save_dir, stem)
            except Exception as err:  # noqa: BLE001 - 하나가 실패해도 나머지는 계속
                row.update(status="failed", reason=str(err) or type(err).__name__)
                with job.lock:
                    job.results.append(row)
                continue

            row.update(name=path.name, status="saved" if downloaded else "exists")
            with job.lock:
                job.results.append(row)
            saved_ids.append(item.mediaid)

        if saved_ids:
            # 중간에 멈춰도 그때까지 받은 것은 기록한다 (다음에 또 받지 않게)
            history.add(saved_ids)

        job.finish("cancelled" if job.cancel.is_set() else "done")
    except Exception as err:  # noqa: BLE001
        traceback.print_exc()
        job.finish("error", str(err) or type(err).__name__)


def start(job: Job, target, *args) -> None:
    """워커 스레드를 띄운다."""
    thread = threading.Thread(target=target, args=(job, *args), daemon=True)
    thread.start()
