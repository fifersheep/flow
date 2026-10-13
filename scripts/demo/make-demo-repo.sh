#!/usr/bin/env bash
# Build the fictional repo the README's screenshots and GIF are taken in.
#
#   scripts/demo/make-demo-repo.sh DIR
#
# DIR/acme-api is a small TypeScript API (git, with a worktree beside it at
# DIR/acme-api-audit-log) holding three flow tasks, fixed in place so every
# capture shows the same thing:
#   rate-limits  this checkout, implementation, 3/7 done, one deviation
#   audit-log    its own worktree, plan-review: researched, planned and
#                critiqued, so gate 1 waits only on you
#   csv-export   complete
# Everything here is made up; DIR's demo folders are wiped first.
set -euo pipefail

dir=${1:?usage: make-demo-repo.sh DIR}
repo="$dir/acme-api"
wt="$dir/acme-api-audit-log"
[ -d "$repo" ] && git -C "$repo" worktree prune 2>/dev/null || true
rm -rf "$repo" "$wt"
mkdir -p "$repo"
cd "$repo"

git init -q -b main
git config user.name "Demo"
git config user.email "demo@example.com"

# --- the codebase -----------------------------------------------------------

cat > README.md <<'EOF'
# acme-api

Acme's public API: Hono on Node, SQLite through better-sqlite3.

    npm install
    npm test
EOF
cat > package.json <<'EOF'
{
  "name": "acme-api",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "tsx watch src/server.ts",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": { "better-sqlite3": "^11.3.0", "hono": "^4.6.3" },
  "devDependencies": { "tsx": "^4.19.1", "typescript": "^5.6.2", "vitest": "^2.1.2" }
}
EOF
mkdir -p src/admin src/jobs migrations test
cat > src/server.ts <<'EOF'
import { Hono } from 'hono'
import { admin } from './admin/routes'
import { requireScope } from './auth'

export const app = new Hono()
app.get('/health', c => c.text('ok'))
app.use('/admin/*', requireScope('admin'))
app.route('/admin', admin)
EOF
cat > src/db.ts <<'EOF'
import Database from 'better-sqlite3'
import { readdirSync, readFileSync } from 'node:fs'

export const db = new Database(process.env.DB_PATH ?? 'acme.db')

/** Applies migrations/*.sql in name order, each once. */
export function migrate(): void {
  db.exec('CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY)')
  const done = new Set(db.prepare('SELECT name FROM migrations').pluck().all() as string[])
  for (const name of readdirSync('migrations').sort()) {
    if (done.has(name)) continue
    db.transaction(() => {
      db.exec(readFileSync(`migrations/${name}`, 'utf8'))
      db.prepare('INSERT INTO migrations (name) VALUES (?)').run(name)
    })()
  }
}
EOF
cat > src/auth.ts <<'EOF'
import type { MiddlewareHandler } from 'hono'
import { db } from './db'

export type Principal = { userId: string; scopes: string[] }

/** Rejects a request whose bearer token lacks `scope`; sets c.var.principal. */
export function requireScope(scope: string): MiddlewareHandler {
  return async (c, next) => {
    const token = c.req.header('authorization')?.replace(/^Bearer /, '')
    const row = token && db.prepare('SELECT user_id, scopes FROM tokens WHERE token = ?').get(token) as
      { user_id: string; scopes: string } | undefined
    if (!row || !row.scopes.split(' ').includes(scope)) return c.json({ error: 'forbidden' }, 403)
    c.set('principal', { userId: row.user_id, scopes: row.scopes.split(' ') } satisfies Principal)
    await next()
  }
}
EOF
cat > src/admin/routes.ts <<'EOF'
import { Hono } from 'hono'
import { db } from '../db'

export const admin = new Hono()

admin.post('/users/:id/suspend', c => {
  db.transaction(() => {
    db.prepare('UPDATE users SET suspended_at = unixepoch() WHERE id = ?').run(c.req.param('id'))
  })()
  return c.body(null, 204)
})

