# module_3/app.py
from flask import Flask, render_template, redirect, url_for, flash, jsonify, request
from query_data import compute_stats
import subprocess, os, sys, re, time
from datetime import datetime

#---- Flask app setup ----
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")
app.config["TEMPLATES_AUTO_RELOAD"] = True

# ---- Jinja filter: format UNIX timestamps ----
@app.template_filter("datetimeformat")
def datetimeformat(value):
    try:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""

# ---- Absolute paths (Windows) ----
SCRAPER_PATH  = r"D:\Users\Joe Hawes Jr\Desktop\School\JHU AI (Prerequisites)\Modern Software Concepts\jhu_software_concepts\module_2\scrape.py"
JSONL_PATH    = r"D:\Users\Joe Hawes Jr\Desktop\School\JHU AI (Prerequisites)\Modern Software Concepts\jhu_software_concepts\module_2\llm_extend_applicant_data.jsonl"
STATE_FILE    = r"D:\Users\Joe Hawes Jr\Desktop\School\JHU AI (Prerequisites)\Modern Software Concepts\jhu_software_concepts\module_2\last_run.txt"
LOCK_FILE     = r"D:\Users\Joe Hawes Jr\Desktop\School\JHU AI (Prerequisites)\Modern Software Concepts\jhu_software_concepts\module_2\scrape.lock"

LOADER_PATH   = r"D:\Users\Joe Hawes Jr\Desktop\School\JHU AI (Prerequisites)\Modern Software Concepts\jhu_software_concepts\module_3\load_data.py"
ANALYSIS_FILE = r"D:\Users\Joe Hawes Jr\Desktop\School\JHU AI (Prerequisites)\Modern Software Concepts\jhu_software_concepts\module_3\last_analysis.txt"

# success marker: written ONLY when scrape+load both succeed
PULL_OK_FILE  = r"D:\Users\Joe Hawes Jr\Desktop\School\JHU AI (Prerequisites)\Modern Software Concepts\jhu_software_concepts\module_3\last_pull_success.txt"

# ---- Commands (no shell; each arg separate) ----
SCRAPER_CMD = [sys.executable, SCRAPER_PATH]
LOADER_CMD  = [sys.executable, LOADER_PATH, JSONL_PATH]

# ---- Gate helpers / lock helpers ----
def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None

# Compute gate state for Update Analysis button
def compute_gate_state():
    """
    Allow Update Analysis only if there's a *successful* pull
    newer than the last analysis.
    """
    last_ok_pull = _mtime(PULL_OK_FILE)    # success marker
    last_analysis = _mtime(ANALYSIS_FILE)
    needs_update = (last_ok_pull is not None) and (last_analysis is None or last_analysis < last_ok_pull)
    return last_ok_pull, last_analysis, needs_update


# Determine whether the client prefers a JSON response
def wants_json_response():
    if request.is_json:
        return True
    accept = request.headers.get("Accept", "")
    if "application/json" in accept or accept == "*/*":
        return True
    return False

# Parse pull counts from scraper/loader output
def _parse_pull_counts(scraper_stdout: str, loader_stdout: str) -> tuple[int|None, int|None]:
    scraped = None
    inserted = None
    if scraper_stdout:
        matches = re.findall(r'appended\s+(\d+)\s+records', scraper_stdout, flags=re.I)
        if matches:
            scraped = int(matches[-1])
    if loader_stdout:
        m = re.search(r'Inserted rows:\s*(\d+)', loader_stdout, flags=re.I)
        if m:
            inserted = int(m.group(1))
    return scraped, inserted

# Is a pull or load currently running?
def is_running():
    """Return True if a PID in LOCK_FILE exists and is alive."""
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # raises if not running
        return True
    except FileNotFoundError:
        return False
    except (ValueError, ProcessLookupError, OSError):
        try: os.remove(LOCK_FILE)
        except FileNotFoundError: pass
        return False

# Set or clear the lock file with given PID (or None to clear)
def set_lock(pid: int | None):
    if pid is None:
        try: os.remove(LOCK_FILE)
        except FileNotFoundError: pass
    else:
        os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
        with open(LOCK_FILE, "w") as f:
            f.write(str(pid))

