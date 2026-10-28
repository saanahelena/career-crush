export type Job = { id: string; title: string; company: string; location: string; country: string; description: string; required_skills: string; experience_level: string; job_type: string; publication_date: string; original_job_url: string; data_source: string; source_job_id: string; source_tags: string };
export const countries: Record<string, string> = { PT:'Portugal', FI:'Finland', DE:'Germany', NL:'Netherlands', SE:'Sweden', DK:'Denmark', BE:'Belgium', FR:'France', CH:'Switzerland', GB:'United Kingdom' };
export function careerType(job: Job): string {
 const value = `${job.title} ${job.job_type} ${job.experience_level || ""}`.toLowerCase();
 if (/intern|praktik|stage|stagia|est[aá]gi/.test(value)) return 'Internship';
 if (/graduate|absolvent/.test(value)) return 'Graduate';
 if (/trainee/.test(value)) return 'Trainee';
 if (/werkstudent|working student|student college/.test(value)) return 'Working student';
 if (/junior|júnior|entry/.test(value)) return 'Junior';
 return 'Early career';
}
export function workMode(job: Job): string {
 // Only explicit structured labels qualify, never incidental description mentions.
 const value = `${job.job_type} ${job.source_tags || ''}`.toLowerCase();
 if (/\bhybrid\b/.test(value)) return 'Hybrid';
 if (/\bremote\b/.test(value)) return 'Remote';
 if (/\bon[ -]?site\b/.test(value)) return 'On-site';
 return '';
}
export function category(job: Job): string { return job.source_tags; }
export type Filters = { query: string; country: string; career: string; category: string; mode: string };
export function filterJobs(jobs: Job[], filters: Filters): Job[] {
 const words = filters.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
 return jobs.filter(job => {
  const haystack = `${job.title} ${job.company} ${job.description} ${job.required_skills} ${job.source_tags}`.toLowerCase();
  return words.every(word => haystack.includes(word)) &&
   (!filters.country || (job.country || 'unknown') === filters.country) &&
   (!filters.career || careerType(job) === filters.career) &&
   (!filters.category || job.source_tags.split('; ').includes(filters.category)) &&
   (!filters.mode || (workMode(job) || 'unknown') === filters.mode);
 });
}
export function readSaved(raw: string | null, jobs: Job[]): string[] {
 try { const parsed: unknown = JSON.parse(raw || '[]'); return Array.isArray(parsed) ? [...new Set(parsed.filter((id): id is string => typeof id === 'string' && jobs.some(job => job.id === id)))] : []; } catch { return []; }
}
export function safeUrl(url: string): string | undefined { try { const parsed = new URL(url); return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : undefined; } catch { return undefined; } }