admin.delete('/projects/:id', c => {
  db.transaction(() => {
    db.prepare('DELETE FROM projects WHERE id = ?').run(c.req.param('id'))
  })()
  return c.body(null, 204)
})
EOF
cat > src/jobs/nightly.ts <<'EOF'
import { db } from '../db'

/** Runs once a night from the scheduler: drops expired tokens. */
export function nightly(): void {
  db.prepare('DELETE FROM tokens WHERE expires_at < unixepoch()').run()
}
EOF
cat > migrations/001_users.sql <<'EOF'
CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, suspended_at INTEGER);
CREATE TABLE tokens (token TEXT PRIMARY KEY, user_id TEXT NOT NULL, scopes TEXT NOT NULL, expires_at INTEGER NOT NULL);
EOF
cat > migrations/002_projects.sql <<'EOF'
CREATE TABLE projects (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users (id), name TEXT NOT NULL);
EOF
cat > test/admin.test.ts <<'EOF'
import { describe, expect, it } from 'vitest'
import { app } from '../src/server'

describe('admin', () => {
  it('refuses a token without the admin scope', async () => {
    const res = await app.request('/admin/projects/p1', { method: 'DELETE' })
    expect(res.status).toBe(403)
  })
})
EOF
cat > .flow.md <<'EOF'
verify: npm run typecheck && npm test
artifacts-dir: docs/tasks
worktrees: ../acme-api-<slug>
EOF

task() { # folder slug title ticket phase branch updated
  local d="docs/tasks/$1"
  mkdir -p "$d"
  cat > "$d/workflow.md" <<EOF
---
task: $2
title: $3
ticket: https://linear.app/acme/issue/$4
ticket-id: $4
tracker-synced:
mode: full
phase: $5
branch: $6
worktree:
created: 2026-10-08
updated: $7
---
EOF
}

# --- csv-export: done and merged -------------------------------------------
task 2026-10-01-csv-export csv-export "CSV export for the reports page" ENG-118 complete main 2026-10-06
cat >> docs/tasks/2026-10-01-csv-export/workflow.md <<'EOF'

## Next action
Done.

## Decision log
- 2026-10-02 gate 1: plan approved by user
- 2026-10-06 gate 2: merge approved by user

## Progress
- [x] Task 1: stream rows (11aa22)
- [x] Task 2: download button (33bb44)

## Deviations
EOF
git add -A
git commit -q -m "Initial commit"

