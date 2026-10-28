"""Create a browser-readable snapshot without altering the source CSV."""
import csv
import hashlib
import json
from pathlib import Path
web_root = Path(__file__).resolve().parents[1]
root = web_root.parent
source = root / 'data/jobs_combined.csv'
if not source.exists() and (web_root / 'src/data/jobs.json').exists():
    print('Using the committed real-job snapshot; source CSV is not in this checkout.')
    raise SystemExit(0)
with source.open(encoding='utf-8-sig', newline='') as handle:
    jobs = list(csv.DictReader(handle))
for job in jobs:
    identity = job.get('original_job_url') or '|'.join(job.get(k, '') for k in ('data_source', 'source_job_id', 'company', 'title', 'location'))
    job['id'] = hashlib.sha256(identity.encode()).hexdigest()[:24]
output = web_root / 'src/data/jobs.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(jobs, ensure_ascii=False), encoding='utf-8')
print(f'Prepared {len(jobs)} real listings for the website.')
