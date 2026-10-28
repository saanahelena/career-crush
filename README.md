# Career Crush: European early-career job collection

Collect real API listings with Python 3.9+ and no extra packages. No website or
Supabase connection is included.

## Run in the VS Code terminal

Open this folder in VS Code, select **Terminal → New Terminal**, and run:

```sh
python3 collect_jobs.py
```

The default limit is **500 unique listings**. Output files are beside the script
in `data/`, regardless of the terminal's current folder:

- `jobs.csv`: the collected listings, replacing the previous CSV.
- `jobs.report.json`: country counts, duplicate occurrences removed, exclusions,
  per-search result counts and completion status, errors, and stop reason.

The terminal prints the same summary, including empty searches and searches
that were skipped or unfinished. A country with zero collected rows is not
necessarily an empty API search: inspect its search statuses in the report.

Examples:

```sh
# Smaller run (may stop before all searches finish)
python3 collect_jobs.py --limit 50

# Reproduce the original Portugal internship search
python3 collect_jobs.py --countries PT --keywords internship --limit 100

# Select countries and keywords; quote multi-word keywords
python3 collect_jobs.py --countries FI PT --keywords graduate "business analyst"

# Slower pacing and a smaller total page budget
python3 collect_jobs.py --delay 5 --max-pages 100
```

## Countries, searches, and source coverage

Configured countries: Finland (FI), Portugal (PT), Germany (DE), Netherlands
(NL), Sweden (SE), Denmark (DK), Belgium (BE), and France (FR).

Keywords: internship, intern, trainee, graduate, junior, strategy, consulting,
sustainability, business analyst, and business development.

**The source currently covers Portugal, Brazil, and Angola, not all of Europe.**
The collector checks `/api/v1/countries` once per run. Configured countries absent
from that index are reported as `country_unavailable` with zero collected jobs;
their keyword searches are skipped to avoid unnecessary requests. If the source
adds those countries, they will be searched automatically. This is source
coverage, not evidence that those countries have no opportunities elsewhere.

Each available country is searched with every configured keyword. The collector
visits the first page of every search before deeper pages, follows pagination,
and stops at 500 unique listings, search exhaustion, an error, or the page budget.
A successful empty search is reported as `no_results`. `not_searched`, `pending`,
and `limit_reached` indicate incomplete searches, not empty ones.

## Early-career focus and prioritization

A listing must have an internship, intern, trainee, graduate, junior, or entry-level
signal in its title/contract type, or an explicit early-career experience level.
Portuguese internship title terms are also recognized. Clearly senior titles
(senior, principal, director, head, lead) are excluded. Missing/mismatched country
codes are excluded rather than replaced with the requested country.

This is a transparent heuristic, not a guarantee of eligibility. Broad searches
such as strategy and consulting can return experienced roles; those without
positive early-career evidence are excluded. Relevant jobs with ambiguous or
unrecognized titles/metadata can be missed.

Within each fetched page and in the final CSV, results mentioning consulting,
strategy, international business, sustainability/ESG, business development,
finance, marketing, or business analysis rank first. This is a local relevance
ordering, not a complete ranking of every job in the API. It does not invent
listings, skills, or experience levels.

## CSV and duplicate handling

Columns: `title`, `company`, `location`, `country`, `description`,
`required_skills`, `experience_level`, `job_type`, `publication_date`,
`original_job_url`.

HTML descriptions become plain text, skills are semicolon-separated, missing
values are blank, and API publication timestamps are preserved. `job_type` is
`contractType`. UTF-8 with a BOM supports opening the CSV in spreadsheet tools.

Duplicates are removed globally across countries, keywords, and pages using API
IDs or canonical URLs. URL fragments and known tracking parameters are removed
for comparison; meaningful query parameters are retained. A content signature
is used only when neither an ID nor a URL exists. The duplicate count measures
repeated eligible listing occurrences actually processed, not distinct duplicate
groups. Exclusions are counted separately; API `returned` counts include both.

The `original_job_url` column retains the available API URL. okemprego deliberately
provides its own canonical listing URLs, not upstream employer application URLs.
Preserve those links as source attribution when presenting listings.

## Request limits, usage, and failures

