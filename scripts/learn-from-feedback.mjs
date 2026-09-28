// Learn from what gets saved and dismissed on the dashboard.
//
// repo_state (Neon) is the only record of Meagan's opinion on a pick. Saved
// rows carry a full snapshot of the card; dismissed rows carry only
// full_name (api/state.js's dismiss handler stores no snapshot at all), so
// dismissed metadata is recovered by joining against docs/data/index.json's
// 52-run window -- the same pick, seen when it first surfaced.
//
// Deterministic, no LLM: everything here is counting distinct repos per
// owner/word/topic and comparing dismissed counts against saved counts.
// Two narrow, reversible edit types auto-apply, each capped per run so one
// noisy month cannot rewrite the config:
//   - owner_denylist: an owner dismissed 2+ times with zero saves, and not
//     a large org (checked against the GitHub API -- a mega-org like
//     microsoft having two dismissed repos out of thousands is noise, not
//     a pattern; this guard exists because the first live run tried to
//     denylist microsoft on an n=2 sample)
//   - a lane's topics list: a topic on 2+ saved repos, not in any active
//     lane yet, added to whichever lane those repos already led under
//
// A third signal -- single words common across dismissed repos' name and
// description -- is report-only, logged as a suggestion rather than folded
// into global_excludes automatically. The first live run's top candidate
// was "multi-agent", which is lane 1's own topic tag: a word frequent in
// dismissals is not evidence the WORD is bad, only that these particular
// repos were bad, and lanes deliberately share vocabulary (the same lesson
// lane_evidence's strong/weak split already encodes). A hard exclude here
// is much harder to reverse cleanly than an owner or a topic entry, so it
// stays a suggestion for a human to weigh.
//
// Every change (and every suggestion) is appended to docs/learned-
// adjustments.md with the evidence, so an unattended monthly run stays
// auditable.
//
//   node --env-file=.env.local scripts/learn-from-feedback.mjs [--dry-run]

import { neon } from '@neondatabase/serverless';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CONFIG_PATH = path.join(ROOT, 'config', 'lanes.json');
const INDEX_PATH = path.join(ROOT, 'docs', 'data', 'index.json');
const LOG_PATH = path.join(ROOT, 'docs', 'learned-adjustments.md');

const DRY_RUN = process.argv.includes('--dry-run');
const OWNER_DISMISS_MIN = 2;
const OWNER_MAX_PUBLIC_REPOS = 30; // above this, treat as a large org: 2 dismissals is noise, not a pattern
const PHRASE_DISMISS_MIN = 3;
const PHRASE_DISMISS_OWNERS_MIN = 2; // distinct owners, so one repeat-offender repo family can't skew a word
const TOPIC_SAVE_MIN = 2;
const MAX_NEW_OWNERS = 5;
const MAX_SUGGESTED_PHRASES = 3;
const MAX_NEW_TOPICS = 3;
const TOPIC_MAX_RESULTS = 20000; // above this, the topic is industry-wide, not a lane signal

