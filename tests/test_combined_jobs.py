import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import collect_arbeitnow as collector
import combine_jobs
import explore_arbeitnow as exploration
import job_dataset as d


def row(**values):
    result = dict.fromkeys(d.FIELDS, '')
    result.update(title='Finance Intern', company='Example', data_source='arbeitnow')
    result.update(values)
    return result


class DatasetTests(unittest.TestCase):
    def test_normalization_does_not_invent_fields(self):
        normalized = d.normalize_arbeitnow({'title': 'Finance Intern', 'company_name': 'Example',
            'location': 'Berlin', 'tags': ['Finance'], 'slug': 'intern-1',
            'description': '&lt;p&gt;Hello&lt;/p&gt;', 'created_at': 0,
            'job_types': ['Internship'], 'url': 'https://example.com/job'})
        self.assertEqual(normalized['description'], 'Hello')
        self.assertEqual(normalized['publication_date'], '1970-01-01T00:00:00Z')
        self.assertEqual(normalized['source_tags'], 'Finance')
        for key in ('country', 'required_skills', 'experience_level'):
            self.assertEqual(normalized[key], '')
        self.assertEqual(d.normalize_arbeitnow({})['publication_date'], '')
        self.assertEqual(d.publication('not a date'), '')
        self.assertEqual(d.publication('2026-01-01T12:00:00+02:00'), '2026-01-01T10:00:00Z')

    def test_previous_analysis_rule_parity(self):
        jobs = [
            {'title': 'Finance Intern'}, {'title': 'Graduate Program'},
            {'title': 'Trainee Consultant'}, {'title': 'Junior Engineer'},
            {'title': 'Junior Business Analyst'}, {'title': 'Senior Finance Intern'},
            {'title': 'Working Student Marketing'}, {'title': 'International Business Manager'},
            {'title': 'Junior Associate', 'tags': ['Finance']},
            {'title': 'Consultant', 'description': 'We offer internships too.'},
        ]
        expected = exploration.analyze([{'data': jobs}])['relevance']['appears_relevant']
        actual = sum(d.eligibility(j['title'], '', j.get('tags', []))[0] for j in jobs)
        self.assertEqual(actual, expected)
        self.assertEqual(actual, 6)
        self.assertFalse(d.eligibility('Junior Engineer')[0])
        self.assertFalse(d.eligibility('Consulting Director', experience='junior')[0])
        self.assertTrue(d.eligibility('Estagiário de Marketing', portuguese=True)[0])

    def test_urls_and_scoped_ids(self):
        first = row(original_job_url='https://EXAMPLE.com/job/?id=1&utm_source=a#top')
        same = row(original_job_url='https://example.com/job?id=1')
        distinct = row(original_job_url='https://example.com/job?id=2')
        unique, groups = d.deduplicate([first, same, distinct])
        self.assertEqual(len(unique), 2)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(d.deduplicate([row(source_job_id='1'),
            row(source_job_id='1', data_source='okemprego')])[0]), 2)

    def test_exact_content_and_identity_bridges(self):
        desc = 'Specific duties and qualifications for this particular position. ' * 3
        a = row(location='Berlin', description=desc, original_job_url='https://a.com/1')
        b = row(location='Berlin', description=desc, original_job_url='https://b.com/2')
        self.assertEqual(len(d.deduplicate([a, b])[0]), 1)
        # A shared title/company alone is insufficient to remove another job.
        self.assertEqual(len(d.deduplicate([row(), row()])[0]), 2)
        records = [row(source_job_id='a', original_job_url='https://a.com/1'),
                   row(source_job_id='b', original_job_url='https://a.com/2'),
                   row(source_job_id='a', original_job_url='https://a.com/2')]
        self.assertEqual(len(d.deduplicate(records)[0]), 1)

    def test_merge_filters_both_sources_and_reports(self):
        ok = [row(data_source='okemprego', country='PT', title='Junior Software Engineer'),
              row(data_source='okemprego', country='PT', title='Junior Finance Analyst')]
        work = [row(title='Graduate Consultant'), row(title='Senior Strategy Consultant')]
        rows, report = combine_jobs.combine(ok, work)
        self.assertEqual(len(rows), 2)
        self.assertEqual(report['by_country'], {'PT': 1, 'unknown': 1})
        self.assertEqual(report['collected_by_source']['okemprego']['excluded'], 1)
        self.assertEqual(report['collected_by_source']['arbeitnow']['excluded'], 1)

    def test_pagination_and_pacing(self):
        responses = [({'data': [{'title': 'Finance Intern', 'slug': '1'}],
                       'links': {'next': exploration.ENDPOINT + '?page=2'}}, {}),
                     ({'data': [{'title': 'Graduate Program', 'slug': '2'}],
                       'links': {'next': None}}, {})]
        with patch.object(exploration, 'retrieve', side_effect=responses) as fetch, \
                patch.object(collector.time, 'sleep') as sleep:
            rows, report = collector.collect(pages=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(5)
        self.assertEqual(report['stop_reason'], 'exhausted')

    def test_failure_preserves_existing_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            output = root / 'data/jobs_arbeitnow.csv'
            output.write_text('previous successful snapshot')
            error = HTTPError(exploration.ENDPOINT, 429, 'Too many requests', {'Retry-After': '60'}, None)
            with patch.object(collector, 'ROOT', root), \
                    patch.object(exploration, 'retrieve', side_effect=error) as fetch, \
                    patch('sys.argv', ['collect_arbeitnow.py']), patch('builtins.print'):
                self.assertEqual(collector.main(), 1)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(output.read_text(), 'previous successful snapshot')
            self.assertEqual(json.loads((root / 'data/jobs_arbeitnow.report.json').read_text())['retry_after'], '60')


if __name__ == '__main__':
    unittest.main()
