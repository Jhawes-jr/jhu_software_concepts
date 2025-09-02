import urllib3         # for making HTTP requests
from bs4 import BeautifulSoup       # for parsing HTML
import os                           # for file system stuff, make folders/files, etc.
import json                         # for reading/writing JSON
import time                         # for sleeping between requests
import urllib.parse as up           # for URL encoding

LIST_URL = "https://www.thegradcafe.com/survey/index.php"    # URL of the page to scrape
CACHE_DIR = ".cache"                                         # temporary holding place for files
RAW_STREAM = os.path.join(CACHE_DIR, "raw_entries.jsonl")    # raw data file

HEADERS = {
    "User-Agent": "JHU-EP-Module2-Scraper/0.1 (+student project)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def _http():
    return urllib3.PoolManager(
        timeout=urllib3.Timeout(connect=10.0, read=20.0),                                               # set timeouts
        retries=urllib3.Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504]), # retry on certain HTTP status codes
        headers=HEADERS)                                                                                # default headers for all requests

def _clean_text(s: str | None) -> str | None:
    """Cleans up text by stripping whitespace and normalizing spaces."""   
    if not s:
        return None
    s = " ".join(s.split())
    return s or None

def scrape_data(max_entries: int = 100):
    """Fetch the first results page, parse real entries, and append to .cache/raw_entries.jsonl"""

    os.makedirs(CACHE_DIR, exist_ok=True)                   # ensure cache directory exists
    http = _http()                                          # get HTTP manager

    # fetch first page
    r = http.request("GET", LIST_URL)
    if r.status != 200:
        print(f"Error: got HTTP {r.status}")
        return
    
    # decode and parse HTML
    soup = BeautifulSoup(r.data.decode("utf-8", errors="replace"), "html.parser")  

    #print the title of the page
    print("page title:", soup.title.get_text() if soup.title else "No title found")

    #count "See More" links on the page
    links = soup.find_all("a", string=lambda s: s and "See More" in s)
    print(f"Found {len(links)} 'See More' links on the page.")

    written = 0
    with open(RAW_STREAM, "a", encoding="utf-8") as out: # open for appending new info without overwriting old
        for a in links:
            # detail url
            detail_url = up.urljoin(LIST_URL, a.get("href")) # convert relative to absolute URL

            # "walk" up a few parents up to find "card" container
            card = a
            for _ in range(4):           # go up to 4 levels
                if card.parent:          # if there's a parent
                    card = card.parent   # move up
            block = card.get_text("\n", strip=True) if card else a.get_text("\n", strip=True) # get text block
            lines = [ln for ln in block.split("\n") if ln]                                    # split into non-empty lines
            
            university = _clean_text(lines[0]) if lines else None # first line in the card is usually university name

            program_name = None
            for ln in lines[1:4]:  # check next few lines for something that looks like a program name
                if any(k in ln for k in ("Masters", "PhD", "MBA", "MFA", "PsyD", "JD", "MD", "EdD")):
                    program_name = ln
                    break
            if not program_name and len(lines) > 1: # fallback to second line if no program name found
                program_name = lines[1]
            
            # Look for added on (usually contains month, day, 20XX, so we'll use ", 20" to capture anything that fits that pattern) 
            added_on = next((ln for ln in lines if ", 20" in ln), None)

            # Look for status line (Accepted on, Rejected on, Wait listed on, Interview on)
            status_line = next((ln for ln in lines if any(
                k in ln for k in ("Accepted on", "Rejected on", "Wait listed on", "Interview on"))), None)
            
            # Look for term (Fall, Spring, Summer, Winter)
            term = next((ln for ln in lines if any(t in ln for t in("Fall", "Spring", "Summer", "Winter"))), None)

            # Look for citizenship (International, American)
            citizenship = next((ln for ln in lines if "international" in ln or "American" in ln), None)

            # Look for GPA and GRE
            gpa_line = next((ln for ln in lines if "GPA" in ln), None)
            gre_line = next((ln for ln in lines if "GRE" in ln), None)

            # fetch detail page to get comments (if any)
            comments = None
            try:
                rd = http.request("GET", detail_url)  # fetch detail page
                if rd.status == 200:
                    dsoup = BeautifulSoup(rd.data.decode("utf-8", errors="replace"), "html.parser")
                    for el in dsoup.find_all(["p", "div"]):                  # look for paragraphs or divs
                        t = _clean_text(el.get_text(" ", strip=True))        # get cleaned text
                        # look for something that looks like a comment (longer than 6 words, not a status line)
                        if t and len(t.split()) > 6 and not any(t.startswith(x) for x in ("Accepted on", "Rejected on", "Wait listed on", "Interview on")):
                            comments = t
                            break
            except Exception:
                pass

            # build/define the record dictionary
            record = {
                "university": _clean_text(university),
                "program_name": _clean_text(program_name),
                "added_on": _clean_text(added_on),
                "status_raw": _clean_text(status_line),
                "term_raw": _clean_text(term),
                "citizenship_raw": _clean_text(citizenship),
                "gpa_raw": _clean_text(gpa_line),
                "gre_raw": _clean_text(gre_line),
                "page": 1,  # since we're only fetching the first page
            }

            out.write(json.dumps(record, ensure_ascii=False) + "\n") # write as JSON line
            written += 1
            if written >= max_entries: # if we hit max entries, stop
                break
                                            

    

    print(f"Wrote {written} records to {RAW_STREAM}")
    print("First page scrape complete.")

if __name__ == "__main__":
    scrape_data(max_entries=100)  # scrape up to 100 entries for testing