# ---- Routes ----
@app.route("/")
@app.route("/analysis")
def index():
    stats = compute_stats()
    last_pull_ts, last_analysis_ts, needs_update = compute_gate_state()
    return render_template(
        "index.html",
        running=is_running(),
        needs_update=needs_update,
        last_pull_ts=last_pull_ts,
        last_analysis_ts=last_analysis_ts,
        **stats
    )

#Pull data: scrape + load
@app.route("/pull-data", methods=["POST"])
def pull_data():
    if is_running():
        if wants_json_response():
            return jsonify(status="busy"), 409
        flash("A data pull is already running. Please wait for it to finish.", "error")
        return redirect(url_for("index"))

    json_response = wants_json_response()

    # Force UTF-8 for child processes (fixes UnicodeEncodeError from scraper prints)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    payload = {"status": "ok"}
    status_code = 200
    messages = []
    out1 = out2 = ""
    scraped = inserted = None

    try:
        # Lock immediately to block Update clicks in the tiny startup window
        set_lock(os.getpid())

        # 1) Scrape
        p1 = subprocess.Popen(
            SCRAPER_CMD,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env
        )
        set_lock(p1.pid)  # now track the child pid
        out1, err1 = p1.communicate()
        if p1.returncode != 0:
            raise subprocess.CalledProcessError(p1.returncode, SCRAPER_CMD, output=out1, stderr=err1)

        # 2) Load
        p2 = subprocess.Popen(
            LOADER_CMD,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env
        )
        out2, err2 = p2.communicate()
        if p2.returncode != 0:
            raise subprocess.CalledProcessError(p2.returncode, LOADER_CMD, output=out2, stderr=err2)

        # success -> write marker enabling Update Analysis
        os.makedirs(os.path.dirname(PULL_OK_FILE), exist_ok=True)
        with open(PULL_OK_FILE, "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))

        scraped, inserted = _parse_pull_counts(out1, out2)
        payload = {
            "status": "ok",
            "scraped": scraped if scraped is not None else 0,
            "inserted": inserted if inserted is not None else 0,
        }

        if not json_response:
            if scraped is not None or inserted is not None:
                messages.append((f"Pull complete: scraped {scraped or 0}, inserted {inserted or 0}.", "success"))
            else:
                messages.append(("New data pulled and loaded successfully.", "success"))
            if out1:
                messages.append((f"Scraper: {out1[-500:]}", "success"))
            if out2:
                messages.append((f"Loader: {out2[-500:]}", "success"))

    # Handle errors
    except subprocess.CalledProcessError as e:
        status_code = 500
        msg = f"Command failed ({' '.join(e.cmd)}), exit {e.returncode}."
        if e.stderr:
            msg += f" STDERR: {e.stderr[-500:]}"
        payload = {"status": "error", "message": msg}
        if not json_response:
            messages.append((msg, "error"))
    except Exception as e:
        status_code = 500
        msg = f"Pull failed: {e}"
        payload = {"status": "error", "message": msg}
        if not json_response:
            messages.append((msg, "error"))
    finally:
        set_lock(None)

    if json_response:
        return jsonify(payload), status_code

    for message, category in messages:
        flash(message, category)
    return redirect(url_for("index"))

# Update analysis (if needed)
@app.route("/update-analysis", methods=["POST"])
def update_analysis():
    json_response = wants_json_response()

    if is_running():
        if json_response:
            return jsonify(status="busy"), 409
        flash("Please wait until data pull has completed.", "error")
        return redirect(url_for("index"))

    last_pull_ts, _, needs_update = compute_gate_state()
    #If no new successful pull since last analysis, do nothing
    if not needs_update:
        if json_response:
            return jsonify(status="noop", reason="no-new-data"), 409
        # Check if we have ever had a successful pull, if not, say so
        if last_pull_ts is None:
            flash("No new data to update analysis with, please click Pull Data to refresh data.", "info")
        else:
            flash("No new data to update analysis with since the last successful pull.", "info")
        return redirect(url_for("index"))

    # Try to write the analysis timestamp
    try:
        os.makedirs(os.path.dirname(ANALYSIS_FILE), exist_ok=True)
        with open(ANALYSIS_FILE, "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))
    except Exception as e:
        msg = f"Update failed: {e}"
        if json_response:
            return jsonify(status="error", message=msg), 500
        flash(msg, "error")
        return redirect(url_for("index"))

    if json_response:
        return jsonify(status="ok", updated=True), 200

    flash("Analysis updated.", "success")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True, use_reloader=True)
