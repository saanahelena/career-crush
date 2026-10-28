#!/usr/bin/env python3
"""Collect up to 500 early-career opportunities across Europe from okemprego."""

import argparse
import csv
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
import math
import re
from collections import Counter, deque
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ENDPOINT = "https://www.okemprego.com/api/v1/jobs"
COUNTRIES = ("FI", "PT", "DE", "NL", "SE", "DK", "BE", "FR")
KEYWORDS = ("internship", "intern", "trainee", "graduate", "junior", "strategy",
            "consulting", "sustainability", "business analyst", "business development")
PRIORITY_TERMS = ("consult", "strategy", "strategic", "international business",
                  "sustainab", "esg", "business development", "finance", "financial",
                  "marketing", "business analyst")
EARLY_CAREER = re.compile(r"\b(intern(?:ship)?s?|trainees?(?:hip)?s?|graduates?|junior|entry[ -]level|est[aá]gi[oa](?:s|ri[oa]s?)?)\b", re.I)
SENIOR_TITLE = re.compile(r"\b(senior|s[eé]nior|sr\.?|principal|director|head|lead)\b", re.I)
FIELDS = ["title", "company", "location", "country", "description",
          "required_skills", "experience_level", "job_type",
          "publication_date", "original_job_url"]


class CollectionError(Exception):
    pass


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "br", "li", "div"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"p", "li", "div"}:
            self.parts.append(" ")


def value(item):
    """Represent absent values as empty strings, without inventing data."""
    if item is None:
        return ""
    if isinstance(item, dict):
        return value(item.get("name"))
    return str(item).strip()


def normalize(job):
    location = job.get("location")
    if isinstance(location, dict):
        places = [value(location.get(key)) for key in
                  ("municipality", "district", "region")]
        location = ", ".join(dict.fromkeys(p for p in places if p))
    location = value(location) or value(job.get("city")) or value(job.get("region"))
    parser = PlainText()
    parser.feed(value(job.get("description")))
    skills = job.get("skills") or []
    if isinstance(skills, list):
        skills = "; ".join(filter(None, (value(skill) for skill in skills)))
    return dict(zip(FIELDS, [
        value(job.get("title")), value(job.get("company")), location,
        value(job.get("country")), " ".join("".join(parser.parts).split()),
        value(skills), value(job.get("experienceLevel")),
        value(job.get("contractType")), value(job.get("postedAt")),
        value(job.get("originalUrl") or job.get("sourceUrl") or job.get("url")),
    ]))


def retry_delay(headers, attempt):
    raw = headers.get("Retry-After")
    if raw:
        try:
            seconds = float(raw)
        except ValueError:
            try:
                seconds = (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                seconds = 2 ** (attempt + 1)
        # Stop instead of retrying earlier than a long server-requested wait.
        if seconds > 120:
            raise CollectionError(f"Server requests a {seconds:.0f}s wait; try again later.")
        return max(1, seconds)
    return 2 ** (attempt + 1)


def fetch(url, delay):
    for attempt in range(3):
        try:
            request = Request(url, headers={"Accept": "application/json",
                                           "User-Agent": "CareerCrush-UniversityProject/1.0"})
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise CollectionError("Unexpected API response: expected an object with a data array.")
            return payload
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise CollectionError(f"API returned HTTP {exc.code}: {exc.reason}") from exc
            wait = max(delay, retry_delay(exc.headers, attempt))
            print(f"HTTP {exc.code}; retrying in {wait:g}s.", file=sys.stderr)
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 2:
                raise CollectionError(f"Cannot reach API: {exc}") from exc
            wait = max(delay, 2 ** (attempt + 1))
            print(f"Network error; retrying in {wait:g}s.", file=sys.stderr)
        except (ValueError, UnicodeError) as exc:
            raise CollectionError("API returned invalid JSON.") from exc
        time.sleep(wait)


def page_url(page, country="PT", keyword="internship"):
    return ENDPOINT + "?" + urlencode({"country": country, "q": keyword, "page": page, "perPage": 50})


def next_page(payload, current_page):
    links = payload.get("links") or {}
    if "next" in links:
        if not links["next"]:
            return None
        # Use only the next page number, preserving our endpoint and filters.
        parsed = urlsplit(links["next"])
        params = dict(parse_qsl(parsed.query))
        try:
            page = int(params["page"])
        except (KeyError, ValueError):
            raise CollectionError("Unrecognized next-page link; stopping safely.")
        if page <= current_page or page > 200:
            raise CollectionError("API pagination did not advance or exceeded page 200.")
        return page
    pagination = payload.get("pagination") or {}
    if current_page < int(pagination.get("totalPages") or current_page):
        if current_page >= 200:
            raise CollectionError("API page limit reached; use a bulk dump for a full sync.")
        return current_page + 1
    return None


def canonical_url(url):
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in
             {"fbclid", "gclid", "msclkid"}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path.rstrip("/"), urlencode(sorted(query)), ""))


