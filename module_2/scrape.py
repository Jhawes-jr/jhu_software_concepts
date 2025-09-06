import os
import re
import json
import time
import urllib.parse as up

import urllib3
from bs4 import BeautifulSoup

# List page to start from
LIST_URL = "https://www.thegradcafe.com/survey/index.php"

# Output
OUT_PATH = "applicant_data.json"

# Basic headers so the site knows we're a normal client
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _http() -> urllib3.PoolManager:
    return urllib3.PoolManager(
        headers=HEADERS,
        timeout=urllib3.Timeout(connect=5.0, read=10.0),
        retries=urllib3.Retry(
            total=3, 
            connect=2, 
            read=2, 
            status=2, 
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

# Main scraper ---------------------------------------------------------------

def scrape_data(max_entries=31000, sleep_s: float = 0.35) -> None:
    """
    Fetch list pages, follow 'See More' links, read <dt>/<dd> pairs on detail pages,
    and write a single JSON array to applicant_data.json.
    """
    http = _http()
    rows: list[dict] = []

    page = 1
    written = 0

    while written < max_entries:
        print(f"\rFetching page {page}... (total records so far: {written})", end="", flush=True)
        list_url = LIST_URL if page == 1 else f"{LIST_URL}?page={page}"
        r = http.request("GET", list_url)
        if r.status != 200:
            print(f"\nHTTP {r.status} on page {page}, stopping.")
            break

        soup = BeautifulSoup(r.data.decode("utf-8", errors="replace"), "html.parser")
        links = soup.find_all("a", string=lambda s: s and "See More" in s)
        if not links:
            print(f"\nNo links on page {page}, stopping.")
            break

        for a in links:
            detail_url = up.urljoin(LIST_URL, a.get("href"))

            rd = http.request("GET", detail_url)
            
            written += 1
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

            # combine program + institution exactly as shown on the site
            if program_only and institution:
                combined_program = f"{program_only}, {institution}"
            else:
                combined_program = program_only or institution or ""

            # Notification often contains the date text ("on 07/08/2025 via ...")
            decision = data.get("decision")            # Accepted / Rejected / Wait listed / ...
            notification = data.get("notification")    # e.g., "on 07/08/2025 via E-mail"
            status = None
            if decision and notification:
                status = f"{decision} {notification}"
            else:
                status = decision or None

            # term can appear as "term" on some pages; if not present, leave None
            term = data.get("term")

            # comments are under "notes"
            comments = data.get("notes")

            # "Added on" may appear as a label; also try to read it from the list card text
            date_added = data.get("added on")
            if not date_added:
                card = a.find_parent(["article", "li", "div", "section"]) or a.parent
                card_text = _text(card) or ""
                m = re.search(r"\bAdded on\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})", card_text, flags=re.I)
                date_added = m.group(1) if m else None

            # assemble minimal record expected by the later step
            record = {
                "program": combined_program,                 # program + institution combined
                "comments": comments,
                "date_added": date_added,
                "url": detail_url,
                "status": status,
                "term": term,
                "US/International": data.get("degree's country of origin"),
                "Degree": data.get("degree type"),
                "GPA": data.get("undergrad gpa"),
                "GRE": data.get("gre general"),
                "GRE V": data.get("gre verbal"),
                "GRE AW": data.get("analytical writing"),
            }
            rows.append(record)

            time.sleep(sleep_s)  # polite delay between detail requests
        print(f"\nFinished page {page}, total {written} records so far. {written/max_entries:0.4%} done.")
        page += 1
        #time.sleep(0.8)          # polite delay between list pages

    # write as a single JSON array file
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(rows)} records → {OUT_PATH}")


if __name__ == "__main__":
    # adjust max_pages upward later to reach 30k+ entries
    scrape_data(max_entries=31000)
