#!/usr/bin/env python3
"""Filter and merge existing source CSVs offline; preserve both inputs."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import sys

import explore_arbeitnow as exploration
from job_dataset import (ROOT, FIELDS, RULE, ATTRIBUTION, read_csv, write_csv,
                         write_json, eligibility, normalize_okemprego, deduplicate)


def combine(okemprego, arbeitnow):
    accepted, source_stats = [], {}
    for source, input_rows in (('okemprego', okemprego), ('arbeitnow', arbeitnow)):
        reasons = Counter()
        count = 0
        for original in input_rows:
            row = normalize_okemprego(original) if source == 'okemprego' else {
                field: original.get(field, '') for field in FIELDS}
            if row['data_source'] != source:
                raise ValueError(f'Unexpected data_source in {source} input')
            relevant, reason = eligibility(row['title'], row['job_type'],
                row['source_tags'].split('; '), row['experience_level'], source == 'okemprego')
            if relevant:
                accepted.append(row)
                count += 1
            else:
                reasons[reason] += 1
        source_stats[source] = {'input_rows': len(input_rows), 'eligible': count,
                                'excluded': len(input_rows) - count,
                                'exclusion_reasons': dict(reasons)}
    unique, groups = deduplicate(accepted)
    for source, stats in source_stats.items():
        kept = [row for row in unique if row['data_source'] == source]
        stats['retained_rows'] = len(kept)
        stats['duplicates_removed'] = stats['eligible'] - len(kept)
        stats['by_country'] = dict(Counter(row['country'] or 'unknown' for row in kept))
    inferred = Counter()
    for row in unique:
        if not row['country']:
            codes, _ = exploration.infer_country(row['location'])
            inferred.update(codes or ['unknown'])
    report = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'collected_by_source': source_stats, 'total_unique': len(unique),
              'by_country': dict(Counter(row['country'] or 'unknown' for row in unique)),
              'location_inferences_for_rows_without_country_not_source_facts': dict(inferred),
              'duplicates_removed': len(accepted) - len(unique), 'duplicate_groups': groups,
              'filtering_rule': RULE, 'attribution': ATTRIBUTION,
              'limitations': ['Heuristic relevance is not a guarantee of eligibility; review before applying.',
                  'Arbeitnow countries, skills and experience levels are blank when unavailable.',
                  'Source-hosted URLs are retained; upstream employer URLs are unavailable.',
                  'Different URLs and rewritten descriptions can hide cross-source duplicates. No fuzzy title/company merging.',
                  'First matching record wins (okemprego first); all duplicate provenance URLs are recorded in duplicate_groups.',
                  'Source snapshots have different collection times; no new okemprego requests are made.']}
    return unique, report


def main():
    try:
        paths = {'okemprego': ROOT / 'data/jobs.csv', 'arbeitnow': ROOT / 'data/jobs_arbeitnow.csv'}
        original_fields = FIELDS[:10]
        inputs = {source: read_csv(path, original_fields if source == 'okemprego' else FIELDS)
                  for source, path in paths.items()}
        rows, report = combine(inputs['okemprego'], inputs['arbeitnow'])
        report['input_sha256'] = {source: hashlib.sha256(path.read_bytes()).hexdigest()
                                  for source, path in paths.items()}
        write_csv(ROOT / 'data/jobs_combined.csv', rows)
        write_json(ROOT / 'data/jobs_combined.report.json', report)
    except (OSError, ValueError) as exc:
        print(f'Cannot combine datasets: {exc}', file=sys.stderr)
        return 1
    print(f"Saved {len(rows)} unique listings to data/jobs_combined.csv")
    print('By source:', {source: stats['retained_rows'] for source, stats in report['collected_by_source'].items()})
    print('By country (API-provided):', report['by_country'])
    print('Duplicates removed:', report['duplicates_removed'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