def identity_keys(job, row):
    keys = set()
    if job.get("id"):
        keys.add(("id", str(job["id"])))
    for field in ("url", "originalUrl", "sourceUrl"):
        if job.get(field):
            keys.add(("url", canonical_url(value(job[field]))))
    # Only use content when the API supplies neither an ID nor a URL.
    if not keys:
        keys.add(("content", *(row[k].casefold() for k in
                  ("title", "company", "country", "location", "description"))))
    return keys


def early_career(row):
    if SENIOR_TITLE.search(row["title"]):
        return False
    return bool(EARLY_CAREER.search(row["title"] + " " + row["job_type"]) or
                row["experience_level"].lower() in
                {"junior", "entry", "entry-level", "entry_level", "graduate", "internship", "intern", "trainee"})


def priority_score(row):
    text = " ".join(row[k] for k in
                    ("title", "description", "required_skills")).casefold()
    return sum(term in text for term in PRIORITY_TERMS)


def collect(limit, delay, countries=COUNTRIES, keywords=KEYWORDS, max_pages=200):
    rows, seen = [], set()
    searches = [{"country": country, "keyword": keyword, "pages": 0,
                 "returned": 0, "duplicates": 0, "excluded": 0,
                 "status": "not_searched"}
                for keyword in keywords for country in countries]
    # Visit every country/keyword before fetching deeper pages of a search.
    queue = deque((index, 1) for index in range(len(searches)))
    fingerprints = {index: set() for index in range(len(searches))}
    report = {"started_at": datetime.now(timezone.utc).isoformat(),
              "duplicates_removed": 0, "excluded": 0, "pages_requested": 0,
              "searches": searches, "errors": [], "stop_reason": "exhausted"}
    try:
        index_payload = fetch("https://www.okemprego.com/api/v1/countries", delay)
        available = {value(item.get("code")).upper() for item in index_payload["data"]
                     if isinstance(item, dict) and item.get("code")}
        if not available:
            raise CollectionError("Country index contained no country codes")
        report["available_countries"] = sorted(available)
        for search in searches:
            if search["country"] not in available:
                search["status"] = "country_unavailable"
        queue = deque((index, page) for index, page in queue
                      if searches[index]["status"] != "country_unavailable")
        time.sleep(delay)
    except CollectionError as exc:
        report["errors"].append(f"Country availability check: {exc}")
        report["stop_reason"] = "error"
        queue.clear()
    while queue and len(rows) < limit and report["pages_requested"] < max_pages:
        index, page = queue.popleft()
        search = searches[index]
        if report["pages_requested"]:
            time.sleep(delay)
        try:
            report["pages_requested"] += 1
            payload = fetch(page_url(page, search["country"], search["keyword"]), delay)
            search["pages"] += 1
            jobs = payload["data"]
            search["returned"] += len(jobs)
            fingerprint = json.dumps(jobs, sort_keys=True)
            if jobs and fingerprint in fingerprints[index]:
                raise CollectionError("Repeated page detected")
            fingerprints[index].add(fingerprint)
            candidates = []
            for job in jobs:
                if not isinstance(job, dict):
                    search["excluded"] += 1
                    continue
                row = normalize(job)
                # Never label results with the requested country if the API omits it.
                if row["country"].upper() != search["country"] or not early_career(row):
                    search["excluded"] += 1
                    continue
                row["country"] = row["country"].upper()
                candidates.append((job, row))
            candidates.sort(key=lambda item: priority_score(item[1]), reverse=True)
            processed = 0
            for job, row in candidates:
                keys = identity_keys(job, row)
                duplicate = bool(keys & seen)
                seen.update(keys)
                processed += 1
                if duplicate:
                    search["duplicates"] += 1
                    report["duplicates_removed"] += 1
                else:
                    rows.append(row)
                if len(rows) >= limit:
                    break
            following = next_page(payload, page) if jobs else None
            search["status"] = ("limit_reached" if processed < len(candidates) else
                                "pending" if following else
                                "no_results" if search["returned"] == 0 else "complete")
            if following:
                queue.append((index, following))
            print(f'{search["country"]} / {search["keyword"]} / page {page}: '
                  f'{len(jobs)} returned; {len(rows)} unique collected.', flush=True)
        except (CollectionError, ValueError, TypeError) as exc:
            search["status"] = "error"
            report["errors"].append(f'{search["country"]}/{search["keyword"]}: {exc}')
            report["stop_reason"] = "error"
            # Avoid multiplying requests after a rate-limit or service failure.
            break
    if not report["errors"]:
        if len(rows) >= limit:
            report["stop_reason"] = "limit_reached"
        elif queue:
            report["stop_reason"] = "page_budget_reached"
    rows.sort(key=priority_score, reverse=True)
    counts = Counter(row["country"] for row in rows)
    report["by_country"] = {country: counts[country] for country in countries}
    report["collected"] = len(rows)
    report["excluded"] = sum(search["excluded"] for search in searches)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return rows, report


