import argparse
import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import requests


# ============================================================
# CONFIG
# ============================================================

SITE_INSIGHT_URL = os.getenv(
    "SITE_INSIGHT_URL",
    "http://localhost:10000",
).rstrip("/")

SCHEDULER_INTERVAL_MINUTES = int(
    os.getenv("SCHEDULER_INTERVAL_MINUTES", "360")
)

RADAR_LANGUAGE = os.getenv("RADAR_LANGUAGE", "ru")
RADAR_HOURS_BACK = int(os.getenv("RADAR_HOURS_BACK", "72"))
RADAR_MAX_RESULTS = int(os.getenv("RADAR_MAX_RESULTS", "50"))

DIRECTOR_ENABLED = (
    os.getenv("DIRECTOR_ENABLED", "true").lower()
    in {"1", "true", "yes", "on"}
)

BACKUP_ENABLED = (
    os.getenv("BACKUP_ENABLED", "false").lower()
    in {"1", "true", "yes", "on"}
)

HEALTH_PORT = int(os.getenv("PORT", "10000"))

REQUEST_TIMEOUT = int(os.getenv("SCHEDULER_REQUEST_TIMEOUT", "120"))


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger("ai-youtube-scheduler")


# ============================================================
# STATE
# ============================================================

state: dict[str, Any] = {
    "status": "starting",
    "started_at": None,
    "last_run_started_at": None,
    "last_run_finished_at": None,
    "last_run_status": None,
    "last_run_error": None,
    "last_radar_result": None,
    "last_director_result": None,
    "runs": 0,
}


