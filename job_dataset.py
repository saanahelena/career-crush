"""Shared schema, transparent eligibility rules, and conservative identity matching."""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import explore_arbeitnow as exploration

FIELDS = ['title', 'company', 'location', 'country', 'description', 'required_skills',
          'experience_level', 'job_type', 'publication_date', 'original_job_url',
          'data_source', 'source_job_id', 'source_tags']
ROOT = Path(__file__).resolve().parent
RULE = ('Internship/graduate/trainee title or job-type signal, or junior/entry-level/'
        'working-student signal plus business topic in title/tags. Senior titles excluded. '
        'Descriptions alone never establish eligibility. okemprego additionally uses '
        'its explicit experience level and Portuguese internship title terms.')
ATTRIBUTION = {
    'okemprego': {'site': 'https://www.okemprego.com',
                 'terms': 'https://www.okemprego.com/pt/api',
                 'requirement': 'Cite the canonical okemprego job URL when displaying a listing.'},
    'arbeitnow': {'site': 'https://www.arbeitnow.com',
                 'terms': 'https://www.arbeitnow.com/terms',
                 'requirement': 'Link back to Arbeitnow.com on your platform (API terms section 11).'},
}


def clean(value):
    return str(value).strip() if value is not None else ''


def publication(value, epoch=False):
    if value is None or value == '':
        return ''
    try:
        if epoch:
            if isinstance(value, bool):
                return ''
            date = datetime.fromtimestamp(float(value), timezone.utc)
        else:
            date = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            # Do not invent a timezone when the source does not give one.
            if date.tzinfo is None:
                return date.isoformat()
        return date.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, TypeError, OverflowError, OSError):
        return ''


def eligibility(title, job_type='', tags=(), experience='', portuguese=False):
    if not clean(title):
        return False, 'missing_title'
    if re.search(r'\b(?:senior|s[eé]nior|sr|principal|director|head|lead)\b', title, re.I):
        return False, 'senior_title'
    early = exploration.matches(exploration.PATTERNS, title + ' ' + job_type + ' ' + experience)
    if portuguese and re.search(r'\b(?:est[aá]gios?|estagi[aá]ri[oa]s?)\b', title + ' ' + job_type, re.I):
        early.append('internships')
    topics = exploration.matches(exploration.TOPICS, title + ' ' + ' '.join(tags))
    if set(early) & {'internships', 'graduate_programs', 'trainee_positions'}:
        return True, 'internship_graduate_or_trainee'
    if set(early) & {'junior', 'working_students'} and topics:
        return True, 'junior_or_student_business'
    return False, 'no_target_early_career_evidence'


def normalize_arbeitnow(job):
    row = dict.fromkeys(FIELDS, '')
    row.update(title=exploration.text(job.get('title')),
               company=clean(job.get('company_name')), location=clean(job.get('location')),
               description=exploration.text(job.get('description')),
               job_type='; '.join(clean(v) for v in job.get('job_types', []) or []),
               publication_date=publication(job.get('created_at'), epoch=True),
               original_job_url=clean(job.get('url')), data_source='arbeitnow',
               source_job_id=clean(job.get('slug')),
               source_tags='; '.join(exploration.text(v) for v in (job.get('tags') or [])))
    # The observed API supplies no country, required skills or experience level.
    # Do not turn city guesses, tags, or inferred eligibility into source facts.
    return row


def normalize_okemprego(row):
    normalized = {field: clean(row.get(field)) for field in FIELDS}
    normalized['data_source'] = 'okemprego'
    normalized['publication_date'] = publication(row.get('publication_date'))
    return normalized


def canonical_url(url):
    parts = urlsplit(url)
    if parts.scheme.lower() not in {'http', 'https'} or not parts.netloc:
        return ''
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith('utm_') and k.lower() not in
                   {'fbclid', 'gclid', 'msclkid'})
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path.rstrip('/'), urlencode(query), ''))


def identities(row):
    keys = set()
    url = canonical_url(row['original_job_url'])
    if url:
        keys.add(('url', url))
    if row['source_job_id']:
        keys.add(('source_id', row['data_source'], row['source_job_id']))
    # Exact substantial content is corroboration, not fuzzy title matching.
    if all(row[k] for k in ('title', 'company', 'location')) and len(row['description']) >= 100:
        keys.add(('exact_content', *(row[k].casefold() for k in
                  ('title', 'company', 'location', 'description'))))
    return keys


def deduplicate(rows):
    # Union all matching identities, including a later row bridging two groups.
    parents = list(range(len(rows)))
    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index
    seen = {}
    for index, row in enumerate(rows):
        for key in identities(row):
            if key in seen:
                left, right = root(index), root(seen[key])
                parents[max(left, right)] = min(left, right)
            else:
                seen[key] = index
    groups = {}
    for index in range(len(rows)):
        groups.setdefault(root(index), []).append(index)
    # Keep first record intact. Record every provenance URL separately in report.
    kept = [rows[indexes[0]] for indexes in groups.values()]
    duplicates = [{'retained_url': rows[indexes[0]]['original_job_url'],
                   'members': [{'source': rows[i]['data_source'],
                                'source_job_id': rows[i]['source_job_id'],
                                'url': rows[i]['original_job_url']} for i in indexes]}
                  for indexes in groups.values() if len(indexes) > 1]
    return kept, duplicates


def read_csv(path, required):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not set(required).issubset(reader.fieldnames or []):
            raise ValueError(f'{path}: missing required columns')
        rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError(f'{path}: malformed CSV row')
        return rows


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.csv.tmp')
    with temporary.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_json(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)