async function publicRepoCount(login, token) {
  try {
    const headers = { 'User-Agent': 'repo-radar', 'Accept': 'application/vnd.github+json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    const resp = await fetch(`https://api.github.com/users/${encodeURIComponent(login)}`, { headers });
    if (!resp.ok) return null;
    const data = await resp.json();
    return typeof data.public_repos === 'number' ? data.public_repos : null;
  } catch {
    return null;
  }
}

async function topicResultCount(topic, token) {
  try {
    const headers = { 'User-Agent': 'repo-radar', 'Accept': 'application/vnd.github+json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    const q = encodeURIComponent(`topic:${topic}`);
    const resp = await fetch(`https://api.github.com/search/repositories?q=${q}&per_page=1`, { headers });
    if (!resp.ok) return null;
    const data = await resp.json();
    return typeof data.total_count === 'number' ? data.total_count : null;
  } catch {
    return null;
  }
}

// Generic enough to show up in almost any description; mining on these would
// exclude everything and nothing at once.
const STOPWORDS = new Set([
  'this', 'that', 'with', 'from', 'your', 'into', 'have', 'that', 'will',
  'each', 'their', 'about', 'based', 'using', 'used', 'use', 'for', 'and',
  'the', 'you', 'can', 'are', 'was', 'its', 'it\'s', 'now', 'via', 'app',
  'tool', 'tools', 'open', 'source', 'simple', 'easy', 'fast', 'new', 'like',
  'more', 'all', 'one', 'get', 'run', 'runs', 'running', 'works', 'work',
  'project', 'projects', 'built', 'build', 'building', 'made', 'make',
  'code', 'codebase', 'repo', 'repository', 'github', 'python', 'javascript',
  'typescript', 'node', 'library', 'framework', 'server', 'client', 'api',
]);

function words(text) {
  return (text || '').toLowerCase().match(/[a-z][a-z'-]{3,}/g) || [];
}

function ownerOf(fullName) {
  return fullName.split('/')[0].toLowerCase();
}

function loadIndexPicks() {
  if (!existsSync(INDEX_PATH)) return new Map();
  const data = JSON.parse(readFileSync(INDEX_PATH, 'utf8'));
  const picks = new Map();
  for (const run of data.runs || []) {
    for (const p of run.picks || []) {
      if (!picks.has(p.full_name)) picks.set(p.full_name, p);
    }
  }
  return picks;
}

async function main() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    console.error('DATABASE_URL is not set. Run: vercel env pull .env.local');
    process.exit(1);
  }
  const sql = neon(url);
  const config = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'));
  const indexPicks = loadIndexPicks();

  const rows = await sql`select full_name, status, snapshot from repo_state`;

  const dismissed = [];
  const saved = [];
  let dismissedUnresolved = 0;
  for (const row of rows) {
    if (row.status === 'saved') {
      saved.push({ full_name: row.full_name, meta: row.snapshot || {} });
    } else {
      const meta = row.snapshot || indexPicks.get(row.full_name);
      if (meta) dismissed.push({ full_name: row.full_name, meta });
      else dismissedUnresolved++;
    }
  }

  console.log(`repo_state: ${saved.length} saved, ${dismissed.length} dismissed `
    + `(${dismissedUnresolved} dismissed with no recoverable metadata, skipped)`);

  const existingDenylist = new Set(
    (config.global_excludes.owner_denylist || []).map(o => o.toLowerCase())
  );
  const existingLaneTopics = new Set();
  const existingLaneKeywords = new Set();
  for (const lane of config.lanes) {
    for (const t of lane.topics || []) existingLaneTopics.add(t.toLowerCase());
    for (const k of lane.keywords || []) existingLaneKeywords.add(k.toLowerCase());
  }

  const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN || '';

  // --- owner denylist -------------------------------------------------
  const dismissByOwner = new Map(); // owner -> Set(full_name)
  const savedOwners = new Set(saved.map(r => ownerOf(r.full_name)));
  for (const r of dismissed) {
    const owner = ownerOf(r.full_name);
    if (savedOwners.has(owner)) continue; // a save from this owner overrides any dismissal pattern
    if (!dismissByOwner.has(owner)) dismissByOwner.set(owner, new Set());
    dismissByOwner.get(owner).add(r.full_name);
  }
  const ownerCandidates = [...dismissByOwner.entries()]
    .filter(([owner, repos]) => repos.size >= OWNER_DISMISS_MIN && !existingDenylist.has(owner))
    .sort((a, b) => b[1].size - a[1].size)
    .slice(0, MAX_NEW_OWNERS);

  // A mega-org (or a prolific individual) having a couple of dismissed repos
  // out of hundreds or thousands is not a pattern -- check actual repo count
  // before denylisting, so a name like microsoft never gets caught on n=2.
  const newOwners = [];
  for (const [owner, repos] of ownerCandidates) {
    const count = await publicRepoCount(owner, token);
    if (count !== null && count > OWNER_MAX_PUBLIC_REPOS) {
      console.log(`  skipping owner denylist for ${owner}: ${count} public repos, too large a sample to judge on ${repos.size} dismissals`);
      continue;
    }
    newOwners.push([owner, repos.size]);
  }

  // --- exclude-phrase suggestions (report-only, never auto-applied) -----
  // A word frequent across dismissed repos is evidence those repos were
  // unwanted, not evidence the WORD itself predicts junk -- lanes deliberately
  // share vocabulary, and a hard exclude is expensive to reverse cleanly once
  // live. Requiring 2+ distinct OWNERS (not just repos) also keeps one prolific
  // dismissed repo family from manufacturing a false pattern on its own.
  const dismissedWordOwners = new Map(); // word -> Map(owner -> Set(full_name))
  for (const r of dismissed) {
    const text = `${r.meta.full_name || r.full_name} ${r.meta.description || ''}`;
    const owner = ownerOf(r.full_name);
    for (const w of new Set(words(text))) {
      if (STOPWORDS.has(w) || existingLaneTopics.has(w) || existingLaneKeywords.has(w)) continue;
      if (!dismissedWordOwners.has(w)) dismissedWordOwners.set(w, new Map());
      const byOwner = dismissedWordOwners.get(w);
      if (!byOwner.has(owner)) byOwner.set(owner, new Set());
      byOwner.get(owner).add(r.full_name);
    }
  }
  const savedWords = new Set();
  for (const r of saved) {
    const text = `${r.meta.full_name || r.full_name} ${r.meta.description || ''}`;
    for (const w of words(text)) savedWords.add(w);
  }
  const existingPattern = config.global_excludes.name_or_description || '';
  const suggestedPhrases = [...dismissedWordOwners.entries()]
    .map(([w, byOwner]) => [w, [...byOwner.values()].reduce((s, set) => s + set.size, 0), byOwner.size])
    .filter(([w, repoCount, ownerCount]) => repoCount >= PHRASE_DISMISS_MIN
      && ownerCount >= PHRASE_DISMISS_OWNERS_MIN
      && !savedWords.has(w)
      && !existingPattern.toLowerCase().includes(w))
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_SUGGESTED_PHRASES);

  // --- lane topic additions ---------------------------------------------
  const activeLaneIds = new Set(config.lanes.map(l => l.id));
  const topicSaves = new Map(); // topic -> { repos: Set, leadLaneCounts: Map }
  for (const r of saved) {
    const leadLane = (r.meta.lanes || [])[0]?.id;
    for (const t of r.meta.topics || []) {
      const tl = t.toLowerCase();
      if (existingLaneTopics.has(tl)) continue;
      if (!topicSaves.has(tl)) topicSaves.set(tl, { repos: new Set(), leadLaneCounts: new Map() });
      const entry = topicSaves.get(tl);
      entry.repos.add(r.full_name);
      if (leadLane != null) entry.leadLaneCounts.set(leadLane, (entry.leadLaneCounts.get(leadLane) || 0) + 1);
    }
  }
  const topicCandidates = [];
  for (const [topic, entry] of topicSaves.entries()) {
    if (entry.repos.size < TOPIC_SAVE_MIN) continue;
    const bestLane = [...entry.leadLaneCounts.entries()].sort((a, b) => b[1] - a[1])[0];
    if (!bestLane || !activeLaneIds.has(bestLane[0])) continue;
    topicCandidates.push({ topic, laneId: bestLane[0], repoCount: entry.repos.size });
  }
  topicCandidates.sort((a, b) => b.repoCount - a.repoCount);

  // A topic this broad would loosen the lane's OWN strong-evidence bar for
  // nearly anything, not just repos like the ones that earned it a save --
  // "ai" appearing on 14 saved repos is really "most saved repos happen to
  // carry the industry-wide tag", not "ai" being a lane-1 signal. Checked
  // against actual result volume rather than a hardcoded stoplist.
  const newTopics = [];
  const suggestedTopics = [];
  for (const cand of topicCandidates.slice(0, MAX_NEW_TOPICS + 3)) {
    const total = await topicResultCount(cand.topic, token);
    if (total !== null && total > TOPIC_MAX_RESULTS) {
      suggestedTopics.push({ ...cand, total });
    } else if (newTopics.length < MAX_NEW_TOPICS) {
      newTopics.push(cand);
    }
  }
  const cappedNewTopics = newTopics;

  // --- apply --------------------------------------------------------------
  const stamp = new Date().toISOString().slice(0, 10);
  const logLines = [];

  if (newOwners.length) {
    config.global_excludes.owner_denylist = [
      ...(config.global_excludes.owner_denylist || []),
      ...newOwners.map(([owner]) => owner),
    ];
    for (const [owner, n] of newOwners) {
      logLines.push(`- **owner denylist:** \`${owner}\` (${n} dismissals, 0 saves)`);
    }
  }

  if (cappedNewTopics.length) {
    for (const { topic, laneId, repoCount } of cappedNewTopics) {
      const lane = config.lanes.find(l => l.id === laneId);
      lane.topics = [...(lane.topics || []), topic];
      logLines.push(`- **lane ${laneId} topic:** \`${topic}\` added (${repoCount} saved repos, `
        + `led under lane ${laneId})`);
    }
  }

  const suggestionLines = [
    ...suggestedTopics.map(({ topic, laneId, repoCount, total }) =>
      `- **lane ${laneId} topic (suggested, not applied):** \`${topic}\` -- ${repoCount} saved repos `
      + `led under lane ${laneId}, but topic:${topic} matches ${total.toLocaleString()} repos on GitHub, `
      + `too broad to trust as a lane signal without a human call`),
  ];
  suggestionLines.push(...suggestedPhrases.map(([w, repoCount, ownerCount]) => {
    const repos = [...dismissedWordOwners.get(w).values()].flatMap(s => [...s]);
    return `- **exclude phrase (suggested, not applied):** \`${w}\` (${repoCount} dismissed repos `
      + `across ${ownerCount} owners, 0 saved: ${repos.slice(0, 3).join(', ')}${repos.length > 3 ? ', …' : ''})`;
  }));

  if (!logLines.length && !suggestionLines.length) {
    console.log('Nothing crossed a threshold this run. No config changes, no suggestions.');
    return;
  }

  if (logLines.length) console.log(`${logLines.length} change(s):\n${logLines.join('\n')}`);
  if (suggestionLines.length) console.log(`\n${suggestionLines.length} suggestion(s) (not applied):\n${suggestionLines.join('\n')}`);

  if (DRY_RUN) {
    console.log('\n[dry run] config/lanes.json and docs/learned-adjustments.md not written.');
    return;
  }

  if (logLines.length) {
    // JSON.stringify drops the trailing .0 from whole-number floats
    // (weight: 1.0 -> 1), which is semantically identical but rewrites
    // every untouched lane on every run. Restore the hand-authored style
    // so the diff only shows what this run actually changed.
    const serialized = JSON.stringify(config, null, 2)
      .replace(/"(weight|star_weight|standing_weight)": (-?\d+)(?=[,\n])/g, '"$1": $2.0');
    writeFileSync(CONFIG_PATH, serialized + '\n');
  }

  const sections = [];
  if (logLines.length) sections.push(`**Applied:**\n\n${logLines.join('\n')}`);
  if (suggestionLines.length) sections.push(`**Suggested, review and fold in by hand:**\n\n${suggestionLines.join('\n')}`);
  const entry = `## ${stamp}\n\n${sections.join('\n\n')}\n\n`
    + `_${saved.length} saved, ${dismissed.length} dismissed in repo_state at run time._\n\n`;
  const prior = existsSync(LOG_PATH) ? readFileSync(LOG_PATH, 'utf8') : (
    '# Learned adjustments\n\n'
    + 'Auto-applied by `scripts/learn-from-feedback.mjs`, run monthly. Deterministic pattern '
    + 'mining over Saved/Dismissed on the dashboard -- no LLM, no judgment calls beyond the '
    + 'thresholds in the script. Review `config/lanes.json` diffs same as any other commit; '
    + 'anything here can be hand-reverted.\n\n'
  );
  writeFileSync(LOG_PATH, prior + entry);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
