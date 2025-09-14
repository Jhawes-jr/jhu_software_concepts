# module_3/load_data.py

import json
import sys
from datetime import datetime
from db import get_conn
import re


# parse floats, return None if invalid
def parse_float(x):
    if x is None: 
        return None
    try:
        return float(str(x).strip())
    except:
        return None

# Parse dates in using common formats.
def parse_date(x):
    if not x:
        return None
    for fmt in (
        "%Y-%m-%d",   # 2025-09-14
        "%m/%d/%Y",   # 09/14/2025
        "%b %d, %Y",  # Sep 14, 2025
        "%B %d, %Y",  # September 14, 2025  <-- THIS was missing
        "%d-%b-%Y",   # 14-Sep-2025
    ):
        try:
            return datetime.strptime(x.strip(), fmt).date()
        except Exception:
            continue
    return None


def parse_status(s):
    if not s:
        return None, None
    m = re.match(r"^([^\d]+)\s+on\s+(\d{2}/\d{2}/\d{4})", s.strip())
    if not m:
        return None, None
    status_type = m.group(1).strip()
    status_date = parse_date(m.group(2))  # reuse your parse_date
    return status_type, status_date


#Get each JSON object from a file.
def iter_records(path):
    with open(path, encoding="utf-8") as f:
        first = f.read(1)
        while first.isspace():
            first = f.read(1)
        f.seek(0)
        if first == "[":
            for obj in json.load(f):
                yield obj
        else:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

# Insert SQL with all fields (use ON CONFLICT to avoid dups)
# Insert SQL with all fields (use ON CONFLICT to avoid dups)
INSERT_SQL = """
INSERT INTO applicants
(program, comments, date_added, url, status, term, us_or_international,
 gpa, gre, gre_v, gre_aw, degree, llm_generated_program, llm_generated_university)
VALUES (%(program)s, %(comments)s, %(date_added)s, %(url)s, %(status)s, %(term)s,
        %(us_or_international)s, %(gpa)s, %(gre)s, %(gre_v)s, %(gre_aw)s, %(degree)s,
        %(llm_generated_program)s, %(llm_generated_university)s)
ON CONFLICT (url) DO NOTHING;
"""

def main(path, limit=None):
    n = 0
    with get_conn() as conn, conn.cursor() as cur:
        for obj in iter_records(path):
            payload = {
                "program": obj.get("program"),
                "comments": obj.get("comments"),
                "date_added": parse_date(obj.get("date_added")),
                "url": obj.get("url"),
                "status": obj.get("status"),  # <-- raw status string
                "term": obj.get("term"),
                "us_or_international": obj.get("US/International"),
                "gpa": parse_float(obj.get("GPA")),
                "gre": parse_float(obj.get("GRE")),        # Quant
                "gre_v": parse_float(obj.get("GRE V")),    # Verbal
                "gre_aw": parse_float(obj.get("GRE AW")),  # Writing
                "degree": obj.get("Degree"),
                "llm_generated_program": obj.get("llm-generated-program"),
                "llm_generated_university": obj.get("llm-generated-university"),
            }
            cur.execute(INSERT_SQL, payload)
            n += 1
            if limit is not None and n >= limit:
                break
    print(f"Inserted rows: {n}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("Usage: python module_3/load_data.py <path.jsonl|.json> [limit]")
        sys.exit(1)
    path = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) == 3 else None
    main(path, limit)

