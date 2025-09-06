Name: Joe Hawes

Module Info: Module 2 — Web Scraping

OVERVIEW

This assignment collects recent applicant entries from The GradCafe, saves them as a JSON array, performs light cleaning (regex/string), and then runs the provided LLM to add two standardized fields. The scraper utilizes urllib3 + BeautifulSoup + string/regex and I intentionally preserved the raw “program” string (which often mixes program and institution) so that Part 2 can standardize it.

REPOSITORY STRUCTURE (RELEVANT FILES)

module_2/
scrape.py # urllib3 + BeautifulSoup scraper
clean.py # light cleaner (regex and string ops)
applicant_data.json # JSON array output from scrape.py
applicant_data_clean.json # JSON array output from clean.py
llm_extend_applicant_data.json # NDJSON produced by the LLM standardizer
robots_screenshot.png # screenshot of https://www.thegradcafe.com/robots.txt

requirements.txt 
# Part 1 deps: beautifulsoup4, urllib3
.cache/ # transient/debug files
llm_hosting/ # instructor-provided mini-LLM tool 
# Part 2
app.py
requirements.txt # Flask, huggingface_hub, llama-cpp-python
canon_programs.txt
canon_universities.txt
sample_data.json

ENVIRONMENT

Python 3.11 - venv created becasue of early issues running llm on 3.13 - no prebuilt wheel caused compile and fail issues.

Part 1 requirements (module_2/requirements.txt): beautifulsoup4, urllib3.

Part 2 LLM tool uses its own virtual environment under module_2/llm_hosting with:
Flask, huggingface_hub, llama-cpp-python (CPU wheel on Windows).

ROBOTS.TXT COMPLIANCE

I manually checked https://www.thegradcafe.com/robots.txt
 (screenshot saved as module_2/robots_screenshot.png).

For User-agent: * the site disallows only:
/cgi-bin/ and /index-ad-test.php
No crawl-delay was posted at the time I checked.

My scraper visits:
/survey/ and /survey/index.php (listing pages)
/result/<id> (detail pages)
These paths are allowed for User-agent: *.