# --- audit-log: its own worktree, waiting only on gate 1 --------------------
git worktree add -q -b flow/audit-log "$wt"
(
  cd "$wt"
  t=docs/tasks/2026-10-11-audit-log
  task 2026-10-11-audit-log audit-log "Audit log for admin actions" ENG-151 plan-review flow/audit-log 2026-10-13
  cat >> $t/workflow.md <<'EOF'

## Next action
Gate 1 — the critic passed the plan (no blocking findings); waiting on your
approval of plan.md.

## Decision log
- 2026-10-11 Q: keep entries for how long? A: 400 days
- 2026-10-12 Q: log reads as well as changes? A: changes only
- 2026-10-13 plan critic: no blocking findings; advisory "index created_at for the purge" taken into task 1

## Progress

## Deviations
EOF
  cat > $t/research.md <<'EOF'
# Research — audit log for admin actions

## Findings
- Admin routes live in `src/admin/routes.ts:6-19`; each mutation already runs
  inside `db.transaction(...)`, so an entry can be written atomically with it.
- `requireScope('admin')` (`src/auth.ts:7`) sets `c.var.principal`, which
  carries the acting user's id — the "who" for each entry.
- Migrations are plain SQL applied in name order by `migrate()` (`src/db.ts:7`);
  the next file is `003_*.sql`.
- Nightly work runs from `src/jobs/nightly.ts`; a purge fits there.
- Tests use Hono's `app.request` (`test/admin.test.ts`).

## Constraints & prior art
- SQLite: no partitioning, so the purge is a `DELETE ... WHERE created_at < ?`
  — needs an index on `created_at`.

## Open questions
- Retention (answered: 400 days); reads vs changes (answered: changes only).
EOF
  cat > $t/plan.md <<'EOF'
# Plan — Audit log for admin actions

## Intent
Record who changed what through the admin API, so support can answer "who
suspended this account?" without reading server logs.

## Acceptance criteria
- [ ] Each admin mutation writes one `audit_log` row in the same transaction (a failed mutation writes none) — test
- [ ] `GET /admin/audit` returns entries newest first, 50 a page, with a cursor — test
- [ ] Entries older than 400 days are gone after the nightly job — test
- [ ] Non-admin tokens get 403 from `/admin/audit` — test

## Approach
An `audit(c, action, target)` helper called inside each mutation's existing
transaction. Alternatives: a Hono middleware (can't see the transaction, so a
failed write could still log); SQLite triggers (no access to the acting user).

## Assumptions & open questions
- [answered 2026-10-11] entries are kept 400 days, then purged nightly
- [answered 2026-10-12] only state-changing requests are logged, not reads
- [assumed] the actor is `c.var.principal.userId` — set by requireScope, `src/auth.ts:14`
- [assumed] cursor paging on (created_at, id), like other list endpoints would — no list endpoint exists yet to copy

## Tasks
1. Migration `audit_log` (id, actor_id, action, target, created_at + index) — files: migrations/003_audit_log.sql — verify: `npm test` (migrate runs in setup)
2. `audit()` helper; call it in both mutations — files: src/admin/audit.ts, src/admin/routes.ts — verify: test/audit.test.ts
3. `GET /admin/audit` with cursor paging — files: src/admin/routes.ts — verify: test/audit.test.ts
4. Purge in the nightly job — files: src/jobs/nightly.ts — verify: test/nightly.test.ts

## Out of scope
- Logging reads; an admin UI for the log; exporting it.

## Verification
- Machine: `npm run typecheck && npm test`
- Outcome: suspend a user through the API, then `GET /admin/audit` shows the entry with your user id
EOF
  git add -A
  git commit -q -m "flow: audit-log researched and planned"
)

# --- rate-limits: this checkout, mid-implementation -------------------------
git switch -q -c flow/rate-limits
task 2026-10-08-rate-limits rate-limits "Per-user rate limits on the public API" ENG-142 implementation flow/rate-limits 2026-10-12
cat >> docs/tasks/2026-10-08-rate-limits/workflow.md <<'EOF'

## Next action
Task 4 — wrap the client in the retry helper, then tick it.

## Decision log
- 2026-10-08 Q: per-user or per-team limits? A: per-user
- 2026-10-09 gate 1: plan approved by user

## Progress
- [x] Task 1: token bucket (a1b2c3)
- [x] Task 2: middleware (d4e5f6)
- [x] Task 3: config surface (0a9b8c)
- [ ] Task 4: retry helper
- [ ] Task 5: docs
- [ ] Task 6: load test
- [ ] Task 7: dashboard

## Deviations
- 2026-10-12 used a sliding window, not a fixed one — bursts at the boundary
EOF
cat > docs/tasks/2026-10-08-rate-limits/plan.md <<'EOF'
# Plan — Per-user rate limits on the public API

## Intent
Stop one user's burst from degrading the API for everyone.

## Approach
A token bucket per user, enforced in middleware ahead of every public route;
limits come from config, with a per-plan override.

## Assumptions & open questions
- [answered 2026-10-08] limits are per user, not per team
- [assumed] a 429 carries `Retry-After`, and clients are expected to honour it

## Tasks
1. Token bucket
2. Middleware
3. Config surface
4. Retry helper for the internal client
5. Docs
6. Load test
7. Dashboard
EOF
git add -A
git commit -q -m "flow: rate-limits, tasks 1-3"
echo "$repo"
