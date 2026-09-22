"""'스토리를 가져와 고르고 저장' 한 번의 흐름.

CLI(__main__.py)와 대화형 메뉴(menu.py)가 모두 이 함수를 쓴다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import config, download, fetch, history, net, picker, session


def resolve_save_dir(cfg: config.Config, out: Optional[str] = None) -> Optional[Path]:
    """--out > config.json > 직접 입력 순으로 저장 폴더를 정한다."""
    if out:
        return Path(out).expanduser().resolve()
    if cfg.save_dir:
        return Path(cfg.save_dir)

    print("\n스토리를 저장할 폴더가 정해져 있지 않습니다.")
    typed = input("저장 폴더 경로를 입력하세요: ").strip().strip('"')
    if not typed:
        print("폴더를 입력하지 않아 취소합니다.")
        return None
    save_dir = Path(typed).expanduser().resolve()
    cfg.save_dir = str(save_dir)
    config.save(cfg)
    print(f"저장 폴더로 기억해 두었습니다: {save_dir}")
    return save_dir


def run_once(
    fav: bool = False,
    accounts: Optional[list[str]] = None,
    out: Optional[str] = None,
    login: bool = False,
) -> int:
    """0 이면 정상 종료, 1 이면 중간에 멈춤."""
    cfg = config.load()

    if accounts:
        targets = [config.normalize_id(a) for a in accounts]
    else:
        targets = cfg.targets(only_fav=fav)

    if not targets:
        if fav:
            print("즐겨찾기로 등록된 계정이 없습니다.")
        else:
            print("등록된 계정이 없습니다. 먼저 계정을 추가하세요.")
        return 1

    save_dir = resolve_save_dir(cfg, out)
    if save_dir is None:
        return 1

    try:
        client = session.get_client(cfg, force_login=login)
    except session.LoginFailed as err:
        print(f"\n{err}")
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\n로그인을 취소했습니다.")
        return 1

    print(f"\n스토리 확인 중: {', '.join('@' + t for t in targets)}")
    items, notes = fetch.fetch_stories(client, targets, skip_mediaids=history.load())
    for note in notes:
        print(f"  - {note}")

    if not items:
        print("\n새로 저장할 스토리가 없습니다.")
        return 0

    print(f"\n새 스토리 {len(items)}개를 찾았습니다.")
    chosen = picker.pick(items, net.fetch_bytes)
    if not chosen:
        print("선택한 항목이 없어 종료합니다. (저장된 파일 없음)")
        return 0

    print(f"\n{len(chosen)}개를 {save_dir} 에 저장합니다.")
    ok, failed = download.download_items(chosen, save_dir)
    print(f"\n완료: {ok}개 저장, {failed}개 실패")
    return 0
