/** Resets the isolated e2e database to the pre-analysis demo state before the run. */

import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { E2E_DATABASE_URL, EVAL_REPORTS_DIR } from '../playwright.config'

export default function globalSetup() {
  const backendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../backend')
  execFileSync(path.join(backendDir, '.venv/bin/python'), ['-m', 'tests.e2e.prepare'], {
    cwd: backendDir,
    stdio: 'inherit',
    env: { ...process.env, E2E_DATABASE_URL, EVAL_REPORTS_DIR },
  })
}
