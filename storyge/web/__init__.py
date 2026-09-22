"""웹 버전 (python -m storyge serve).

**1인용 로컬 도구다.** 로그인도 CSRF 토큰도 없고, 보안 모델은 두 줄이 전부다.

  1. 127.0.0.1 에만 바인딩한다 (server.serve).
  2. Host 헤더가 로컬이 아니면 거절한다 (아래 _local_only).

2번이 없으면 사용자가 방문하는 **아무 웹페이지나** 이 서버를 조종할 수 있다
(DNS rebinding — 공격자 도메인이 127.0.0.1 을 가리키게 만들면 브라우저는
같은 출처로 여긴다). 포트만 열어 두고 1번에 기대는 것으로는 막히지 않는다.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import Flask, jsonify, request

from . import api, jobs, views

# 이 이름으로 들어온 요청만 받는다
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _host_of(value: str) -> str:
    """'127.0.0.1:8760' 또는 'http://localhost:8760' 에서 호스트만 뽑는다."""
    text = (value or "").strip()
    if "://" in text:
        text = urlsplit(text).netloc
    if text.startswith("["):                      # IPv6
        return text[: text.find("]") + 1].lower()
    return text.rsplit(":", 1)[0].lower() if ":" in text else text.lower()


def create_app() -> Flask:
    app = Flask(__name__)
    # 한국어 안내가 \uXXXX 로 깨져 나가지 않게
    app.json.ensure_ascii = False
    app.extensions["storyge_jobs"] = jobs.JobRegistry()

    app.register_blueprint(views.bp)
    app.register_blueprint(api.bp)

    @app.before_request
    def _local_only():
        if _host_of(request.host) not in LOCAL_HOSTS:
            return jsonify({"error": "local only"}), 403
        origin = request.headers.get("Origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
            if _host_of(origin) not in LOCAL_HOSTS:
                return jsonify({"error": "local only"}), 403
        return None

    @app.errorhandler(404)
    def _not_found(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "not found"}), 404
        return err, 404

    @app.errorhandler(500)
    def _boom(err):  # noqa: ARG001
        if request.path.startswith("/api/"):
            return jsonify({"error": "server error"}), 500
        return "server error", 500

    return app
