#!/usr/bin/env python3
"""Inspect one Arbeitnow page (300 listings observed), without touching jobs.csv."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

ENDPOINT = 'https://www.arbeitnow.com/api/job-board-api'
TARGETS = ('FI', 'SE', 'DK', 'DE', 'NL', 'BE', 'FR')
PATTERNS = {
    'internships': r'\b(?:intern(?:ship)?s?|praktik\w*|pflichtpraktikum|jahrespraktikum|stage|afstudeerstage|stagiair\w*)\b',
    'graduate_programs': r'\b(?:graduate(?:s| program(?:me)?s?| scheme)?|absolvent\w*)\b',
    'trainee_positions': r'\btrainee\w*\b',
    'junior': r'\b(?:junior|entry[ -]level|entry|berufseinstieg)\b',
    'working_students': r'\b(?:werkstudent\w*|working student|student college)\b',
}
TOPICS = {
    'consulting': r'\b(?:consult\w*|beratung|berater\w*)\b',
    'strategy': r'\bstrateg\w*\b',
    'sustainability': r'\b(?:sustainab\w*|esg|nachhaltig\w*|durab\w*|duurzaam\w*)\b',
    'finance': r'\b(?:financ\w*|finanz\w*|accounting|controller|controlling|reconciliation\w*)\b',
    'business_development': r'\bbusiness development\b|\bgeschäftsentwicklung\b',
    'international_business': r'\binternational(?:e[rsnm]?)? business\b',
    'other_business': r'\b(?:business analyst|marketing|sales|account executive|hr|human resources|operations|eventmanagement|event management|founders? associate|marketplace)\b',
}
SENIOR = re.compile(r'\b(?:senior|sr|principal|director|head|lead)\b', re.I)
COUNTRY_NAMES = {
    'FI': ('finland', 'suomi'), 'SE': ('sweden', 'sverige'),
    'DK': ('denmark', 'danmark'), 'DE': ('germany', 'deutschland'),
    'NL': ('netherlands', 'nederland', 'nederlands'),
    'BE': ('belgium', 'belgique', 'belgië'), 'FR': ('france', 'frankrijk'),
    'CH': ('switzerland', 'schweiz', 'suisse'), 'AT': ('austria', 'österreich'),
    'GB': ('united kingdom', 'england', 'scotland', 'northern ireland'),
    'PT': ('portugal',), 'ES': ('spain', 'españa'), 'IT': ('italy', 'italia'),
    'IE': ('ireland',), 'NO': ('norway', 'norge'), 'PL': ('poland', 'polska'),
}
# Deliberately limited city clues; ambiguous/unrecognized locations remain unknown.
CITY_CLUES = {
    'FI': ('helsinki', 'espoo', 'tampere', 'turku'),
    'SE': ('stockholm', 'gothenburg', 'göteborg', 'malmö'),
    'DK': ('copenhagen', 'københavn', 'aarhus'),
    'BE': ('brussels', 'bruxelles', 'antwerp', 'antwerpen', 'gent'),
    'DE': ('berlin', 'munich', 'münchen', 'hamburg', 'frankfurt', 'cologne',
           'köln', 'düsseldorf', 'stuttgart', 'kassel', 'wiesbaden', 'dresden',
           'nuremberg', 'hanover', 'erfurt', 'essen', 'pforzheim', 'ludwigsburg'),
    'NL': ('amsterdam', 'utrecht', 'rotterdam', 'delft', 'eindhoven', 'haarlem',
           'the hague', 'ridderkerk'),
    'FR': ('paris', 'lyon', 'bordeaux', 'nantes', 'rennes', 'orly', 'clichy',
           'sucé-sur-erdre', 'toulouse'),
    'CH': ('zurich', 'zürich', 'bern', 'geneva', 'lausanne', 'winterthur',
           'st. gallen', 'neuchâtel', 'zug', 'zofingen', 'frauenfeld', 'crissier',
           'wallisellen', 'leibstadt', 'blonay'),
    'GB': ('london', 'birmingham', 'manchester', 'edinburgh', 'belfast',
           'bristol', 'studley', 'darlington', 'durham', 'ashington', 'morpeth', 'hexham'),
}


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def text(value):
    parser = TextParser()
    parser.feed(unescape(str(value or '')))
    return ' '.join(' '.join(parser.parts).split())


def matches(patterns, value):
    return [name for name, pattern in patterns.items() if re.search(pattern, value, re.I)]


def mentions(location, clues):
    return any(re.search(r'(?<!\w)' + re.escape(clue) + r'(?!\w)', location, re.I)
               for clue in clues)


def infer_country(location):
    explicit = [code for code, names in COUNTRY_NAMES.items() if mentions(location, names)]
    if explicit:
        return explicit, 'country_name_in_location'
    cities = [code for code, names in CITY_CLUES.items() if mentions(location, names)]
    return cities, 'city_clue_in_location' if cities else 'unknown'


def retrieve(page):
    # No automatic retries: a 429 or outage ends this small investigation.
    request = Request(f'{ENDPOINT}?page={page}', headers={
        'Accept': 'application/json', 'User-Agent': 'CareerCrush-SourceExploration/1.0'})
    with urlopen(request, timeout=30) as response:
        headers = {k.lower(): v for k, v in response.headers.items()
                   if k.lower() in {'x-ratelimit-limit', 'x-ratelimit-remaining',
                                    'x-ratelimit-reset', 'retry-after', 'last-modified', 'date'}}
        return json.load(response), headers


def analyze(pages):
    seen, jobs, duplicates = set(), [], 0
    fields, types, missing = Counter(), defaultdict(set), Counter()
    pagination = []
    for payload in pages:
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
            raise ValueError('Expected a JSON object containing a data array')
        pagination.append({'links': payload.get('links'), 'meta': payload.get('meta')})
        for job in payload['data']:
            if not isinstance(job, dict):
                raise ValueError('Expected each job to be an object')
            identity = job.get('slug') or job.get('url') or json.dumps(job, sort_keys=True)
            if identity in seen:
                duplicates += 1
                continue
            seen.add(identity)
            jobs.append(job)
            for key, value in job.items():
                fields[key] += 1
                types[key].add(type(value).__name__)
                if value is None or value == '' or value == []:
                    missing[key] += 1
    early_counts, topic_counts, country_counts = Counter(), Counter(), Counter()
    evidence_counts, unknowns = Counter(), Counter()
    related_examples = {key: [] for key in TOPICS}
    junior_business_count = 0
    examples, strict_count, business_count, senior_count = [], 0, 0, 0
    for job in jobs:
        title = text(job.get('title'))
        tags = ' '.join(text(v) for v in (job.get('tags') or []))
        job_types = ' '.join(text(v) for v in (job.get('job_types') or []))
        early = matches(PATTERNS, title + ' ' + job_types)
        topics = matches(TOPICS, title + ' ' + tags)
        description_topics = matches(TOPICS, text(job.get('description')))
        senior = bool(SENIOR.search(title))
        # Internship/graduate/trainee roles in any discipline; junior/student
        # roles need a business-topic signal in title/tags.
        relevant = not senior and bool(set(early) & {
            'internships', 'graduate_programs', 'trainee_positions'} or
            (set(early) & {'junior', 'working_students'} and topics))
        junior_business_count += bool(not senior and 'junior' in early and topics)
        for topic in topics:
            if len(related_examples[topic]) < 2:
                related_examples[topic].append({'title': job.get('title'),
                    'company': job.get('company_name'), 'location': job.get('location'),
                    'url': job.get('url'), 'appears_early_career_relevant': relevant})
        early_counts.update(early)
        topic_counts.update(topics)
        if relevant:
            strict_count += 1
            business_count += bool(topics)
        senior_count += bool(senior and topics)
        location = str(job.get('location') or '')
        countries, evidence = infer_country(location)
        evidence_counts[evidence] += 1
        country_counts.update(countries)
        if not countries:
            unknowns[location or '(missing)'] += 1
        if relevant:
            examples.append({'title': job.get('title'), 'company': job.get('company_name'),
                             'location': location, 'url': job.get('url'),
                             'early_career_signals': early, 'business_topics': topics,
                             'description_topic_mentions': description_topics,
                             'inferred_countries': countries, 'country_evidence': evidence})
    return {
        'analyzed_at': datetime.now(timezone.utc).isoformat(), 'source': ENDPOINT,
        'sample': {'pages': len(pages), 'unique_listings': len(jobs),
                   'duplicates_removed': duplicates, 'exhaustive': False},
        'fields': {key: {'present': fields[key], 'missing_or_empty':
                        len(jobs) - fields[key] + missing[key], 'types': sorted(types[key])}
                   for key in sorted(fields)},
        'field_notes': {'description': 'HTML, sometimes HTML-escaped',
                        'created_at': 'Numeric Unix timestamp in the observed sample',
                        'slug': 'Available job identifier',
                        'tags': 'Topic labels, not guaranteed required skills',
                        'job_types': 'Mixed languages and seniority/contract labels; sometimes empty',
                        'remote': 'Boolean; does not specify permitted remote countries'},
        'pagination_observed': pagination,
        'relevance': {'appears_relevant': strict_count,
                      'relevant_with_business_topic_in_title_or_tags': business_count,
                      'junior_business_roles': junior_business_count,
                      'early_career_signal_counts_overlapping': {key: early_counts[key] for key in PATTERNS},
                      'topic_counts_in_title_or_tags_overlapping': {key: topic_counts[key] for key in TOPICS},
                      'senior_title_topic_matches_excluded': senior_count,
                      'rule': 'Internship/graduate/trainee title or job_type signal, or junior/working-student signal plus business topic in title/tags; senior titles excluded. Description mentions alone do not establish eligibility.'},
        'geography': {'structured_country_field_present': 'country' in fields,
                      'inferred_location_counts': dict(sorted(country_counts.items())),
                      'target_countries': {code: {'sample_location_matches': country_counts[code],
                          'status': 'observed_in_location' if country_counts[code] else 'not_observed_in_sample'}
                          for code in TARGETS},
                      'evidence_counts': dict(evidence_counts),
                      'unknown_country_count': sum(unknowns.values()),
                      'unknown_location_examples': dict(unknowns.most_common(12)),
                      'method': 'Location only: explicit country names first, then a limited city dictionary. Inferences are not API country fields. Remote does not establish eligibility in any country; counts may overlap for multi-country locations.'},
        'topic_examples_not_necessarily_early_career': related_examples,
        'relevant_examples': sorted(examples, key=lambda e: bool(e['business_topics']), reverse=True)[:15],
        'limitations': ['One or two recent pages are a time-ordered convenience sample, not a coverage estimate.',
                       'No structured required skills or experience level was observed unless shown in fields; tags are not necessarily skills.',
                       'Heuristics can miss local-language roles or misclassify ambiguous titles. Manual review is required.',
                       'No matching locations does not mean the API has no jobs in that country.',
                       'Descriptions may contain boilerplate about other locations; they are not used for country inference.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages', type=int, choices=(1, 2), default=1,
                        help='Small sample only: one page by default, at most two')
    parser.add_argument('--delay', type=float, default=5, help='Seconds between pages (minimum 5)')
    parser.add_argument('--input', type=Path, help='Analyze an already-downloaded single-page JSON response without network requests')
    args = parser.parse_args()
    if not math.isfinite(args.delay) or args.delay < 5:
        parser.error('--delay must be at least 5 seconds')
    pages, headers, error = [], [], None
    try:
        if args.input:
            pages.append(json.loads(args.input.read_text(encoding='utf-8')))
        else:
            current = 1
            for index in range(args.pages):
                if index:
                    time.sleep(args.delay)
                payload, observed_headers = retrieve(current)
                if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                    raise ValueError('Unexpected API response: missing data array')
                pages.append(payload)
                headers.append(observed_headers)
                following = (payload.get('links') or {}).get('next')
                if not payload['data'] or not following or index + 1 >= args.pages:
                    break
                url = urlsplit(following)
                if url.scheme != 'https' or url.netloc != 'www.arbeitnow.com' or url.path != '/api/job-board-api':
                    raise ValueError('Unexpected pagination URL; stopping')
                next_number = int(parse_qs(url.query)['page'][0])
                if next_number <= current:
                    raise ValueError('Pagination did not advance')
                current = next_number
    except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError) as exc:
        error = str(exc)
        if isinstance(exc, HTTPError) and exc.code == 429:
            error += '; rate limited, no retry made; Retry-After=' + str(exc.headers.get('Retry-After'))
    try:
        report = analyze(pages)
    except (ValueError, TypeError) as exc:
        report = {'source': ENDPOINT}
        error = str(exc)
    report.update({'status': 'partial_or_failed' if error else 'success', 'error': error,
                   'input_mode': 'local_saved_response' if args.input else 'live_api',
                   'response_rate_limit_headers': headers,
                   'usage': {'documentation': 'https://www.arbeitnow.com/blog/job-board-api',
                             'terms_url': 'https://www.arbeitnow.com/terms',
                             'conditions': 'API metadata requests no abuse. Terms section 11 requires a link back to Arbeitnow.com on your platform; service is as-is and permission can be revoked.',
                             'pacing': 'At most two requests, at least five seconds apart; no automatic retries. Rate-limit window not assumed from headers.',
                             'refresh': 'Observed API metadata says listings update hourly. Reuse saved samples instead of repeated exploration requests.'}})
    output = Path(__file__).resolve().parent / 'data/arbeitnow_analysis.json'
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        temporary.replace(output)
    except OSError as exc:
        print(f'Cannot save analysis: {exc}', file=sys.stderr)
        return 1
    print(f'Analysis saved to {output}')
    if error:
        print(error, file=sys.stderr)
        return 1
    print(f"Sample: {report['sample']['unique_listings']} listings; {report['relevance']['appears_relevant']} appear relevant, including {report['relevance']['relevant_with_business_topic_in_title_or_tags']} with business-topic signals.")
    print('Inferred countries:', report['geography']['inferred_location_counts'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