See the [official API documentation](https://www.okemprego.com/pt/api) for current
coverage, usage conditions, pagination, and quotas. It documents 20 requests per
10 seconds per IP, a maximum page size of 50, and a maximum page number of 200.
The collector uses 50 results per page to reduce requests, sequential requests
three seconds apart (configurable, minimum two), a 200-page total budget,
30-second timeouts, and at most three attempts per request. `Retry-After` is
honored on retries; waits over 120 seconds stop the run. After exhausted retries
or an API error the run stops globally to avoid repeatedly hitting a failing
service. It never fetches individual listing detail pages.

Metadata may be used for search, indexing, and recommendations under the API's
published conditions; descriptions and trademarks can retain third-party rights.
When displaying a listing, cite its canonical okemprego URL. For future full-index
syncs, the provider recommends its cached bulk dumps instead of search pagination.
Avoid repeatedly running identical searches just to refresh unchanged data.

If an error occurs before any jobs are collected, the existing CSV is preserved.
If an error occurs later, partial results are saved with a warning and nonzero
exit status. A successful empty run writes a header-only CSV. A page budget or
listing limit can also produce incomplete coverage; inspect `stop_reason` and
individual search statuses. CSV replacement uses a temporary file to avoid
leaving a half-written CSV. The report describes the latest attempt, even when
an older CSV is preserved after failure.

## Offline checks

```sh
python3 -m unittest discover -s tests -v
```

These checks use mocked responses and make no API requests.


## Separate Arbeitnow investigation

Run `python3 explore_arbeitnow.py` to inspect one API page and write only
`data/arbeitnow_analysis.json`. The first observed page contains 300 jobs.
No dependencies are required. The exploration does not change `jobs.csv` or
integrate Arbeitnow into the existing collector.

The report describes fields, pagination, heuristic early-career relevance,
business-topic matches, examples, and country evidence. Countries are inferred
from location text using explicit names or limited city clues; unknown locations
remain unknown. Zero matches in this recent sample do not establish absence
from the full API. Topic matches alone do not establish early-career suitability.

At most two pages can be sampled with `python3 explore_arbeitnow.py --pages 2`,
with a minimum five-second delay and no automatic retries. A saved single-page
API response can be reanalyzed without requests:
`python3 explore_arbeitnow.py --input /path/to/saved_response.json`.
The initial report was produced from one downloaded response, reused locally.

The [API terms, section 11](https://www.arbeitnow.com/terms) require a link back
to Arbeitnow.com on your platform and state that availability is not guaranteed
and API permission may be revoked. The response metadata asks consumers not to
abuse the service and says jobs update hourly. The observed response supplied
rate-limit headers (limit 50, remaining 49), without a reset window; the script
does not assume a per-minute quota. No additional pages were requested during
the initial investigation.


## Collect and combine both sources

The original `collect_jobs.py`, `data/jobs.csv`, and exploration remain unchanged.
The separate Arbeitnow collector and offline merger run with Python 3.9+ and no
extra packages:

```sh
python3 collect_arbeitnow.py
python3 combine_jobs.py
```

The first command fetches **one page by default**, uses the previous Arbeitnow
analysis criteria, and writes `data/jobs_arbeitnow.csv` plus
`data/jobs_arbeitnow.report.json`. To inspect more listings explicitly, use
`python3 collect_arbeitnow.py --pages 2` (maximum five pages). Requests are
sequential and at least five seconds apart, with no automatic retries. A 429 or
other error stops collection and preserves the previous Arbeitnow CSV; the
report records the failed attempt. Successful collection replaces that source
CSV. Empty successful responses produce a header-only CSV. A zero remaining
quota stops pagination. No hourly quota window is assumed from rate-limit headers.

A previously downloaded response can be reused without network access:
`python3 collect_arbeitnow.py --input /path/to/saved_response.json`.
The first combined dataset reuses the genuine 300-listing response downloaded
for the exploration, rather than making another identical request. Its report
records the input mode and response hash. Analysis examples alone are never
used to reconstruct listings. A future live collection may return different jobs.

`combine_jobs.py` reads both source CSVs offline and writes:

- `data/jobs_combined.csv`: the normalized, filtered, deduplicated dataset.
- `data/jobs_combined.report.json`: input hashes, input/eligible/excluded/retained
  counts per source, retained source-by-country counts, total country counts,
  duplicate counts and provenance, attribution, and filtering limitations.

Neither command writes to `data/jobs.csv`. The merge does not refresh okemprego,
so it combines snapshots collected at different times. Run the existing
okemprego collector separately only when you intentionally want to refresh that
original dataset.

### Filtering the combined dataset

Arbeitnow uses exactly the exploration rule: internship/graduate/trainee signals
in title or job types qualify in any discipline; junior/entry-level/working-student
signals require a business topic in title or source tags. Senior titles are
excluded. Mere mentions in descriptions do not qualify. Working-student business
roles remain included to match the previous analysis. Local-language signals
recognized by the exploration are retained.

The existing Portuguese CSV is **filtered again only for the combined output**:
the same target-audience rule is applied, also recognizing Portuguese internship
titles and the API's supplied experience level. Consequently, many junior
engineering roles included by the broader original collector are excluded from
the combined dataset. The original 500-row CSV remains intact. This is a
transparent relevance heuristic, not manual verification or a guarantee that
every advertised role accepts recent graduates. Language variants and ambiguous
metadata can cause missed matches or false positives.

### Normalization and missing information

Shared columns: title, company, location, country, description, required_skills,
experience_level, job_type, publication_date, original_job_url, data_source,
source_job_id, source_tags. The last two preserve available source identifiers
and topic tags for deduplication and reproducible filtering. Existing okemprego
CSV rows have no retained API IDs, so their source_job_id is blank.

Descriptions are plain text. API publication timestamps are converted to ISO
8601 (UTC when timezone information is available); missing/invalid timestamps
are blank. Arbeitnow job_types are preserved as semicolon-separated source
labels; they may include contract and seniority labels. Tags stay in source_tags
and are **not** converted into required skills. Country, required skills, and
experience level stay blank for Arbeitnow because its observed API has no
structured fields supplying those facts. Country counts use `unknown` for blank
countries. Location-based country estimates appear in a separate report section;
they do not populate the CSV or imply remote-work eligibility.

### Duplicate matching and attribution

The merger matches canonical URLs (removing fragments and known tracking
parameters while preserving meaningful query values), source-scoped identifiers,
or exact title/company/location plus an identical substantial description.
It handles identities that link previously separate groups. It does not use
fuzzy title/company matching. Different source URLs and rewritten descriptions
can still conceal duplicates. A matching group retains the first record
(okemprego first); the report preserves every matched source URL and identifier.
Retained source counts refer to those retained records, so totals add up.

Keep original source URLs when presenting listings. The
[okemprego API conditions](https://www.okemprego.com/pt/api) require citing the
canonical job page; [Arbeitnow API terms, section 11](https://www.arbeitnow.com/terms)
require a link back to Arbeitnow.com on your platform. Provider-hosted URLs are
the available listing URLs, not guaranteed employer application URLs. Source
content retains applicable rights, data is provided as-is, and API permission
or availability can change. No website, publishing, or Supabase connection is
part of this workflow.

Run all normalization, eligibility, pagination, error-handling, and deduplication
checks offline with `python3 -m unittest discover -s tests -v`.


## Career Crush website

The React + TypeScript + Vite website lives in `web/`, with Tailwind CSS and Lucide icons.
From the VS Code terminal:

```sh
cd web
npm install
python3 scripts/prepare_data.py
npm run dev
```

Open the local URL printed by Vite. `npm run build` refreshes the JSON snapshot
from `data/jobs_combined.csv`, checks TypeScript, and creates `web/dist/`.
The generated real-job JSON is also committed so the website can build independently.
Use Node.js 22.18+ (Node 24 recommended) for `npm test`.

The first version includes title/company/keyword search, country/source-category/
career-stage/work-style filters, sorting, expandable details, original listing
links, load-more cards, and a Saved Jobs page with localStorage bookmarks. All
207 listings are available; cards appear 12 at a time. Bookmarks stay on the same
browser and origin, with no account or Supabase connection.

Country is never inferred for the website. The 41 Arbeitnow jobs display
“Country not provided”. Work-style filters use only explicit source type/tag labels, never description
guesses; unavailable work styles remain unspecified.
Career-stage pills are display classifications based on source titles/types.
Category options use available source tags; many Portuguese rows lack tags.
Both providers receive visible attribution and their original links are retained.

Run frontend checks with `npm test` and `npm run build` from `web/`.
