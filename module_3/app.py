# module_3/app.py
from flask import Flask, render_template, redirect, url_for, flash, request
from query_data import compute_stats
import subprocess, os, sys, signal

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")
app.config["TEMPLATES_AUTO_RELOAD"] = True

# --- Commands ---
SCRAPER_CMD = [sys.executable, "module_2/scrape.py", "--incremental"]  # adjust flag if needed
JSONL_PATH  = os.getenv("APP_JSONL", "module_2/llm_extend_applicant_data.jsonl")
LOADER_CMD  = [sys.executable, "module_3/load_data.py", JSONL_PATH]

# --- PID lock (rather than empty file) ---
LOCK_FILE = "module_2/scrape.lock"

def is_running():
    """Return True if a PID in LOCK_FILE exists and is alive."""
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        # On Windows, os.kill with 0 also checks existence (raises OSError if not running)
        os.kill(pid, 0)
        return True
    except FileNotFoundError:
        return False
    except (ValueError, ProcessLookupError, OSError):
        # Stale lock or process not found
        try: os.remove(LOCK_FILE)
        except FileNotFoundError: pass
        return False

def set_lock(pid: int | None):
    if pid is None:
        try: os.remove(LOCK_FILE)
        except FileNotFoundError: pass
    else:
        os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
        with open(LOCK_FILE, "w") as f:
            f.write(str(pid))

# --- Routes ---
@app.route("/")
def index():
    stats = compute_stats()
    return render_template(
        "index.html",
        running=is_running(),
        **stats   # <- spread keys so I can still use {{ q1 }}, {{ q2 }}, etc.
    )

@app.route("/pull-data", methods=["POST"])
def pull_data():
    if is_running():
        flash("A data pull is already running. Please wait for it to finish.", "error")
        return redirect(url_for("index"))

    try:
        # 1) Scrape (incremental)
        p1 = subprocess.Popen(SCRAPER_CMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        set_lock(p1.pid)
        out1, err1 = p1.communicate()
        if p1.returncode != 0:
            raise subprocess.CalledProcessError(p1.returncode, SCRAPER_CMD, output=out1, stderr=err1)

        # 2) Load JSONL into Postgres
        p2 = subprocess.Popen(LOADER_CMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out2, err2 = p2.communicate()
        if p2.returncode != 0:
            raise subprocess.CalledProcessError(p2.returncode, LOADER_CMD, output=out2, stderr=err2)

        flash("New data pulled and loaded successfully.", "success")
        if out1: flash(f"Scraper: {out1[-500:]}", "success")
        if out2: flash(f"Loader: {out2[-500:]}", "success")

    except subprocess.CalledProcessError as e:
        msg = f"Command failed ({' '.join(e.cmd)}), exit {e.returncode}."
        if e.stderr: msg += f" STDERR: {e.stderr[-500:]}"
        flash(msg, "error")
    except Exception as e:
        flash(f"Pull failed: {e}", "error")
    finally:
        set_lock(None)

    return redirect(url_for("index"))

@app.route("/update-analysis", methods=["POST"])
def update_analysis():
    if is_running():
        flash("Cannot update while a data pull is running.", "error")
        return redirect(url_for("index"))
    # index() recomputes stats on render.
    flash("Analysis refreshed.", "success")
    return redirect(url_for("index"))

if __name__ == "__main__":
    # For Windows + reloader edge cases, avoid forking issues by disabling the reloader if needed:
    app.run(host="0.0.0.0", port=8080, debug=True, use_reloader=True)
