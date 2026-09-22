"""웹 버전의 HTTP 창구.

규칙 두 가지만 기억하면 된다.

1. **mediaid 는 문자열로 오간다.** 진짜 인스타 pk 는 10^18 규모라 자바스크립트
   Number 로는 정확히 표현되지 않는다. 받는 즉시 int() 로 되돌린다.
2. **주소를 받는 엔드포인트가 하나도 없다.** 썸네일은 job_id + mediaid 로만
   찾는다. 서버가 임의의 주소를 대신 요청하게 만들 파라미터가 아예 없다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from flask import Blueprint, Response, current_app, jsonify, request

from .. import config, filename, history, net, paths
from ..i18n import t
from . import jobs

bp = Blueprint("api", __name__, url_prefix="/api")


def registry() -> jobs.JobRegistry:
    return current_app.extensions["storyge_jobs"]


def fail(message: str, status: int = 400, **extra):
    payload = {"error": message}
    payload.update(extra)
    return jsonify(payload), status


def body() -> dict:
    raw = request.get_json(silent=True)
    return raw if isinstance(raw, dict) else {}


def as_mediaid(text) -> Optional[int]:
    try:
        return int(str(text))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 상태

def config_json(cfg: config.Config) -> dict:
    save_dir = Path(cfg.save_dir) if cfg.save_dir else None
    return {
        "save_dir": cfg.save_dir or "",
        "save_dir_ok": bool(save_dir and save_dir.is_dir()),
        "theme": cfg.theme if cfg.theme in ("dark", "light") else "dark",
        "lang": cfg.lang,
        "confirm_delete": cfg.confirm_delete,
        "web_source": cfg.web_source,
        "use_filename_template": cfg.use_filename_template,
        "filename_template": cfg.filename_template,
    }


def accounts_json(cfg: config.Config) -> list[dict]:
    # 즐겨찾기(a.fav)는 내려보내지 않는다 — exe 전용 기능이라 웹 화면이 다루지 않는다.
    # 설정 파일에는 그대로 남고, config.save 가 읽은 값을 다시 쓰므로 지워지지 않는다.
    return [{"id": a.id} for a in cfg.accounts]


@bp.post("/reset")
def reset():
    """화면을 새로 열 때 돌던 작업을 전부 멈춘다.

    새로고침하면 하던 일을 이어받는 대신 깨끗한 화면에서 다시 시작한다.
    취소는 계정 사이·파일 사이에서만 일어나므로 반쪽 파일은 남지 않는다.
    """
    stopped = registry().running_all()
    for job in stopped:
        job.cancel.set()
    return jsonify({"stopped": [job.id for job in stopped]})


@bp.get("/state")
def state():
    """한 번 불러 화면 전체를 채운다."""
    cfg = config.load()
    running = registry().running("fetch")
    return jsonify({
        "config": config_json(cfg),
        "accounts": accounts_json(cfg),
        # 수집 방식 목록은 내보내지 않는다 — 화면에서 고르지 않는다.
        # auto 가 막힌 사이트를 알아서 건너뛰고, config.json 으로만 고정할 수 있다.
        #
        # 묶음 이름과 설명은 **한국어 원문 그대로** 내보낸다 — 여기서 t() 로 번역해
        # 버리면 언어를 바꿀 때 다시 물어봐야 한다. 화면이 window.I18N 으로 칠하므로
        # 새로고침 없이 그 자리에서 바뀐다 (views.index 의 i18n_table 참고).
        "tokens": [
            {"token": token, "group": group, "description": desc}
            for token, group, desc in filename.TOKENS
        ],
        "history_count": len(history.load()),
        "job": running.snapshot() if running else None,
    })


# ---------------------------------------------------------------- 가져오기

@bp.post("/fetch")
def fetch_start():
    cfg = config.load()
    data = body()

    asked = data.get("accounts")
    if isinstance(asked, list) and asked:
        targets = []
        for raw in asked:
            name = config.normalize_id(str(raw))
            if name and name not in targets:
                targets.append(name)
    else:
        # 즐겨찾기로 거르지 않는다 — 웹 화면에는 즐겨찾기가 없다 (exe 전용).
        targets = cfg.targets()

    if not targets:
        return fail(t("확인할 계정이 없습니다. 계정을 먼저 추가해 주세요."))

    existing = registry().running("fetch")
    if existing:
        return fail(t("이미 가져오는 중입니다."), 409, job_id=existing.id)

    skip = history.load() if data.get("skip_downloaded", True) else set()
    source_id = str(data.get("source") or cfg.web_source or "auto")

    job = registry().create("fetch", targets)
    jobs.start(job, jobs.run_fetch_job, targets, skip, source_id)
    return jsonify({"job_id": job.id, "accounts": targets}), 202


@bp.get("/fetch/<job_id>")
def fetch_state(job_id: str):
    job = registry().get(job_id)
    if job is None or job.kind != "fetch":
        return fail(t("그 작업을 찾을 수 없습니다."), 404)
    return jsonify(job.snapshot())


@bp.post("/fetch/<job_id>/cancel")
def fetch_cancel(job_id: str):
    job = registry().get(job_id)
    if job is None or job.kind != "fetch":
        return fail(t("그 작업을 찾을 수 없습니다."), 404)
    # 계정과 계정 사이에서 멈춘다. 조회 한 건이 도중에 끊기지는 않는다.
    job.cancel.set()
    return jsonify({"job_id": job.id, "state": job.state})


# ---------------------------------------------------------------- 썸네일

# 주소가 몇 시간이면 죽으므로, 테마를 바꿔 다시 그릴 때마다 CDN 을 때리지 않도록
# 잠깐 들고 있는다. mediaid 로만 키를 잡는다.
_CACHE: "OrderedDict[int, tuple[str, bytes]]" = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 200


def _cached(mediaid: int):
    with _CACHE_LOCK:
        found = _CACHE.get(mediaid)
        if found is not None:
            _CACHE.move_to_end(mediaid)
        return found


def _remember(mediaid: int, kind: str, blob: bytes) -> None:
    with _CACHE_LOCK:
        _CACHE[mediaid] = (kind, blob)
        _CACHE.move_to_end(mediaid)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


@bp.get("/thumb/<job_id>/<mediaid>")
def thumb(job_id: str, mediaid: str):
    """미리보기 이미지를 서버가 대신 받아 넘긴다.

    인스타 CDN 이미지는 브라우저에서 직접 부르면 referer/CORS 로 자주 막힌다.
    **키는 job_id + mediaid 뿐이다** — 주소를 파라미터로 받지 않으므로 서버가
    엉뚱한 곳을 대신 요청하게 만들 방법이 없다.
    """
    key = as_mediaid(mediaid)
    job = registry().get(job_id)
    if key is None or job is None:
        return fail(t("그 미리보기를 찾을 수 없습니다."), 404)
    item = job.by_mediaid(key)
    if item is None:
        return fail(t("그 미리보기를 찾을 수 없습니다."), 404)

    hit = _cached(key)
    if hit is None:
        try:
            upstream = net.get_session().get(item.thumb_url, timeout=net.TIMEOUT)
            upstream.raise_for_status()
        except Exception:  # noqa: BLE001 - 화면은 실패한 칸을 회색으로 보여 준다
            return fail(t("미리보기를 가져오지 못했습니다."), 502)
        hit = (upstream.headers.get("Content-Type", "image/jpeg"), upstream.content)
        _remember(key, *hit)

    kind, blob = hit
    return Response(blob, content_type=kind,
                    headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------- 저장

@bp.post("/save")
def save_start():
    cfg = config.load()
    data = body()

    if not cfg.save_dir:
        return fail(t("저장 폴더를 먼저 정해 주세요."))
    save_dir = Path(cfg.save_dir).expanduser()

    source_job = registry().get(str(data.get("job_id") or ""))
    if source_job is None or source_job.kind != "fetch":
        return fail(t("그 작업을 찾을 수 없습니다."), 404)

    wanted = [as_mediaid(m) for m in data.get("mediaids") or []]
    chosen = source_job.pick([m for m in wanted if m is not None])
    if not chosen:
        return fail(t("고른 스토리가 없습니다."))

    existing = registry().running("save")
    if existing:
        return fail(t("이미 저장하는 중입니다."), 409, job_id=existing.id)

    job = registry().create("save")
    job.total = len(chosen)
    template = cfg.filename_template if cfg.use_filename_template else None
    jobs.start(job, jobs.run_save_job, chosen, save_dir, template)
    return jsonify({"job_id": job.id, "total": job.total}), 202


@bp.get("/save/<job_id>")
def save_state(job_id: str):
    job = registry().get(job_id)
    if job is None or job.kind != "save":
        return fail(t("그 작업을 찾을 수 없습니다."), 404)
    return jsonify(job.snapshot())


@bp.post("/save/<job_id>/cancel")
def save_cancel(job_id: str):
    job = registry().get(job_id)
    if job is None or job.kind != "save":
        return fail(t("그 작업을 찾을 수 없습니다."), 404)
    job.cancel.set()
    return jsonify({"job_id": job.id, "state": job.state})


# ---------------------------------------------------------------- 설정

@bp.get("/settings")
def settings_read():
    return jsonify({"ok": True, "config": config_json(config.load())})


@bp.post("/settings")
def settings_write():
    cfg = config.load()
    data = body()
    errors: dict[str, str] = {}
    warnings: list[str] = []

    if "save_dir" in data:
        checked = _check_save_dir(str(data["save_dir"] or ""))
        if checked["ok"]:
            cfg.save_dir = checked["resolved"]
        else:
            errors["save_dir"] = checked["error"]

    if "theme" in data and data["theme"] in ("dark", "light"):
        cfg.theme = data["theme"]

    if "lang" in data and data["lang"] in ("ko", "en"):
        cfg.lang = data["lang"]
        # i18n 은 모듈 전역이라 요청마다 다를 수 없다. 1인용 로컬 도구라 괜찮다.
        from .. import i18n
        i18n.set_lang(cfg.lang)

    if "confirm_delete" in data:
        cfg.confirm_delete = bool(data["confirm_delete"])

    if "web_source" in data and data["web_source"] in config.WEB_SOURCES:
        cfg.web_source = data["web_source"]

    if "use_filename_template" in data:
        cfg.use_filename_template = bool(data["use_filename_template"])

    if "filename_template" in data:
        template = str(data["filename_template"] or "").strip()
        if cfg.use_filename_template:
            bad, warn = filename.validate(template)
            warnings.extend(warn)
            if bad:
                errors["filename_template"] = bad[0]
            else:
                cfg.filename_template = template
        else:
            # 꺼 둔 상태에서는 초안으로만 들고 있는다 (검사하지 않는다)
            cfg.filename_template = template

    if errors:
        return jsonify({"ok": False, "errors": errors, "warnings": warnings,
                        "config": config_json(config.load())}), 400

    config.save(cfg)
    return jsonify({"ok": True, "errors": {}, "warnings": warnings,
                    "config": config_json(cfg)})


def _check_save_dir(text: str) -> dict:
    """저장 폴더로 쓸 수 있는지 본다. 브라우저는 폴더 대화상자를 못 열기 때문에
    직접 적은 경로를 여기서 꼼꼼히 확인해 준다."""
    raw = text.strip().strip('"')
    if not raw:
        return {"ok": False, "error": t("저장 폴더를 적어 주세요.")}

    try:
        path = Path(raw).expanduser()
    except (OSError, ValueError):
        return {"ok": False, "error": t("경로를 읽을 수 없습니다.")}

    if not path.is_absolute():
        return {"ok": False, "error": t("전체 경로를 적어 주세요 (예: D:\\스토리).")}

    try:
        resolved = path.resolve()
    except OSError:
        return {"ok": False, "error": t("경로를 읽을 수 없습니다.")}

    if resolved == paths.DATA_DIR.resolve():
        return {"ok": False, "error": t("data 폴더는 저장 폴더로 쓸 수 없습니다.")}

    existed = resolved.is_dir()
    try:
        resolved.mkdir(parents=True, exist_ok=True)
        probe = resolved / ".storyge_write_test"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as err:
        return {"ok": False, "error": t("그 폴더에 쓸 수 없습니다 ({reason}).",
                                        reason=str(err))}

    return {"ok": True, "resolved": str(resolved), "existed": existed, "error": ""}


@bp.post("/settings/save_dir/check")
def save_dir_check():
    return jsonify(_check_save_dir(str(body().get("path") or "")))


# 탐색기 폴더 선택 창을 띄우는 아주 작은 프로그램.
# **별도 프로세스로 돌리는 것이 핵심이다** — Tk 는 자기 프로세스의 메인 스레드를
# 가져야 하는데 여기서는 Flask 가 메인 스레드를 쓰고 있다. 프로세스를 하나 더
# 띄우면 그쪽 메인 스레드를 Tk 가 가지므로 충돌이 없다.
_PICK_DIR = """
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)      # 브라우저 창 뒤에 숨지 않게
start = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
picked = filedialog.askdirectory(title="저장 폴더 선택", initialdir=start)
root.destroy()
sys.stdout.write(picked or "")
"""

# 창이 열린 채 잊히면 요청이 붙잡혀 있으므로 반드시 상한을 둔다.
# Flask 는 threaded=True 라 이 요청 하나가 막혀도 나머지는 계속 돈다.
PICK_TIMEOUT = 180


def _picker_python() -> Optional[str]:
    """폴더 창을 띄울 파이썬. 콘솔이 깜빡이지 않게 pythonw.exe 를 먼저 찾는다."""
    if getattr(sys, "frozen", False):
        # exe 안에서는 python -c 를 쓸 수 없다 (웹은 소스 실행 기능이라 지금은 해당 없음)
        return None
    here = Path(sys.executable)
    windowless = here.with_name("pythonw.exe")
    return str(windowless if windowless.exists() else here)


@bp.post("/settings/save_dir/browse")
def save_dir_browse():
    """서버 PC 에 탐색기 폴더 선택 창을 띄운다.

    os.startfile 과 같은 '브라우저와 서버가 같은 PC' 전제를 쓴다.
    """
    python = _picker_python()
    if python is None:
        return fail(t("여기서는 폴더 창을 띄울 수 없습니다. 경로를 직접 적어 주세요."))

    cfg = config.load()
    start = cfg.save_dir or str(Path.home())
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(
            [python, "-c", _PICK_DIR, start],
            capture_output=True, text=True, timeout=PICK_TIMEOUT, creationflags=flags,
        )
    except subprocess.TimeoutExpired:
        return fail(t("폴더 창이 너무 오래 열려 있어 그만두었습니다."))
    except OSError as err:
        return fail(t("폴더 창을 띄우지 못했습니다 ({reason}).", reason=str(err)))

    picked = (done.stdout or "").strip()
    if not picked:
        # 사용자가 취소한 것은 오류가 아니다
        return jsonify({"ok": False, "cancelled": True, "resolved": ""})

    # 직접 적은 경로와 같은 검사를 거친다 — 규칙을 한 곳에만 둔다
    return jsonify(_check_save_dir(picked))


@bp.post("/settings/save_dir/open")
def save_dir_open():
    """탐색기로 저장 폴더를 연다. 서버와 브라우저가 같은 PC 라는 전제를 쓴다."""
    cfg = config.load()
    if not cfg.save_dir:
        return fail(t("저장 폴더를 먼저 정해 주세요."))
    target = Path(cfg.save_dir).expanduser()
    if not target.is_dir():
        return fail(t("저장 폴더가 없습니다."))
    try:
        os.startfile(str(target))  # noqa: S606 - 사용자가 직접 정한 폴더다
    except (OSError, AttributeError) as err:
        return fail(t("폴더를 열지 못했습니다 ({reason}).", reason=str(err)))
    return jsonify({"ok": True})


# ---------------------------------------------------------------- 계정

@bp.get("/accounts")
def accounts_read():
    return jsonify({"accounts": accounts_json(config.load())})


@bp.post("/accounts")
def accounts_add():
    cfg = config.load()
    data = body()
    # 공백으로 여러 개를 한 번에. normalize_id 가 '@abc' 와 프로필 주소도 받아 준다.
    raw = str(data.get("raw") or "").replace(",", " ").split()
    if not raw:
        return fail(t("추가할 계정을 적어 주세요."))
    added, existing = config.add_accounts(cfg, raw, fav=bool(data.get("fav")))
    config.save(cfg)
    return jsonify({"added": added, "existing": existing,
                    "accounts": accounts_json(cfg)})


@bp.delete("/accounts")
def accounts_remove():
    cfg = config.load()
    ids = [str(i) for i in body().get("ids") or []]
    if not ids:
        return fail(t("지울 계정을 골라 주세요."))
    removed, missing = config.remove_accounts(cfg, ids)
    config.save(cfg)
    return jsonify({"removed": removed, "missing": missing,
                    "accounts": accounts_json(cfg)})


# 즐겨찾기를 켜고 끄는 엔드포인트는 일부러 없다. exe 전용 기능이라
# 웹 화면이 다루지 않고, config.set_fav 는 창 버전만 쓴다.


# ---------------------------------------------------------------- 파일명

@bp.post("/filename/preview")
def filename_preview():
    """이름 형식 미리보기.

    브라우저에서 그리지 않는 이유: 선택 구간과 '기존 번호 뒤로 잇기' 규칙을
    자바스크립트에 한 번 더 구현하면 금방 어긋난다.
    """
    data = body()
    template = str(data.get("template") or "").strip()

    if not data.get("use_template", True) or not template:
        # 라벨은 filename 쪽 헬퍼를 쓴다 — 두 벌로 두면 한쪽만 고치게 된다.
        return jsonify({
            "ok": True, "errors": [], "warnings": [],
            "preview": [
                {"label": filename.preview_label(s),
                 "name": filename.default_stem(s),
                 "ext": ".mp4" if s.is_video else ".jpg"}
                for s in filename.sample_items()
            ],
        })

    errors, warnings = filename.validate(template)
    source_job = registry().get(str(data.get("job_id") or ""))
    items = source_job.items[:3] if source_job else None

    return jsonify({
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "preview": [] if errors else filename.preview(template, items),
    })
