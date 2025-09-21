"""Flask app for orchestrating data pulls and analysis updates."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from query_data import compute_stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE2_ROOT = PROJECT_ROOT / "module_2"
MODULE3_ROOT = PROJECT_ROOT / "module_3"

SCRAPER_PATH = MODULE2_ROOT / "scrape.py"
JSONL_PATH = MODULE2_ROOT / "llm_extend_applicant_data.jsonl"
LOCK_FILE = MODULE2_ROOT / "scrape.lock"
LOADER_PATH = MODULE3_ROOT / "load_data.py"
ANALYSIS_FILE = MODULE3_ROOT / "last_analysis.txt"
PULL_OK_FILE = MODULE3_ROOT / "last_pull_success.txt"

SCRAPER_CMD = [sys.executable, str(SCRAPER_PATH)]
LOADER_CMD = [sys.executable, str(LOADER_PATH), str(JSONL_PATH)]

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")
app.config["TEMPLATES_AUTO_RELOAD"] = True


@dataclass
class PullResult:
    """Container for subprocess output and row counts."""

    scraped: int | None
    inserted: int | None
    scraper_output: str
    loader_output: str


def _clear_lock() -> None:
    """Remove the lock file if it exists."""

    LOCK_FILE.unlink(missing_ok=True)


def _mtime(path: Path) -> float | None:
    """Return the modification time for ``path`` if it exists."""

    try:
        return path.stat().st_mtime
    except OSError:
        return None


def compute_gate_state() -> tuple[float | None, float | None, bool]:
    """Return timestamps relevant to the Update Analysis gate."""

    last_ok_pull = _mtime(PULL_OK_FILE)
    last_analysis = _mtime(ANALYSIS_FILE)
    needs_update = (
        last_ok_pull is not None
        and (last_analysis is None or last_analysis < last_ok_pull)
    )
    return last_ok_pull, last_analysis, needs_update


def wants_json_response() -> bool:
    """Return ``True`` when the client prefers a JSON payload."""

    if request.is_json:
        return True
    accept = request.headers.get("Accept", "")
    if "application/json" in accept or accept == "*/*":
        return True
    return False


def _parse_pull_counts(scraper_stdout: str, loader_stdout: str) -> tuple[int | None, int | None]:
    """Extract record counts from stdout emitted by the pipeline."""

    scraped = None
    inserted = None
    if scraper_stdout:
        matches = re.findall(r"appended\s+(\d+)\s+records", scraper_stdout, flags=re.I)
        if matches:
            scraped = int(matches[-1])
    if loader_stdout:
        match = re.search(r"Inserted rows:\s*(\d+)", loader_stdout, flags=re.I)
        if match:
            inserted = int(match.group(1))
    return scraped, inserted


def is_running() -> bool:
    """Return ``True`` when the lock file points to a live PID."""

    try:
        pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        return False
    except ValueError:
        _clear_lock()
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        _clear_lock()
        return False
    return True


def set_lock(pid: int | None) -> None:
    """Persist ``pid`` to the lock file, or clear it when ``pid`` is ``None``."""

    if pid is None:
        _clear_lock()
        return
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(str(pid), encoding="utf-8")


@app.template_filter("datetimeformat")
def datetimeformat(value: float | int | None) -> str:
    """Render a UNIX timestamp as a formatted string for templates."""

    try:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _build_child_env() -> dict[str, str]:
    """Return an environment dict that forces UTF-8 for child processes."""

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _write_success_marker() -> None:
    """Record the timestamp of a successful scrape/load cycle."""

    PULL_OK_FILE.parent.mkdir(parents=True, exist_ok=True)
    PULL_OK_FILE.write_text(str(int(time.time())), encoding="utf-8")


def _run_scraper_and_loader(env: dict[str, str]) -> PullResult:
    """Execute the scraper then the loader, returning their outputs."""

    set_lock(os.getpid())
    try:
        with subprocess.Popen(
            SCRAPER_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        ) as scraper:
            set_lock(scraper.pid)
            scraper_stdout, scraper_stderr = scraper.communicate()
            if scraper.returncode != 0:
                raise subprocess.CalledProcessError(
                    scraper.returncode,
                    SCRAPER_CMD,
                    output=scraper_stdout,
                    stderr=scraper_stderr,
                )

        with subprocess.Popen(
            LOADER_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        ) as loader:
            loader_stdout, loader_stderr = loader.communicate()
            if loader.returncode != 0:
                raise subprocess.CalledProcessError(
                    loader.returncode,
                    LOADER_CMD,
                    output=loader_stdout,
                    stderr=loader_stderr,
                )
        _write_success_marker()
    finally:
        set_lock(None)

    scraped, inserted = _parse_pull_counts(scraper_stdout, loader_stdout)
    return PullResult(scraped, inserted, scraper_stdout, loader_stdout)


def _handle_when_running(json_response: bool):
    """Return a busy response when a pull is already running."""

    if not is_running():
        return None
    if json_response:
        return jsonify(status="busy"), 409
    flash("A data pull is already running. Please wait for it to finish.", "error")
    return redirect(url_for("index"))


def _success_messages(result: PullResult) -> list[tuple[str, str]]:
    """Build flash messages for a successful pull."""

    messages: list[tuple[str, str]] = []
    if result.scraped is not None or result.inserted is not None:
        messages.append(
            (
                f"Pull complete: scraped {result.scraped or 0}, inserted {result.inserted or 0}.",
                "success",
            )
        )
    else:
        messages.append(("New data pulled and loaded successfully.", "success"))
    if result.scraper_output:
        messages.append((f"Scraper: {result.scraper_output[-500:]}", "success"))
    if result.loader_output:
        messages.append((f"Loader: {result.loader_output[-500:]}", "success"))
    return messages


def _handle_subprocess_failure(json_response: bool, exc: subprocess.CalledProcessError):
    """Return an error response for ``CalledProcessError`` instances."""

    command = " ".join(map(str, exc.cmd))
    message = f"Command failed ({command}), exit {exc.returncode}."
    if exc.stderr:
        message += f" STDERR: {exc.stderr[-500:]}"
    payload = {"status": "error", "message": message}
    if json_response:
        return jsonify(payload), 500
    flash(message, "error")
    return redirect(url_for("index"))


def _handle_generic_failure(json_response: bool, exc: Exception):
    """Return a fallback error response for unexpected failures."""

    message = f"Pull failed: {exc}"
    payload = {"status": "error", "message": message}
    if json_response:
        return jsonify(payload), 500
    flash(message, "error")
    return redirect(url_for("index"))


def _respond_success(json_response: bool, result: PullResult):
    """Return the appropriate success response for the client."""

    payload = {
        "status": "ok",
        "scraped": result.scraped or 0,
        "inserted": result.inserted or 0,
    }
    if json_response:
        return jsonify(payload), 200
    for message, category in _success_messages(result):
        flash(message, category)
    return redirect(url_for("index"))


@app.route("/")
@app.route("/analysis")
def index():
    """Render the dashboard template with latest stats and metadata."""

    stats = compute_stats()
    last_pull_ts, last_analysis_ts, needs_update = compute_gate_state()
    return render_template(
        "index.html",
        running=is_running(),
        needs_update=needs_update,
        last_pull_ts=last_pull_ts,
        last_analysis_ts=last_analysis_ts,
        **stats,
    )


@app.route("/pull-data", methods=["POST"])
def pull_data():
    """Trigger the scraper/loader pipeline and report its status."""

    json_response = wants_json_response()
    busy_response = _handle_when_running(json_response)
    if busy_response is not None:
        return busy_response

    try:
        result = _run_scraper_and_loader(_build_child_env())
    except subprocess.CalledProcessError as exc:
        return _handle_subprocess_failure(json_response, exc)
    except (OSError, ValueError) as exc:
        return _handle_generic_failure(json_response, exc)

    return _respond_success(json_response, result)


def _update_busy_response(json_response: bool):
    """Return a response when an update is blocked by a running pull."""

    if json_response:
        return jsonify(status="busy"), 409
    flash("Please wait until data pull has completed.", "error")
    return redirect(url_for("index"))


def _no_update_available_response(json_response: bool, last_pull_ts: float | None):
    """Return a response when no new data is available for analysis."""

    if json_response:
        return jsonify(status="noop", reason="no-new-data"), 409
    if last_pull_ts is None:
        flash(
            "No new data to update analysis with, please click Pull Data to refresh data.",
            "info",
        )
    else:
        flash(
            "No new data to update analysis with since the last successful pull.",
            "info",
        )
    return redirect(url_for("index"))


def _update_failure_response(json_response: bool, message: str):
    """Return a response for update-analysis failures."""

    if json_response:
        return jsonify(status="error", message=message), 500
    flash(message, "error")
    return redirect(url_for("index"))


def _update_success_response(json_response: bool):
    """Return a success response after recording the analysis timestamp."""

    if json_response:
        return jsonify(status="ok", updated=True), 200
    flash("Analysis updated.", "success")
    return redirect(url_for("index"))


@app.route("/update-analysis", methods=["POST"])
def update_analysis():
    """Mark the analysis as refreshed when new data is available."""

    json_response = wants_json_response()

    if is_running():
        return _update_busy_response(json_response)

    last_pull_ts, _, needs_update = compute_gate_state()
    if not needs_update:
        return _no_update_available_response(json_response, last_pull_ts)

    try:
        ANALYSIS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ANALYSIS_FILE.write_text(str(int(time.time())), encoding="utf-8")
    except OSError as exc:
        return _update_failure_response(json_response, f"Update failed: {exc}")

    return _update_success_response(json_response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True, use_reloader=True)
