// Applies every migration, rolls them all back, then re-applies them, using an
// in-process PGlite (WASM Postgres). Catches broken up/down SQL without needing a server.
import { PGlite } from '@electric-sql/pglite'
import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'

const dir = path.join(import.meta.dirname, 'migrations')
const files = (await readdir(dir)).filter((f) => f.endsWith('.sql')).sort()

const migrations = []
for (const file of files) {
  const sql = await readFile(path.join(dir, file), 'utf8')
  const [, rest] = sql.split('-- migrate:up')
  if (rest === undefined) throw new Error(`${file}: missing "-- migrate:up"`)
  const [up, down] = rest.split('-- migrate:down')
  if (down === undefined) throw new Error(`${file}: missing "-- migrate:down"`)
  migrations.push({ file, up, down })
}

const db = new PGlite()
for (const m of migrations) await db.exec(m.up)
for (const m of [...migrations].reverse()) await db.exec(m.down)

const leftover = await db.query(
  `select table_name from information_schema.tables where table_schema = 'public'`,
)
if (leftover.rows.length) {
  throw new Error(`rollback left objects behind: ${leftover.rows.map((r) => r.table_name).join(', ')}`)
}

for (const m of migrations) await db.exec(m.up)
const { rows } = await db.query(
  `select count(*)::int as n from information_schema.tables where table_schema = 'public'`,
)
console.log(
  `OK: ${migrations.length} migration(s) apply, roll back cleanly and re-apply (${rows[0].n} tables/views).`,
)
await db.close()