def print_report(report):
    print("Unique jobs collected by country:")
    for country, count in report["by_country"].items():
        print(f"  {country}: {count}")
    print(f'Duplicate occurrences removed: {report["duplicates_removed"]}')
    print(f'Excluded (country mismatch/missing or no early-career evidence): {report["excluded"]}')
    unavailable = {search["country"] for search in report["searches"]
                   if search["status"] == "country_unavailable"}
    for country in report["by_country"]:
        if country in unavailable:
            print(f"Country unavailable in API: {country}; keyword searches skipped.")
    for search in report["searches"]:
        if search["status"] == "country_unavailable":
            continue
        if search["status"] == "no_results":
            print(f'No results: {search["country"]} / {search["keyword"]}')
        elif search["status"] not in {"complete"}:
            print(f'{search["status"]}: {search["country"]} / {search["keyword"]}')
    print(f'Stop reason: {report["stop_reason"]}')
    for error in report["errors"]:
        print(error, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=500, choices=range(1, 501), metavar="1-500")
    parser.add_argument("--delay", type=float, default=3, help="Seconds between requests (minimum 2)")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "data/jobs.csv")
    parser.add_argument("--countries", nargs="+", choices=COUNTRIES, default=list(COUNTRIES))
    parser.add_argument("--keywords", nargs="+", choices=KEYWORDS, default=list(KEYWORDS))
    parser.add_argument("--max-pages", type=int, default=200, help="Total page request budget")
    args = parser.parse_args()
    if not math.isfinite(args.delay) or not args.delay >= 2:
        parser.error("--delay must be at least 2 seconds")
    if args.max_pages < 1:
        parser.error("--max-pages must be positive")
    rows, report = collect(args.limit, args.delay, tuple(dict.fromkeys(args.countries)),
                           tuple(dict.fromkeys(args.keywords)), args.max_pages)
    print_report(report)
    error = bool(report["errors"])
    # Persist the report even on an error, without overwriting a working CSV.
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report_path = args.output.with_suffix(".report.json")
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Cannot write collection report: {exc}", file=sys.stderr)
        return 1
    if error and not rows:
        print("No CSV written; any existing file was preserved.", file=sys.stderr)
        return 1
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(args.output)
    except OSError as exc:
        print(f"Cannot write CSV: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {len(rows)} unique listings to {args.output}" + (" (partial results)." if error else "."))
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main())
