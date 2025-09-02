# scrape.py

import urllib3
from bs4 import BeautifulSoup
import os
import json
import time
import re
import urllib.parse as up

LIST_URL = "https://www.thegradcafe.com/survey/index.php"
CACHE_DIR = ".cache"
RAW_STREAM = os.path.join(CACHE_DIR, "raw_entries.jsonl")

# Optional: set True to dump debug HTML files for the first record
DEBUG = False

# Pull the "Added on Month DD, YYYY" from the list card text
ADDED_ON_RE = re.compile(r"\bAdded on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", re.I)

# Map labels seen on detail pages to normalized keys
LABEL_MAP = {
    # institution/program
    "institution": "university",
    "institution name": "university",
    "school": "university",
    "program": "program_name",
    "program name": "program_name",

    # degree / term
    "degree type": "degree_type",
    "term": "term_raw",
    "term of admission": "term_raw",

    # decision / dates
    "decision": "status_raw",
    "notification": "decision_date_raw",
    "notification date": "decision_date_raw",
    "decision date": "decision_date_raw",

    # applicant type / origin
    "degree's country of origin": "citizenship_raw",
    "degree’s country of origin": "citizenship_raw",
    "applicant type": "citizenship_raw",
    "citizenship": "citizenship_raw",

    # academics
    "undergrad gpa": "gpa_raw",
    "undergraduate gpa": "gpa_raw",

    # gre variants
    "gre": "gre_total_raw",
    "gre general": "gre_total_raw",
    "gre total": "gre_total_raw",
    "gre verbal": "gre_v_raw",
    "gre v": "gre_v_raw",
    "verbal": "gre_v_raw",
    "analytical writing": "gre_aw_raw",
    "gre aw": "gre_aw_raw",
    "aw": "gre_aw_raw",

    # notes / comments
    "notes": "comments",

    # sometimes present on detail
    "added on": "added_on_raw",
}

HEADERS = {
    "User-Agent": "GradScraper/0.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def _norm_label(txt: str) -> str:
    t = (txt or "")
    t = t.replace("’", "'")  # normalize curly apostrophes
    t = " ".join(t.split()).strip().lower()
    return t[:-1].strip() if t.endswith(":") else t

def _dd_for_dt(dt):
    # On these pages, <dt> and <dd> are siblings inside the same <dl>
    return dt.find_next_sibling("dd")

def scrape_data(max_entries: int = 20):
    os.makedirs(CACHE_DIR, exist_ok=True)

    http = urllib3.PoolManager(
        headers=HEADERS,
        timeout=urllib3.Timeout(connect=5.0, read=10.0),
        retries=urllib3.Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504]),
    )

    written = 0
    page = 1

    with open(RAW_STREAM, "w", encoding="utf-8") as out:
        while written < max_entries:
            url = LIST_URL if page == 1 else f"{LIST_URL}?page={page}"
            r = http.request("GET", url)
            if r.status != 200:
                break

            soup = BeautifulSoup(r.data.decode("utf-8", errors="replace"), "html.parser")
            if page == 1:
                print("Page title:", soup.title.get_text(strip=True) if soup.title else "(no title)")
            links = soup.find_all("a", string=lambda s: s and "See More" in s)
            if not links:
                break

            for idx, a in enumerate(links):
                if written >= max_entries:
                    break

                detail_url = up.urljoin(LIST_URL, a.get("href"))

                # Added-on from list card (fallback)
                card = a.find_parent(["article", "li", "div", "section"]) or a.parent
                card_text = card.get_text(" ", strip=True) if card else ""
                m = ADDED_ON_RE.search(card_text)
                added_on_from_list = m.group(1) if m else None

                # Fetch detail page
                rd = http.request("GET", detail_url)
                if rd.status != 200:
                    time.sleep(0.2)
                    continue

                html = rd.data.decode("utf-8", errors="replace")
                dsoup = BeautifulSoup(html, "html.parser")

                # Optional debug dumps for the first record only
                if DEBUG and written == 0:
                    with open(os.path.join(CACHE_DIR, "debug_detail_page.html"), "w", encoding="utf-8") as f:
                        f.write(dsoup.prettify())
                    if card:
                        with open(os.path.join(CACHE_DIR, "debug_card.html"), "w", encoding="utf-8") as f:
                            f.write(card.prettify())
                    dls = dsoup.find_all("dl")
                    for j, dl_block in enumerate(dls):
                        with open(os.path.join(CACHE_DIR, f"debug_dl_{j}.html"), "w", encoding="utf-8") as f:
                            f.write(dl_block.prettify())
                    with open(os.path.join(CACHE_DIR, "debug_pairs.txt"), "w", encoding="utf-8") as f:
                        for dl_block in dsoup.find_all("dl"):
                            for dt in dl_block.find_all("dt"):
                                dd = _dd_for_dt(dt)
                                f.write(
                                    f"DT: {_norm_label(dt.get_text(' ', strip=True))} | "
                                    f"DD: {(dd.get_text(' ', strip=True) if dd else None)}\n"
                                )

                # Parse all <dl> blocks on the page
                record = {}
                for dl in dsoup.find_all("dl"):
                    for dt in dl.find_all("dt"):
                        dd = _dd_for_dt(dt)
                        if not dd:
                            continue
                        label = _norm_label(dt.get_text(" ", strip=True))
                        value = " ".join(dd.get_text(" ", strip=True).split()) or None
                        key = LABEL_MAP.get(label)
                        if key:
                            record[key] = value

                # Ensure keys exist
                for k in [
                    "university", "program_name", "degree_type", "citizenship_raw",
                    "status_raw", "decision_date_raw", "gpa_raw", "gre_total_raw",
                    "gre_v_raw", "gre_aw_raw", "comments", "term_raw", "added_on_raw"
                ]:
                    record.setdefault(k, None)

                if record.get("added_on_raw") is None:
                    record["added_on_raw"] = added_on_from_list

                record["detail_url"] = detail_url
                record["page"] = page

                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1
                time.sleep(0.3)

            page += 1

    print(f"Wrote {written} record(s) → {RAW_STREAM}")

if __name__ == "__main__":
    try:
        scrape_data(max_entries=40)
    except KeyboardInterrupt:
        print("\nStopped by user.")
