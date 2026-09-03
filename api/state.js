// Persistence for the dashboard's Saved and Dismissed collections.
//
// Only reachable on the Vercel deployment. The GitHub Pages copy of the same
// page has no backend and falls back to localStorage, so the client treats a
// failed request here as "run local", not as an error.
//
// ACCESS: this endpoint has no auth of its own. It is protected by Vercel
// Deployment Protection, which is what keeps the dashboard private. Turning
// protection off would expose read and write on a public URL — add auth here
// first if that ever happens.
import { neon } from '@neondatabase/serverless';

const REPO = /^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/;
const MAX_MERGE = 500;

// Lazy: a top-level neon() call throws at import time when the env var is
// missing, which would take down the whole function instead of one request.
let _sql = null;
function db() {
  if (!_sql) {
    if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL is not set');
    _sql = neon(process.env.DATABASE_URL);
  }
  return _sql;
}

const day = v => (v instanceof Date ? v.toISOString() : String(v || '')).slice(0, 10);

async function readState(sql) {
  const rows = await sql`
    select full_name, status, run_id, snapshot, updated_at from repo_state
  `;
  const state = { saved: {}, dismissed: {} };
  for (const row of rows) {
    if (row.status === 'saved') {
      state.saved[row.full_name] = Object.assign({}, row.snapshot || {}, {
        full_name: row.full_name,
        _run: row.run_id || null,
        _saved_at: day(row.updated_at),
      });
    } else {
      state.dismissed[row.full_name] = { at: day(row.updated_at) };
    }
  }
  return state;
}

async function setStatus(sql, name, status, runId, snapshot) {
  await sql`
    insert into repo_state (full_name, status, run_id, snapshot, updated_at)
    values (${name}, ${status}, ${runId || null}, ${snapshot ? JSON.stringify(snapshot) : null}, now())
    on conflict (full_name) do update set
      status = excluded.status,
      run_id = excluded.run_id,
      snapshot = excluded.snapshot,
      updated_at = now()
  `;
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    const sql = db();

    if (req.method === 'GET') {
      return res.status(200).json(await readState(sql));
    }
    if (req.method !== 'POST') {
      res.setHeader('Allow', 'GET, POST');
      return res.status(405).json({ error: 'method not allowed' });
    }

    const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
    const { action } = body;

    // One-time hand-off: entries saved in a browser before the database
    // existed get pushed up on first load, without clobbering rows already
    // here — the database is the newer source of truth for anything it holds.
    if (action === 'merge') {
      const saved = body.saved || {};
      const dismissed = body.dismissed || {};
      const entries = [
        ...Object.entries(saved).map(([n, v]) => ['saved', n, v]),
        ...Object.entries(dismissed).map(([n]) => ['dismissed', n, null]),
      ].filter(([, n]) => REPO.test(n)).slice(0, MAX_MERGE);

      for (const [status, name, snap] of entries) {
        await sql`
          insert into repo_state (full_name, status, run_id, snapshot)
          values (${name}, ${status}, ${(snap && snap._run) || null},
                  ${snap ? JSON.stringify(snap) : null})
          on conflict (full_name) do nothing
        `;
      }
      return res.status(200).json(await readState(sql));
    }

    const name = body.full_name;
    if (!REPO.test(name || '')) return res.status(400).json({ error: 'bad full_name' });

    if (action === 'save') {
      await setStatus(sql, name, 'saved', body.run_id, body.snapshot);
    } else if (action === 'dismiss') {
      await setStatus(sql, name, 'dismissed', null, null);
    } else if (action === 'unsave' || action === 'restore') {
      const want = action === 'unsave' ? 'saved' : 'dismissed';
      await sql`delete from repo_state where full_name = ${name} and status = ${want}`;
    } else {
      return res.status(400).json({ error: 'unknown action' });
    }

    return res.status(200).json(await readState(sql));
  } catch (err) {
    console.error('[state]', err);
    return res.status(500).json({ error: 'state unavailable' });
  }
}
