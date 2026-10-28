import type { Job } from './jobs';
import { extractProfile, readableParagraphs } from './profileText';

export function JobProfile({ job }: { job: Job }) {
 const profile = extractProfile(job.description);
 const skills = job.required_skills.split(';').map(skill => skill.trim()).filter(Boolean);
 const requirements = profile.qualifications;
 return <div className="job-profile" id={`profile-${job.id}`} role="region" aria-label={`Details for ${job.title}`}>
  {profile.structured && <><p className="profile-caption">From the listing · Original language</p><div className="profile-sections">
   {profile.overview.length > 0 && <section className="profile-section profile-overview"><h4>THE OPPORTUNITY</h4>{profile.overview.map((text,i) => <p key={i}>{text}</p>)}</section>}
   {profile.responsibilities.length > 0 && <section className="profile-section"><h4>WHAT YOU’LL DO</h4><ul>{profile.responsibilities.map((text,i) => <li key={i}>{text}</li>)}</ul></section>}
   {(requirements.length > 0 || skills.length > 0 || job.experience_level) && <section className="profile-section"><h4>WHAT THEY’RE LOOKING FOR</h4>{requirements.length > 0 && <ul>{requirements.map((text,i) => <li key={i}>{text}</li>)}</ul>}{job.experience_level && <p className="profile-fact"><strong>Listed experience level</strong><span>{job.experience_level}</span></p>}{skills.length > 0 && <div className="profile-skills"><span>Listed skills</span><div className="skills">{skills.map((skill,i) => <span key={i}>{skill}</span>)}</div></div>}</section>}
   {profile.perks.length > 0 && <section className="profile-section"><h4>THE PERKS</h4><ul>{profile.perks.map((text,i) => <li key={i}>{text}</li>)}</ul></section>}
  </div></>}
  {!profile.structured && (skills.length > 0 || job.experience_level) && <section className="profile-section source-facts"><h4>LISTING AT A GLANCE</h4>{job.experience_level && <p className="profile-fact"><strong>Listed experience level</strong><span>{job.experience_level}</span></p>}{skills.length > 0 && <div className="profile-skills"><span>Listed skills</span><div className="skills">{skills.map((skill,i) => <span key={i}>{skill}</span>)}</div></div>}</section>}
  {job.description && <details className="original-description" open={!profile.structured || undefined}><summary>Read original job description<span aria-hidden="true">+</span></summary><div className="original-copy">{readableParagraphs(job.description).map((text,i) => <p key={i}>{text}</p>)}</div></details>}
  {!job.description && <p className="profile-no-description">Description not provided. Visit the source listing for details.</p>}
  {(job.job_type || job.publication_date) && <dl className="profile-metadata">{job.job_type && <div><dt>Listed job type</dt><dd>{job.job_type}</dd></div>}{job.publication_date && <div><dt>Published</dt><dd>{new Date(job.publication_date).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'})}</dd></div>}</dl>}
 </div>;
}