During development I used a small delay between requests to be polite; for the final large run I minimized delays so the job could complete in a reasonable time while remaining respectful (although this didn't seem to have a huge impact on runtime).

APPROACH (DETAILED)

Note: This took quite a bit of effort and multiple iterations of every step (scrape, clean, setting up llm on windows machine, etc.) to get right (Sunday through Friday, most of the entire day, every day. 
But I think I finally got it working in a way that replicates the info available on the assignment, hopefully I didn't miss something obvious in all the back and forth)

Scraping with urllib3 + BeautifulSoup (scrape.py)

I request the listing page at https://www.thegradcafe.com/survey/index.php and find all “See More” links using BeautifulSoup’s string matching.

For each link I build the absolute detail URL with urllib.parse.urljoin, fetch the detail page, and parse the <dl> structure by pairing each <dt> label with its next <dd>.

I normalize labels (lowercasing, trimming trailing “:”) and map them into standard output keys (e.g., Institution → program’s university component, Program, Degree Type, US/International, Notification, GRE, GRE V, GRE AW, Undergrad GPA, Notes, Term, Added on, etc.). Missing values are stored as null (JSON None).

I preserve the raw “program” text exactly as shown on the site (often “Program, University”). I do not split or standardize it in Part 1 by design.

Records are accumulated in a Python list and written as a single JSON array to applicant_data.json.

Pagination: I iterate pages /survey/index.php?page=N until approximately reaching the target count. The site tends to show  around 20 entries per page, so  around 1,500–1,600 pages are needed to exceed 30,000 entries. (current max_entries set to 31,000)

Progress feedback: I didn't like the idea of running the scaled version of the scraper and waiting for it to finish with no feedback so I wrote a minimal in-place counter that prints the current page, total records written, and % complete.

Light Cleaning (clean.py)

Input: applicant_data.json (JSON array).

For each row:

Strip any stray HTML tags with <...> regex and collapse whitespace.

Normalize empty strings to null.

Leave program unchanged (don't make it perfect, thats what the llm is for)

Parse acceptance/rejection date from the free-text status field using two regex patterns:

Numeric dates: \d{1,2}/\d{1,2}/\d{4}

Dates with text: Month DD, YYYY
If the status contains “accepted” and a date, set acceptance_date; if it contains “rejected” and a date, set rejection_date; otherwise leave them null.

Output: applicant_data_clean.json (JSON array).

Part 2: Instructor-Provided LLM Standardizer (module_2/llm_hosting/app.py)

I run the provided Flask/llama-cpp-python script in CLI mode to append two standardized fields:
llm-generated-program
llm-generated-university

The first run downloads a small TinyLlama .gguf model via huggingface_hub; subsequent runs use the cached model.

The tool reads applicant_data_clean.json and writes NDJSON (one JSON object per line) to llm_extend_applicant_data.json. I did not modify the tool’s logic.

WHAT I TRIED/FAILED / ISSUES ENCOUNTERED

Over-engineering attempt: My first scraper iteration tried to find the "area" that the required fields were at in the html and the step up parent folders until it found something macthing. Spent way too much time on this and never worked.
I then realized that I could just right click -> examine on the GradCafe website to see exactly where something was in the source html. This seemingly obvious thought helped a lot with being able to start trying to have the scraper correctly locate important info on the page.
I needed a way to "see" what the scraper was seeing when running (It would just return nulls and I didnt know why specifically) So i created a .cache to help with debugging only fetching 1 file. 
First with the entire html for the detail page which was way too much, then the card which wasn't helpful, then everything in the dl class which was the rigth amount of granularity.
With this i could see the exact record and what the correct values for each category shoudl be. (for some reason, what the scraper fetched did not match what i coudl see on the page itself so this was helpful for some unfmailiar institutions that threw me off: see next section)

Unexpected content: Some entries included surprising strings (e.g., “42 US” for institution). I encountered this before deploying the debug and it threw me off for quite a while.
I thought that I was somehow combining the end fo one string and the beginning of another because how else could be pulling "US 42" in for institution on 2 out of 10 records if everything was working. This was a coincidence I guess with 2 people using this as their institution.
After alot of back and forth and then finally getting the debug to work, I dumped a single record’s HTML in for inspection, and realized that this was indeed the correct input. If you're wondering, its a peer to peer coding thing with no real classes but people reference it in place of a traditional university I guess.

Windows setup for the LLM:

llama-cpp-python initially didn’t provide a suitable Windows wheel; I had never heard of this before but ended up looking into it a bit to try and figure out why is wasn't working.
Set up a couple different virtual environments to try and run differnet, slightly older, versions of python (maybe those had prebuilt wheels that i could access) to try and get it run.
Bascially, as far as I understand it, it would return build errors because there was no prebuilt wheel for the version of python that I was running on my windows machine (python 3.13) so it would try to compile it at runtime and fail do to one reason or another.  

I installed the prebuilt CPU wheel for python 3.11 from the maintainer’s wheel index, which resolved it. I just need to run the llm portion of this locally within my venv311 virtual environment. No biggie.

The first model download from Hugging Face was slow/intermittent; after caching, runs were quick.

Git line-ending warnings (LF vs CRLF) appeared on Windows; these were benign and did not affect execution.

HOW TO RUN

All commands below are based on what I run in the terminal in VS Code.

Scrape 
cd to module_2
python scrape.py
Current script has max_entries set to 31000 per assignment. Adjust as necessary

Clean
From module_2:
python clean.py
This reads applicant_data.json from scrape.py and writes applicant_data_clean.json.

LLM Standardize (provided tool)
cd module_2\llm_hosting
..venv311\Scripts\Activate.ps1
python app.py --file "..\applicant_data_clean.json" --out "..\llm_extend_applicant_data.json"
This writes NDJSON with the two LLM fields.

DELIVERABLES PRODUCED

scrape.py, clean.py

applicant_data.json (JSON array, ≥ 30,000 rows)

applicant_data_clean.json (JSON array)

llm_extend_applicant_data.json (NDJSON with LLM fields added)

robots_screenshot.png

requirements.txt (scraper)

llm_hosting/ (provided tool)

KNOWN BUGS / LIMITATIONS (AND HOW I WOULD FIX THEM)

Date parsing from status is intentionally minimal (first numeric or textual date); unusual phrasing may be missed.
Fix approach: expand regex patterns and add more targeted parsing for “on … via …” variations.

Missing fields are stored as null for consistency; downstream code must handle nulls explicitly.

Site layout changes (label text or HTML structure) would require updating the label map or the <dt>/<dd> pairing logic.
Fix approach: add small unit tests against saved HTML snippets to detect breakage early.

Runtime: Tried minimizing sleep time to speed up the larger runtime but ran into issues. Needed to implement measures to slow rate of connections, timeouts, etc. Second run successful at 30,999 records.
Fix approach: add adaptive pacing (increase tiny delays when many timeouts/429s occur).

LLM optimization: Initial installation/setup of llm resulted in everything being processed by the CPU which is not ideal. Maxed out the CPU utlization at 100% and was super slow. 
Fix approach: Had to completely uninstall everything associated with previous llm setup. 
Used exisiting WSL2 and Ubuntu installations on windows machine to install necessary CUDA wheel to offload compute to GPU. Used ChatGPT to optimize envirnoment variables for dedciated GPU run.
Took forever to get working but was also fun to get back into linux.

END OF FILE