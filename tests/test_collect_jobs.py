import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import collect_jobs as c


def job(identifier='1', **extra):
    return {'id': identifier, 'title': 'Graduate Business Analyst',
            'country': 'PT', 'company': 'Example', **extra}


def page(jobs, following=None):
    return {'data': jobs, 'links': {'next': following}}


INDEX = {'data': [{'code': 'PT'}]}


class CollectorTests(unittest.TestCase):
    def collect(self, responses, **options):
        with patch.object(c, 'fetch', side_effect=[INDEX, *responses]) as fetch, \
                patch.object(c.time, 'sleep'), patch('builtins.print'):
            rows, report = c.collect(500, 3, countries=('FI', 'PT'),
                                     keywords=('intern', 'graduate'), **options)
        return rows, report, fetch

    def test_global_deduplication_pagination_and_unavailable_country(self):
        rows, report, fetch = self.collect([
            page([job()], '?page=2'), page([job(), job('2')]), page([job('3')])])
        self.assertEqual(len(rows), 3)
        self.assertEqual(report['duplicates_removed'], 1)
        self.assertEqual(report['by_country'], {'FI': 0, 'PT': 3})
        self.assertEqual(report['searches'][0]['status'], 'country_unavailable')
        urls = [call.args[0] for call in fetch.call_args_list]
        self.assertIn('q=graduate', urls[2])
        self.assertIn('page=2', urls[3])
        self.assertNotIn('country=FI', ' '.join(urls))

    def test_canonical_url_deduplication_with_different_ids(self):
        rows, report, _ = self.collect([
            page([job(url='https://EXAMPLE.com/job/?utm_source=x&id=4#top')]),
            page([job('2', url='https://example.com/job?id=4')])])
        self.assertEqual(len(rows), 1)
        self.assertEqual(report['duplicates_removed'], 1)
        self.assertNotEqual(c.canonical_url('https://example.com/?id=1'),
                            c.canonical_url('https://example.com/?id=2'))

    def test_early_career_country_and_priority(self):
        rows, report, _ = self.collect([page([
            job('1', title='Senior Strategy Consultant', experienceLevel='junior'),
            job('2', title='Strategy Consultant', experienceLevel='mid'),
            job('3', title='Marketing Intern', country='DE'),
            job('4', title='Intern', country=None),
            job('5', title='Intern', description='<p>Hello</p><p>World</p>'),
            job('6', title='Graduate Sustainability Consultant')]), page([])])
        self.assertEqual(report['excluded'], 4)
        self.assertEqual(rows[0]['title'], 'Graduate Sustainability Consultant')
        self.assertEqual(rows[1]['description'], 'Hello World')
        self.assertEqual(rows[1]['required_skills'], '')
        self.assertEqual(report['searches'][-1]['status'], 'no_results')

    def test_partial_failure_stops_globally(self):
        rows, report, fetch = self.collect([page([job()]), c.CollectionError('outage')])
        self.assertEqual(len(rows), 1)
        self.assertEqual(report['stop_reason'], 'error')
        self.assertEqual(fetch.call_count, 3)

    def test_limit_avoids_further_requests(self):
        with patch.object(c, 'fetch', side_effect=[INDEX, page([job(), job('2')])]) as fetch, \
                patch.object(c.time, 'sleep'), patch('builtins.print'):
            rows, report = c.collect(1, 3, ('PT',), ('intern', 'graduate'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(report['stop_reason'], 'limit_reached')
        self.assertEqual(report['searches'][1]['status'], 'not_searched')

    def test_page_budget_and_repeat_protection(self):
        _, report, fetch = self.collect([page([], None)], max_pages=1)
        self.assertEqual(report['stop_reason'], 'page_budget_reached')
        self.assertEqual(fetch.call_count, 2)
        with self.assertRaises(c.CollectionError):
            c.next_page(page([], '?page=1'), 1)

    def test_failure_preserves_existing_csv_and_writes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'jobs.csv'
            output.write_text('previous successful collection')
            with patch.object(c, 'fetch', side_effect=c.CollectionError('offline')), \
                    patch('sys.argv', ['collect_jobs.py', '--output', str(output)]), \
                    patch('builtins.print'):
                self.assertEqual(c.main(), 1)
            self.assertEqual(output.read_text(), 'previous successful collection')
            self.assertTrue(output.with_suffix('.report.json').exists())

    def test_rate_limit_retry_after(self):
        error = HTTPError(c.ENDPOINT, 429, 'Rate limited', {'Retry-After': '7'}, None)
        with patch.object(c, 'urlopen', side_effect=error) as request, \
                patch.object(c.time, 'sleep') as sleep, patch('builtins.print'):
            with self.assertRaises(c.CollectionError):
                c.fetch(c.ENDPOINT, 3)
        self.assertEqual(request.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [7, 7])
        with self.assertRaises(c.CollectionError):
            c.retry_delay({'Retry-After': '600'}, 0)


if __name__ == '__main__':
    unittest.main()
