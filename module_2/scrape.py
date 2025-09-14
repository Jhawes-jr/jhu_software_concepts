# module_2/scrape.py
# Scrapes GradCafe entries, appends NEW rows (since the last run) to JSONL,
# and updates last_run.txt with the latest scraped "Added on" date.

import re
import json
import time
import argparse
from datetime import datetime, date, timedelta
import urllib.parse as up
from pathlib import Path

import urllib3
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LIST_URL = "https://www.thegradcafe.com/survey/index.php"

# Paths are relative to this file's directory
HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "last_run.txt"                      # flat file storing YYYY-MM-DD
JSONL_PATH_DEFAULT = HERE / "llm_extend_applicant_data.jsonl"  # incremental output

# Basic headers so the site knows we're a normal client
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DEFAULT_BACKFILL_DAYS = 7  # if last_run.txt missing, only look back this many days

# ---------------------------------------------------------------------------
# HTTP + utils
# ---------------------------------------------------------------------------

def _http() -> urllib3.PoolManager:
    return urllib3.PoolManager(
        headers=HEADERS,
        timeout=urllib3.Timeout(connect=5.0, read=12.0),
        retries=urllib3.Retry(
            total=3, connect=2, read=2, status=2,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False
        ),
    )

def _norm_label(txt: str) -> str:
    """lowercase, strip, remove trailing colon"""
    t = " ".join((txt or "").split()).strip().lower()
    return t[:-1] if t.endswith(":") else t

def _text(el) -> str | None:
    if not el:
        return None
    s = " ".join(el.get_text(" ", strip=True).split()).strip()
    return s or None

def parse_added_on(s: str | None) -> date | None:
    """Parse 'Month D, YYYY' to date (e.g., 'September 7, 2025')."""
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%B %d, %Y").date()
    except Exception:
        return None

# ---------------------------------------------------------------------------
# GRE extraction
# ---------------------------------------------------------------------------

def _to_float(s: str | None):
    if s is None:
        return None
    try:
        return float(str(s).strip())
    except Exception:
        return None

def extract_gre(raw_text: str):
    """
    Try to extract (Q, V, AW) from free text. Returns (q, v, aw) floats or None.
    Handles common forms:
      - 'Q 170 V 165 AW 4.5'
      - 'GRE (Q/V/W): 170/165/4.5' or '(V/Q/W): 165/170/5.0'
      - '170Q/165V/4.5W'
      - 'V: 165, Q: 170, AW: 4.5'
    """
    if not raw_text:
        return (None, None, None)
    t = " ".join(raw_text.split())

    # labeled singletons (most reliable)
    qm = re.search(r'\bQ\s*[:=]?\s*(\d{2,3})\b', t, flags=re.I)
    vm = re.search(r'\bV\s*[:=]?\s*(\d{2,3})\b', t, flags=re.I)
    awm = re.search(r'\b(?:AW|A\.?W\.?|W(?:riting)?)\s*[:=]?\s*([0-6](?:\.\d)?)\b', t, flags=re.I)
    q = _to_float(qm.group(1)) if qm else None
    v = _to_float(vm.group(1)) if vm else None
    aw = _to_float(awm.group(1)) if awm else None
    if q or v or aw:
        return (q, v, aw)

    # parenthesized order hints
    m = re.search(r'\(Q/V/W\)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})\s*/\s*([0-6](?:\.\d)?)', t, flags=re.I)
    if m:
        return (_to_float(m.group(1)), _to_float(m.group(2)), _to_float(m.group(3)))
    m = re.search(r'\(V/Q/W\)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})\s*/\s*([0-6](?:\.\d)?)', t, flags=re.I)
    if m:
        return (_to_float(m.group(2)), _to_float(m.group(1)), _to_float(m.group(3)))

    # '170Q/165V/4.5W' or variations with spaces
    qm = re.search(r'(\d{2,3})\s*Q\b', t, flags=re.I)
    vm = re.search(r'(\d{2,3})\s*V\b', t, flags=re.I)
    awm = re.search(r'([0-6](?:\.\d)?)\s*(?:AW|W)\b', t, flags=re.I)
    if qm or vm or awm:
        return (_to_float(qm.group(1)) if qm else None,
                _to_float(vm.group(1)) if vm else None,
                _to_float(awm.group(1)) if awm else None)

    return (None, None, None)

# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

def scrape_data(*, sleep_s: float, since: date, jsonl_out: Path) -> None:
    """
    Fetch list pages, follow 'See More' links, read <dt>/<dd> pairs on detail pages,
    and append NEW rows (Added on >= since) to JSONL file.
    """
    http = _http()

    appended = 0
    min_date, max_date = None, None
    page = 1
    seen_old = False  # flip to True once we hit a page with only old items

    # open the jsonl for append once
    jsonl_out.parent.mkdir(parents=True, exist_ok=True)
    f_out = open(jsonl_out, "a", encoding="utf-8")

    try:
        while True:
            print(f"\rFetching page {page}... (appended so far: {appended})", end="", flush=True)
            list_url = LIST_URL if page == 1 else f"{LIST_URL}?page={page}"
            r = http.request("GET", list_url)
            if r.status != 200:
                print(f"\nHTTP {r.status} on page {page}, stopping.")
                break

            soup = BeautifulSoup(r.data.decode("utf-8", errors="replace"), "html.parser")
            links = soup.find_all("a", string=lambda s: s and "See More" in s)
            if not links:
                print(f"\nNo 'See More' links on page {page}, stopping.")
                break

            # track whether this page had any new items at all
            page_had_new = False

            for a in links:
                # Try to read 'Added on ...' from the card BEFORE fetching details
                card = a.find_parent(["article", "li", "div", "section"]) or a.parent
                card_text = _text(card) or ""
                m = re.search(r"\bAdded on\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})", card_text, flags=re.I)
                card_added = parse_added_on(m.group(1)) if m else None

                # Early skip if we know it's older than cutoff
                if card_added and card_added < since:
                    continue

                detail_url = up.urljoin(LIST_URL, a.get("href"))
                rd = http.request("GET", detail_url)
                if rd.status != 200:
                    continue

                dsoup = BeautifulSoup(rd.data.decode("utf-8", errors="replace"), "html.parser")

                # Collect all <dt>/<dd> into a dict of normalized label -> value
                data = {}
                for dt in dsoup.find_all("dt"):
                    dd = dt.find_next_sibling("dd")
                    if not dd:
                        continue
                    label = _norm_label(_text(dt) or "")
                    value = _text(dd)
                    if label and value is not None:
                        data[label] = value

                # Map labels found on the site to the exact output keys
                institution = data.get("institution")
                program_only = data.get("program")
                if program_only and institution:
                    combined_program = f"{program_only}, {institution}"
                else:
                    combined_program = program_only or institution or ""

                # Notification often contains the date text ("on 07/08/2025 via ...")
                decision = data.get("decision")
                notification = data.get("notification")
                status = f"{decision} {notification}" if (decision and notification) else (decision or None)

                term = data.get("term")
                comments = data.get("notes")

                # Prefer explicit "Added on" from the detail page
                date_added_str = data.get("added on")
                date_added = parse_added_on(date_added_str) if date_added_str else None
                # Fall back to card-level "Added on" we captured on the list page
                if not date_added and card_added:
                    date_added = card_added
                    date_added_str = card_added.strftime("%B %d, %Y")

                # Cutoff check with final date
                if date_added and date_added < since:
                    continue

                # ---- GRE extraction ----
                gre_q = _to_float(data.get("gre general"))
                gre_v = _to_float(data.get("gre verbal"))
                gre_aw = _to_float(data.get("analytical writing"))
                if gre_q is None or gre_v is None or gre_aw is None:
                    blob = " | ".join(filter(None, [
                        program_only, institution, decision, notification, comments,
                        data.get("test scores"), data.get("additional info"), data.get("score")
                    ]))
                    q2, v2, aw2 = extract_gre(blob)
                    gre_q = gre_q if gre_q is not None else q2
                    gre_v = gre_v if gre_v is not None else v2
                    gre_aw = gre_aw if gre_aw is not None else aw2

                record = {
                    "program": combined_program,                 # program + institution combined
                    "comments": comments,
                    "date_added": date_added_str,                # string; loader parses to DATE
                    "url": detail_url,
                    "status": status,
                    "term": term,
                    "US/International": data.get("degree's country of origin"),
                    "Degree": data.get("degree type"),
                    "GPA": data.get("undergrad gpa"),
                    "GRE": gre_q,            # Quantitative
                    "GRE V": gre_v,          # Verbal
                    "GRE AW": gre_aw,        # Analytical Writing
                }

                # Append to JSONL
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                appended += 1
                page_had_new = True

                # track min/max dates of scraped items
                if date_added:
                    if (min_date is None) or (date_added < min_date):
                        min_date = date_added
                    if (max_date is None) or (date_added > max_date):
                        max_date = date_added

                time.sleep(sleep_s)  # polite delay between detail requests

            # If the page had no new items and many cards showed older-than-since,
            # we can opportunistically stop (pagination is chronological)
            if not page_had_new:
                seen_old = True

            if seen_old and not page_had_new:
                print(f"\nNo new items encountered on page {page}. Stopping.")
                break

            print(f"\nFinished page {page}, appended {appended} records so far.")
            page += 1

    finally:
        f_out.close()

    # Summary
    if min_date or max_date:
        print(f"Scraped date range this run: {min_date} to {max_date}")
    else:
        print("Scraped date range this run: (no valid 'Added on' dates parsed)")

    # Update last_run.txt to the max scraped date (best effort)
    if max_date:
        STATE_FILE.write_text(max_date.strftime("%Y-%m-%d"), encoding="ascii")
        print(f"Updated {STATE_FILE.name} → {max_date.strftime('%Y-%m-%d')}")
    else:
        # If nothing appended, keep last_run.txt as-is (or create with today's date if missing)
        if not STATE_FILE.exists():
            today_iso = date.today().strftime("%Y-%m-%d")
            STATE_FILE.write_text(today_iso, encoding="ascii")
            print(f"No new items. Initialized {STATE_FILE.name} to {today_iso}")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def resolve_since(cli_since: str | None) -> date:
    """Determine the cutoff date (YYYY-MM-DD) to use."""
    if cli_since:
        try:
            return datetime.strptime(cli_since, "%Y-%m-%d").date()
        except ValueError:
            print(f"Invalid --since format: {cli_since} (expected YYYY-MM-DD). Falling back to state.")
    if STATE_FILE.exists():
        txt = STATE_FILE.read_text(encoding="ascii").strip()
        try:
            return datetime.strptime(txt, "%Y-%m-%d").date()
        except ValueError:
            print(f"Warning: {STATE_FILE.name} content not parseable ('{txt}'). Using default backfill.")
    # Default: look back a small window to avoid huge first run
    return date.today() - timedelta(days=DEFAULT_BACKFILL_DAYS)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape GradCafe posts (only NEW records by default).")
    parser.add_argument("--since", type=str, default=None, help="Only include posts Added on or after YYYY-MM-DD (overrides last_run.txt)")
    parser.add_argument("--sleep", type=float, default=0.35, help="Delay between detail requests (seconds)")
    parser.add_argument("--jsonl-out", type=str, default=str(JSONL_PATH_DEFAULT), help="Append results to this JSONL file")
    args = parser.parse_args()

    cutoff = resolve_since(args.since)
    print(f"Cutoff (Added on ≥): {cutoff.isoformat()}")
    scrape_data(sleep_s=args.sleep, since=cutoff, jsonl_out=Path(args.jsonl_out))
