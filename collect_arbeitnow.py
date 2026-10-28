#!/usr/bin/env python3
"""Collect a bounded Arbeitnow sample using the exploration's eligibility rules."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import explore_arbeitnow as exploration
from job_dataset import (ROOT, ATTRIBUTION, RULE, eligibility, normalize_arbeitnow,
                         deduplicate, write_csv, write_json)


def collect(pages=1, delay=5, saved=None):
    rows, rejected = [], Counter()
    report = {'collected_at': datetime.now(timezone.utc).isoformat(),
              'source': exploration.ENDPOINT, 'rule': RULE, 'attribution': ATTRIBUTION['arbeitnow'],
              'mode': 'saved_response' if saved else 'live_api', 'pages': [],
              'returned': 0, 'error': None, 'stop_reason': 'page_budget',
              'country_policy': 'Country remains blank: API has no structured country field.'}
    current, fingerprints = 1, set()
    try:
        for index in range(1 if saved else pages):
            if index:
                time.sleep(delay)
            if saved:
                payload = json.loads(Path(saved).read_text(encoding='utf-8'))
                headers = {}
                report['saved_response_sha256'] = hashlib.sha256(Path(saved).read_bytes()).hexdigest()
            else:
                payload, headers = exploration.retrieve(current)
            if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                raise ValueError('Expected a data array')
            jobs = payload['data']
            fingerprint = hashlib.sha256(json.dumps(jobs, sort_keys=True).encode()).hexdigest()
            if jobs and fingerprint in fingerprints:
                raise ValueError('Repeated API page')
            fingerprints.add(fingerprint)
            report['pages'].append({'page': current, 'returned': len(jobs),
                                    'rate_limit_headers': headers,
                                    'meta': payload.get('meta'), 'links': payload.get('links')})
            report['returned'] += len(jobs)
            for job in jobs:
                if not isinstance(job, dict):
                    rejected['malformed_job'] += 1
                    continue
                row = normalize_arbeitnow(job)
                tags = [exploration.text(v) for v in (job.get('tags') or [])]
                relevant, reason = eligibility(row['title'], row['job_type'], tags)
                if relevant:
                    rows.append(row)
                else:
                    rejected[reason] += 1
            following = (payload.get('links') or {}).get('next')
            if not jobs or not following:
                report['stop_reason'] = 'exhausted'
                break
            if saved:
                report['stop_reason'] = 'saved_single_page'
                break
            if index + 1 >= pages:
                break
            if str(headers.get('x-ratelimit-remaining')) == '0':
                report['stop_reason'] = 'rate_limit_remaining_zero'
                break
            parts = urlsplit(following)
            if (parts.scheme, parts.netloc, parts.path) != ('https', 'www.arbeitnow.com', '/api/job-board-api'):
                raise ValueError('Unexpected next-page URL')
            next_number = int(parse_qs(parts.query)['page'][0])
            if next_number <= current:
                raise ValueError('Pagination did not advance')
            current = next_number
    except (HTTPError, URLError, OSError, ValueError, TypeError, KeyError) as exc:
        report['error'] = str(exc)
        report['stop_reason'] = 'error'
        if isinstance(exc, HTTPError):
            report['retry_after'] = exc.headers.get('Retry-After')
        # No retries, especially after 429: avoid additional load.
    unique, duplicates = deduplicate(rows)
    report.update(eligible_before_dedup=len(rows), collected=len(unique),
                  duplicates_removed=len(rows) - len(unique), exclusions=dict(rejected),
                  by_country=dict(Counter(row['country'] or 'unknown' for row in unique)),
                  status='failed' if report['error'] else 'success')
    return unique, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages', type=int, default=1, choices=range(1, 6), metavar='1-5')
    parser.add_argument('--delay', type=float, default=5)
    parser.add_argument('--input', type=Path, help='Reuse a saved single-page API response offline')
    args = parser.parse_args()
    if not math.isfinite(args.delay) or args.delay < 5:
        parser.error('--delay must be at least five seconds')
    rows, report = collect(args.pages, args.delay, args.input)
    try:
        write_json(ROOT / 'data/jobs_arbeitnow.report.json', report)
        if report['error']:
            print('Collection failed; existing Arbeitnow CSV preserved. ' + report['error'], file=sys.stderr)
            return 1
        write_csv(ROOT / 'data/jobs_arbeitnow.csv', rows)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Saved {len(rows)} Arbeitnow listings from {report['returned']} returned jobs.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
