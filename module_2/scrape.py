import urllib3         # for making HTTP requests
from bs4 import BeautifulSoup       # for parsing HTML
import os                           # for file system stuff, make folders/files, etc.
import json                         # for reading/writing JSON

LIST_URL = "https://www.thegradcafe.com/survey/index.php"    # URL of the page to scrape
CACHE_DIR = ".cache"                                         # temporary holding place for files
RAW_STREAM = os.path.join(CACHE_DIR, "raw_entries.jsonl")    # raw data file

def scrap_data(max_entries=10):
    """Stub: fetches first 10 pages of gradcafe and prints bascic info to test functionality"""
    http = urllib3.PoolManager()  # create an HTTP manager to make requests

    # fetch first page
    r = http.request("GET", LIST_URL)
    if r.status != 200:
        print(f"Error: got HTTP {r.status}")
        return
    
    html = r.data.decode("utf-8")  # decode bytes to string
    soup = BeautifulSoup(html, "html.parser")  # parse HTML

    #print the title of the page
    print("page title:", soup.title.get_text() if soup.title else "No title found")

    #count "See More" links on the page
    links = soup.find_all("a", string=lambda s: s and "See More" in s)
    print(f"Found {len(links)} 'See More' links on the page.")

    #stubbed record
    record = {
        "university": "Stub University",
        "program_name": "Stub Program",
        "comments": None,
        "added_on": None,
        "entry_url": LIST_URL,
        "status": None
    }

    os.makedirs(CACHE_DIR, exist_ok=True)  # ensure cache directory exists
    with open(RAW_STREAM, "w", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")  # write stub record as JSON line

    print(f"Wrote stub record to {RAW_STREAM}")

if __name__ == "__main__":
    scrap_data()
