import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { extractProfile, readableParagraphs } from './profileText.ts';

test('extracts explicit source statements verbatim with no inferred claims', () => {
 const description = 'Acme is seeking a Finance Intern. You will prepare monthly reports. The ideal candidate holds a finance degree. Benefits include paid training.';
 const profile = extractProfile(description);
 assert.deepEqual(profile.overview, ['Acme is seeking a Finance Intern.']);
 assert.deepEqual(profile.responsibilities, ['You will prepare monthly reports.']);
 assert.deepEqual(profile.qualifications, ['The ideal candidate holds a finance degree.']);
 assert.deepEqual(profile.perks, ['Benefits include paid training.']);
 for (const text of [...profile.overview, ...profile.responsibilities, ...profile.qualifications, ...profile.perks]) assert.ok(description.includes(text));
});
test('topic keywords alone never become invented duties or qualifications', () => {
 const profile = extractProfile('A growing sustainability business with finance clients. Training, Excel, and reports are topics we discuss.');
 assert.equal(profile.structured, false);
 assert.deepEqual(profile.responsibilities, []);
 assert.deepEqual(profile.qualifications, []);
 assert.deepEqual(profile.perks, []);
 assert.deepEqual(extractProfile('We offer consulting services. You will receive applications. You will need a degree.').responsibilities, []);
});
test('recognizes only clearly scoped labelled lists, without duplicate sentences', () => {
 const description = 'A role at Acme.\nResponsibilities:\n- You will prepare reports. You will maintain records.\n- Coordinate meetings.\nAbout the company:\nWe are growing.\nRequirements:\n• A finance degree.\nBenefits:\n• Paid leave.';
 const profile = extractProfile(description);
 assert.deepEqual(profile.responsibilities, ['You will prepare reports. You will maintain records.', 'Coordinate meetings.']);
 assert.deepEqual(profile.qualifications, ['A finance degree.']);
 assert.deepEqual(profile.perks, ['Paid leave.']);
 assert.ok(!JSON.stringify(profile.responsibilities).includes('growing'));
});
test('unlabelled prose after a heading is not absorbed into its list', () => {
 const profile = extractProfile('Responsibilities:\n- Coordinate meetings.\nAbout the company\n- We sell products.');
 assert.deepEqual(profile.responsibilities, ['Coordinate meetings.']);
});
test('Portuguese statements stay in Portuguese', () => {
 const profile = extractProfile('O banco procura um estagiário. Será responsável pela análise de dados. Procuramos candidatos com formação em Gestão.');
 assert.deepEqual(profile.responsibilities, ['Será responsável pela análise de dados.']);
 assert.deepEqual(profile.qualifications, ['Procuramos candidatos com formação em Gestão.']);
 assert.deepEqual(profile.perks, []);
});
test('fallback paragraph breaks preserve all words, numbers and punctuation', () => {
 const source = ('Acme procura candidatos com formação em Gestão. O programa dura 12 meses. ' + 'Esta frase contém informação original e não deve ser traduzida nem resumida. ').repeat(7);
 const paragraphs = readableParagraphs(source);
 assert.ok(paragraphs.length > 1);
 assert.equal(paragraphs.join(' ').replace(/\s+/g,' ').trim(), source.replace(/\s+/g,' ').trim());
 assert.equal(readableParagraphs(('Software em C# e .NET. Acesse https://example.com/job. ').repeat(15)).join(' '), ('Software em C# e .NET. Acesse https://example.com/job. ').repeat(15).trim());
 assert.deepEqual(readableParagraphs(''), []);
 assert.equal(extractProfile('').structured, false);
});
