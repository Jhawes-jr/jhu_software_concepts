import json
import os
import re

IN_PATH = "applicant_data.json"      # input from scrape.py (JSON array)
OUT_PATH = "applicant_data_clean.json"     # new cleaned data (JSON array)

# regex helpers
TAG_RE = re.compile(r"<[^>]+>")      # remove any leftover HTML tags
SPACE_RE = re.compile(r"\s+")        # collapse whitespace
DATE_FROM_STATUS_RE_NUM  = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
DATE_FROM_STATUS_RE_TEXT = re.compile(r"\b([A-Za-z]+\s+\d{1,2},\s*\d{4})\b")

FIELDS = [
    "program", "comments", "date_added", "url", "status", "term",
    "US/International", "Degree", "GPA", "GRE", "GRE V", "GRE AW",
]

def _clean_text(s):
    """Return normalized text or None."""
    if s is None:
        return None
    # strip HTML if someone pasted tags into a notes field, etc.
    s = TAG_RE.sub("", str(s))
    # collapse whitespace and trim
    s = SPACE_RE.sub(" ", s).strip()
    return s or None

def load_data(path: str = IN_PATH):
    """Load JSON array written by scrape.py."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def clean_data(rows):
    """
    Light normalization:
    - strip HTML + extra spaces
    - normalize empties to None
    - leave `program` untouched (LLM will split later)
    - extract acceptance/rejection date from `status` if present
    """
    out = []

    cleaned_files = len(rows)
    for i, r in enumerate(rows, 1):
        rec = {}
        for k in FIELDS:
            rec[k] = _clean_text(r.get(k))

        status = rec.get("status") or ""
        status_l = status.lower()

        acceptance_date = None
        rejection_date  = None

        m = DATE_FROM_STATUS_RE_NUM.search(status) or DATE_FROM_STATUS_RE_TEXT.search(status)

        if "accepted" in status_l and m:
            acceptance_date = m.group(1)
        elif "rejected" in status_l and m:
            rejection_date = m.group(1)

        rec["acceptance_date"] = acceptance_date
        rec["rejection_date"]  = rejection_date

        if i % 500 == 0 or i ==1 or i == cleaned_files:
            print(f"Total cleaned files = {i/cleaned_files:0.1%}.")

        out.append(rec)
        
    return out

def save_data(rows, path: str = OUT_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

def main():
    rows = load_data()
    cleaned = clean_data(rows)
    save_data(cleaned)
    print(f"Wrote {len(cleaned)} rows → {OUT_PATH}")

if __name__ == "__main__":
    main()