# ============================================================
# HELPERS
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def api_url(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return SITE_INSIGHT_URL + path


def safe_json_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def post_json(
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    url = api_url(path)

    logger.info("POST %s", url)

    response = requests.post(
        url,
        json=payload or {},
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    return safe_json_response(response)


def get_json(
    path: str,
    params: dict[str, Any] | None = None,
) -> Any:
    url = api_url(path)

    logger.info("GET %s", url)

    response = requests.get(
        url,
        params=params or {},
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    return safe_json_response(response)


# ============================================================
# SITE-INSIGHT ENGINE
# ============================================================

def check_site_insight() -> bool:
    """
    Проверяем, доступен ли site-insight-engine.

    Используем существующий endpoint /events,
    поэтому не придумываем отдельный health API.
    """

    try:
        get_json("/events")
        logger.info("site-insight-engine доступен")
        return True

    except Exception as exc:
        logger.error(
            "site-insight-engine недоступен: %s",
            exc,
        )
        return False


def run_radar() -> Any:
    """
    Запускает существующий Growth Radar.

    Использует уже реализованный endpoint:
        GET /radar-videos
    """

    logger.info(
        "Запуск Growth Radar: language=%s hours_back=%s max_results=%s",
        RADAR_LANGUAGE,
        RADAR_HOURS_BACK,
        RADAR_MAX_RESULTS,
    )

    result = get_json(
        "/radar-videos",
        params={
            "language": RADAR_LANGUAGE,
            "hours_back": RADAR_HOURS_BACK,
            "max_results": RADAR_MAX_RESULTS,
        },
    )

    state["last_radar_result"] = {
        "completed_at": utc_now(),
        "result": result,
    }

    return result


def save_radar_snapshot(radar_result: Any) -> Any:
    """
    Сохраняет результат радара через существующий endpoint.

    ВАЖНО:
    Если формат /radar-save будет отличаться,
    этот участок легко адаптируется.
    """

    logger.info("Сохранение Radar snapshot")

    payload = {
        "language": RADAR_LANGUAGE,
        "hours_back": RADAR_HOURS_BACK,
        "data": radar_result,
    }

    try:
        return post_json(
            "/radar-save",
            payload,
        )

    except requests.HTTPError as exc:
        logger.warning(
            "Radar snapshot не сохранён: %s",
            exc,
        )
        return {
            "saved": False,
            "error": str(exc),
        }


def run_director() -> Any:
    """
    Запускает существующий Director endpoint.

    Никаких будущих функций здесь не предполагаем:
    используется только уже существующий /director/run.
    """

    if not DIRECTOR_ENABLED:
        logger.info("Director отключён через DIRECTOR_ENABLED")
        return {
            "enabled": False,
            "skipped": True,
        }

    logger.info("Запуск AI Director")

    result = post_json(
        "/director/run",
        {},
    )

    state["last_director_result"] = {
        "completed_at": utc_now(),
        "result": result,
    }

    return result


# ============================================================
# BACKUP
# ============================================================

def run_backup() -> Any:
    """
    Пока не пытаемся делать backup базы другого Render-сервиса.

    backup.py существует, но ai-youtube-system и
    site-insight-engine находятся в разных контейнерах.

    Поэтому здесь оставляем безопасную точку расширения.
    Реальный backup подключим после определения общего
    persistent/external storage.
    """

    if not BACKUP_ENABLED:
        logger.info(
            "Backup scheduler отключён: BACKUP_ENABLED=false"
        )

        return {
            "enabled": False,
            "skipped": True,
        }

    logger.warning(
        "BACKUP_ENABLED=true, но межсервисный backup "
        "ещё не подключён к общему хранилищу"
    )

    return {
        "enabled": True,
        "completed": False,
        "reason": (
            "Общее хранилище между Render-сервисами "
            "ещё не настроено"
        ),
    }


# ============================================================
# ONE FULL RUN
# ============================================================

def run_once() -> dict[str, Any]:
    """
    Один полный цикл:

        1. Проверка аналитического сервиса
        2. Growth Radar
        3. Сохранение snapshot
        4. Director
        5. Backup hook
    """

    started = utc_now()

    state["status"] = "running"
    state["last_run_started_at"] = started
    state["last_run_finished_at"] = None
    state["last_run_status"] = None
    state["last_run_error"] = None

    state["runs"] += 1

    result: dict[str, Any] = {
        "started_at": started,
        "finished_at": None,
        "status": "running",
        "radar": None,
        "radar_snapshot": None,
        "director": None,
        "backup": None,
    }

    try:
        if not check_site_insight():
            raise RuntimeError(
                "site-insight-engine недоступен"
            )

        # ----------------------------------------------------
        # 1. RADAR
        # ----------------------------------------------------

        radar_result = run_radar()

        result["radar"] = radar_result

        # ----------------------------------------------------
        # 2. SAVE RADAR SNAPSHOT
        # ----------------------------------------------------

        result["radar_snapshot"] = save_radar_snapshot(
            radar_result
        )

        # ----------------------------------------------------
        # 3. DIRECTOR
        # ----------------------------------------------------

        result["director"] = run_director()

        # ----------------------------------------------------
        # 4. BACKUP
        # ----------------------------------------------------

        result["backup"] = run_backup()

        result["status"] = "success"

        state["status"] = "idle"
        state["last_run_status"] = "success"

        logger.info("Scheduler cycle завершён успешно")

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)

        state["status"] = "error"
        state["last_run_status"] = "error"
        state["last_run_error"] = str(exc)

        logger.exception(
            "Ошибка scheduler cycle"
        )

    finally:
        finished = utc_now()

        result["finished_at"] = finished
        state["last_run_finished_at"] = finished

    return result


# ============================================================
# PERIODIC LOOP
# ============================================================

def scheduler_loop() -> None:
    logger.info(
        "Scheduler запущен. Интервал: %s минут",
        SCHEDULER_INTERVAL_MINUTES,
    )

    state["status"] = "idle"

    while True:
        try:
            run_once()

        except Exception:
            logger.exception(
                "Критическая ошибка scheduler loop"
            )

            state["status"] = "error"

        sleep_seconds = (
            SCHEDULER_INTERVAL_MINUTES * 60
        )

        logger.info(
            "Следующий запуск через %s минут",
            SCHEDULER_INTERVAL_MINUTES,
        )

        time.sleep(sleep_seconds)


# ============================================================
# HEALTH HTTP SERVER
# ============================================================

class HealthHandler(BaseHTTPRequestHandler):

    def _send_json(
        self,
        status_code: int,
        data: dict[str, Any],
    ) -> None:

        body = json.dumps(
            data,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")

        self.send_response(status_code)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.end_headers()

        self.wfile.write(body)

    def do_GET(self) -> None:

        if self.path == "/health":
            self._send_json(
                200,
                {
                    "service": "ai-youtube-scheduler",
                    "status": state["status"],
                    "site_insight_url": SITE_INSIGHT_URL,
                    "interval_minutes": (
                        SCHEDULER_INTERVAL_MINUTES
                    ),
                    "runs": state["runs"],
                    "last_run_status": (
                        state["last_run_status"]
                    ),
                    "last_run_started_at": (
                        state["last_run_started_at"]
                    ),
                    "last_run_finished_at": (
                        state["last_run_finished_at"]
                    ),
                    "last_run_error": (
                        state["last_run_error"]
                    ),
                },
            )

            return

        if self.path == "/":
            self._send_json(
                200,
                {
                    "service": "ai-youtube-scheduler",
                    "status": state["status"],
                },
            )

            return

        if self.path == "/run":
            result = run_once()

            status_code = (
                200
                if result["status"] == "success"
                else 500
            )

            self._send_json(
                status_code,
                result,
            )

            return

        self._send_json(
            404,
            {
                "error": "Not found",
            },
        )

    def log_message(
        self,
        format: str,
        *args: Any,
    ) -> None:

        logger.info(
            "HTTP %s",
            format % args,
        )


def start_health_server() -> HTTPServer:
    server = HTTPServer(
        ("0.0.0.0", HEALTH_PORT),
        HealthHandler,
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )

    thread.start()

    logger.info(
        "Health server запущен на 0.0.0.0:%s",
        HEALTH_PORT,
    )

    return server


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description="AI YouTube Scheduler"
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Выполнить один цикл и завершиться",
    )

    args = parser.parse_args()

    state["started_at"] = utc_now()

    if args.once:
        result = run_once()

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        return

    start_health_server()

    scheduler_loop()


if __name__ == "__main__":
    main()
