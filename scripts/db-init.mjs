// Creates the one table the dashboard needs. Safe to re-run.
//
//   node --env-file=.env.local scripts/db-init.mjs
//
// Run it once per database. The API function deliberately does not create
// tables on the hot path: a CREATE TABLE IF NOT EXISTS on every request buys
// nothing and costs a round trip.
import { neon } from '@neondatabase/serverless';

const url = process.env.DATABASE_URL;
if (!url) {
  console.error('DATABASE_URL is not set. Run: vercel env pull .env.local');
  process.exit(1);
}
const sql = neon(url);

// One row per repo. Saved and dismissed are opposite states of the same repo,
// not two independent flags, so status is a single column rather than two
// tables — it makes "saving clears the dismissal" a plain upsert.
await sql`
  create table if not exists repo_state (
    full_name  text primary key,
    status     text not null check (status in ('saved', 'dismissed')),
    run_id     text,
    snapshot   jsonb,
    updated_at timestamptz not null default now()
  )
`;
await sql`create index if not exists repo_state_status_idx on repo_state (status, updated_at desc)`;

const [{ count }] = await sql`select count(*)::int as count from repo_state`;
console.log(`repo_state ready · ${count} row${count === 1 ? '' : 's'}`);
