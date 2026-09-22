"""명령줄 진입점.

인자 없이 실행하면 GUI 창이 뜬다. 인자를 주면 콘솔에서 서브커맨드로도 쓸 수 있다.

    igstory                          GUI 창
    igstory run --fav                즐겨찾기 계정만 바로 실행
    igstory add abc def --fav        여러 계정 한 번에 추가
    igstory rm abc def               여러 계정 한 번에 삭제
    igstory ls                       등록 목록 보기
    igstory fav abc / unfav abc      즐겨찾기 켜기/끄기
    igstory config --out D:\\스토리    저장 폴더 지정
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from . import app, config, paths


def _print_list(names: list[str], prefix: str) -> None:
    if names:
        print(f"{prefix}: {', '.join('@' + n for n in names)}")


def cmd_add(args) -> int:
    cfg = config.load()
    added, existing = config.add_accounts(cfg, args.accounts, fav=args.fav)
    config.save(cfg)
    _print_list(added, "추가함")
    _print_list(existing, "이미 등록돼 있음")
    return 0


def cmd_rm(args) -> int:
    cfg = config.load()
    removed, missing = config.remove_accounts(cfg, args.accounts)
    config.save(cfg)
    _print_list(removed, "삭제함")
    _print_list(missing, "등록돼 있지 않음")
    return 0


def cmd_fav(args) -> int:
    cfg = config.load()
    on = args.command == "fav"
    changed, missing = config.set_fav(cfg, args.accounts, on)
    config.save(cfg)
    _print_list(changed, "즐겨찾기 " + ("추가" if on else "해제"))
    _print_list(missing, "등록돼 있지 않음")
    return 0


def cmd_ls(args) -> int:
    cfg = config.load()
    paths.ensure_data_dir()
    if not paths.CONFIG_FILE.exists():
        config.save(cfg)

    print(f"저장 폴더: {cfg.save_dir or '(미지정)'}")
    print(f"설정 파일: {paths.CONFIG_FILE}")
    if not cfg.accounts:
        print("\n등록된 계정이 없습니다.  예) igstory add 계정ID")
        return 0
    print(f"\n등록된 계정 {len(cfg.accounts)}개:")
    for acc in cfg.accounts:
        print(f"  {'★' if acc.fav else ' '} @{acc.id}")
    return 0


def cmd_config(args) -> int:
    cfg = config.load()
    if args.out:
        cfg.save_dir = str(Path(args.out).expanduser().resolve())
        config.save(cfg)
        print(f"저장 폴더를 설정했습니다: {cfg.save_dir}")
    else:
        print(f"저장 폴더: {cfg.save_dir or '(미지정)'}")
    return 0


def cmd_run(args) -> int:
    return app.run_once(
        fav=args.fav,
        accounts=args.accounts,
        out=args.out,
        login=args.login,
    )


def _serve_login_dir(asked) -> Path:
    """웹이 로그인 정보를 어디서 빌릴지 정한다.

    exe 는 exe 옆의 data 를, 소스로 띄운 웹은 프로젝트 폴더의 data 를 쓴다. 그래서
    exe 로 로그인해도 웹은 그 세션을 못 찾는다. **로그인 정보만** 그쪽에서 빌려 오면
    정확한 게시 시각과 비공개 계정을 쓸 수 있으면서, 계정 목록·저장 폴더·저장 기록은
    각자 자기 것을 쓴다.

    순서: --login-dir 로 준 것 > exe 옆 dist\\data > data 폴더와 같은 곳
    """
    if asked:
        return Path(asked).expanduser()
    shipped = paths.BASE_DIR / "dist" / "data"
    if shipped != paths.DATA_DIR and paths.looks_like_data_dir(shipped):
        return shipped
    return paths.DATA_DIR


def cmd_serve(args) -> int:
    # 다른 모듈이 경로를 읽기 전에 먼저 정해 둔다.
    # 설정·기록은 웹 자신의 폴더, 로그인 정보만 공유한다.
    if args.data:
        paths.use_data_dir(Path(args.data).expanduser())
    paths.use_login_dir(_serve_login_dir(args.login_dir))
    print(f"설정 폴더  : {paths.DATA_DIR}")
    print(f"로그인 정보: {paths.LOGIN_DIR}"
          + ("" if paths.LOGIN_DIR != paths.DATA_DIR else " (같음)"))

    # Flask 를 여기서만 불러온다. 이렇게 해야 Flask 가 깔려 있지 않아도
    # 창 버전과 나머지 콘솔 명령(ls/add/rm...)이 그대로 돈다.
    try:
        from .web import server
    except ImportError as err:
        print("웹 버전을 띄우려면 Flask 가 필요합니다.")
        print(r"  .venv\Scripts\python.exe -m pip install -r requirements.txt")
        print(f"  ({err})")
        return 1
    return server.serve(host=args.host, port=args.port,
                        open_browser=not args.no_browser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="igstory",
        description="등록한 계정들의 인스타그램 스토리를 골라서 저장합니다. "
                    "인자 없이 실행하면 메뉴가 뜹니다.",
    )
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="스토리를 가져와 고르고 저장")
    run.add_argument("--fav", action="store_true", help="즐겨찾기 계정만 대상")
    run.add_argument("--accounts", nargs="+", metavar="ID", help="등록 목록 대신 이 계정들만")
    run.add_argument("--out", metavar="DIR", help="이번만 다른 폴더에 저장")
    run.add_argument("--login", action="store_true", help="저장된 세션을 무시하고 다시 로그인")
    run.set_defaults(func=cmd_run)

    add = sub.add_parser("add", help="계정 추가 (여러 개 가능)")
    add.add_argument("accounts", nargs="+", metavar="ID")
    add.add_argument("--fav", action="store_true", help="즐겨찾기로 추가")
    add.set_defaults(func=cmd_add)

    rm = sub.add_parser("rm", help="계정 삭제 (여러 개 가능)")
    rm.add_argument("accounts", nargs="+", metavar="ID")
    rm.set_defaults(func=cmd_rm)

    ls = sub.add_parser("ls", help="등록된 계정 목록")
    ls.set_defaults(func=cmd_ls)

    for name, help_text in (("fav", "즐겨찾기 추가"), ("unfav", "즐겨찾기 해제")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("accounts", nargs="+", metavar="ID")
        p.set_defaults(func=cmd_fav)

    conf = sub.add_parser("config", help="저장 폴더 설정")
    conf.add_argument("--out", metavar="DIR", help="스토리를 저장할 기본 폴더")
    conf.set_defaults(func=cmd_config)

    serve = sub.add_parser("serve", help="브라우저로 쓰는 웹 버전을 띄운다")
    serve.add_argument("--port", type=int, default=8760, help="기본 8760")
    # --host 는 있지만 권하지 않는다. 127.0.0.1 밖으로 열면 같은 망의 누구나
    # 이 PC 의 저장 폴더에 파일을 쓰게 할 수 있다 (로그인이 없는 도구다).
    serve.add_argument("--host", default="127.0.0.1", help="권장하지 않음")
    serve.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않는다")
    serve.add_argument("--data", metavar="DIR",
                       help="설정·저장 기록을 둘 폴더 (기본: data)")
    serve.add_argument("--login-dir", metavar="DIR",
                       help="로그인 정보를 빌려 올 폴더 "
                            "(기본: exe 가 쓰던 dist\\data 가 있으면 그쪽)")
    serve.set_defaults(func=cmd_serve)

    return parser


def setup_console_encoding() -> None:
    """콘솔과 표준 입출력을 UTF-8 로 맞춘다.

    exe 로 만들면 파이썬이 인코딩을 로케일(한국어 윈도우는 cp949)에서 가져오는데,
    콘솔은 UTF-8 로 읽는 경우가 있어 한글이 깨진다. 양쪽을 UTF-8 로 고정해 둔다.
    """
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass  # 콘솔이 없는 환경이면 그냥 넘어간다

    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    args_in = sys.argv[1:] if argv is None else argv

    # 인자 없이 실행 = GUI 창을 띄운다.
    if not args_in:
        from . import gui

        return gui.main()

    args = build_parser().parse_args(args_in)
    return args.func(args)


def _entry() -> int:
    """exe 용 진입점. 오류가 나도 창이 바로 닫히지 않게 한다."""
    frozen = getattr(sys, "frozen", False)
    setup_console_encoding()
    try:
        return main()
    except KeyboardInterrupt:
        print("\n중단했습니다.")
        return 130
    except Exception:
        print("\n예상치 못한 오류가 생겼습니다:\n")
        traceback.print_exc()
        if frozen:
            try:
                input("\n엔터를 누르면 창이 닫힙니다...")
            except EOFError:
                pass
        return 1


if __name__ == "__main__":
    sys.exit(_entry())
