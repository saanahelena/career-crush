/** Conservative, verbatim presentation only. Never translate or infer job requirements. */
export type Profile = { overview: string[]; responsibilities: string[]; qualifications: string[]; perks: string[]; structured: boolean };
type Section = 'responsibilities' | 'qualifications' | 'perks';
const leads: Record<Section, RegExp> = {
 responsibilities: /^(?:(?:in this role,? )?(?:you will|you'll) (?:also )?(?:be responsible for|support|assist|prepare|manage|develop|analyse|analyze|contribute|collaborate|conduct|create|maintain|monitor|coordinate|handle|deliver|implement|research|evaluate|document|follow up)\b|your responsibilities (?:include|are)\b|the role involves\b|nesta fun[çc][ãa]o,? (?:ir[áa]|ser[áa])\b|ser[áa] respons[áa]vel\b|as suas (?:principais )?(?:atividades|responsabilidades) incluem\b)/i,
 qualifications: /^(?:the ideal candidate\b|candidates (?:should|must)\b|you (?:must|should) (?:have|hold|possess|demonstrate)\b|proficiency in .+ (?:is required|is essential)\b|we require\b|procuramos (?:candidatos|candidatas) com\b|procuramos (?:um|uma) .+ com (?:forma[çc][ãa]o|experi[êe]ncia|conhecimentos)\b|[ée] essencial\b|[ée] obrigat[óo]ri[oa]\b)/i,
 perks: /^(?:benefits include\b|our benefits include\b|os benef[íi]cios incluem\b)/i,
};
const headingNames: Record<Section, string[]> = {
 responsibilities: ['Responsibilities', 'Key responsibilities', 'What you’ll do', "What you'll do", 'Responsabilidades', 'Principais responsabilidades'],
 qualifications: ['Requirements', 'Qualifications', 'What we’re looking for', "What we're looking for", 'Requisitos', 'Qualificações'],
 perks: ['Benefits', 'Perks', 'What we offer', 'Benefícios', 'O que oferecemos'],
};
export function sentences(text: string): string[] {
 // Segmenter respects punctuation and abbreviations; output remains source text.
 const result: string[] = [];
 let current = '';
 for (const part of new Intl.Segmenter(undefined, { granularity: 'sentence' }).segment(text)) {
  // Never introduce a break inside tokens such as .NET or a URL.
  if (current && /\s$/.test(current)) { result.push(current.trim()); current = ''; }
  current += part.segment;
 }
 if (current.trim()) result.push(current.trim());
 return result.filter(Boolean);
}
export function readableParagraphs(text: string): string[] {
 const blocks = text.split(/\n\s*\n/).map(block => block.trim()).filter(Boolean);
 return blocks.flatMap(block => {
  if (block.length <= 450) return [block];
  const result: string[] = [];
  let current = '';
  let count = 0;
  for (const sentence of sentences(block)) {
   if (current && (count >= 2 || current.length + sentence.length > 450)) {
    result.push(current); current = ''; count = 0;
   }
   current += (current ? ' ' : '') + sentence; count++;
  }
  if (current) result.push(current);
  return result;
 });
}
export function extractProfile(description: string): Profile {
 const profile: Profile = { overview: [], responsibilities: [], qualifications: [], perks: [], structured: false };
 const assigned = new Set<string>();
 let section: Section | null = null;
 // Headings must be on their own line (optionally followed by a colon).
 // Colons, bullets, or keywords within ordinary prose are not headings.
 for (const raw of description.split('\n')) {
  const line = raw.trim();
  if (!line) continue;
  const heading = line.replace(/:\s*$/, '').trim().toLocaleLowerCase();
  const match = (Object.keys(headingNames) as Section[]).find(key => headingNames[key].some(name => name.toLocaleLowerCase() === heading));
  if (match) { section = match; continue; }
  // An unrecognized heading ends the recognized section rather than absorbing it.
  if (section && (/^[^.!?]{1,65}:$/.test(line) || /^[A-Z][A-Z\s’'&-]{2,60}$/.test(line))) { section = null; continue; }
  if (section && !/^(?:[-•*]|\d+[.)])\s+/.test(line)) section = null;
  if (section) {
   const content = line.replace(/^(?:[-•*]|\d+[.)])\s+/, '').trim();
   if (content && !assigned.has(content)) { profile[section].push(content); assigned.add(content); }
  }
 }
 // For flattened descriptions, accept complete sentences only when they make
 // explicit claims about the role/candidate/benefits. Never build claims from keywords.
 for (const sentence of sentences(description)) {
  if (sentence.includes('\n')) continue;
  const key = (Object.keys(leads) as Section[]).find(key => leads[key].test(sentence));
  if (key && ![...assigned].some(text => text.includes(sentence))) { profile[key].push(sentence); assigned.add(sentence); }
 }
 profile.structured = Object.keys(leads).some(key => profile[key as Section].length > 0);
 if (profile.structured) {
  const first = sentences(description)[0];
  // Only a short opening sentence can act as an overview; do not synthesize one.
  if (first && first.length <= 400 && !first.includes('\n') &&
      !assigned.has(first) && !Object.values(headingNames).flat().some(h => first.toLowerCase().startsWith(h.toLowerCase()))) {
   profile.overview = [first];
  }
 }
 return profile;
}
