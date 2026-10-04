/**
 * Playwright config for the offline canonical demo flow (Spec 15).
 *
 * Starts three isolated servers on non-default ports so a running dev stack is never
 * reused: the OpenAI stub (8765), the backend against E2E_DATABASE_URL (8001) and Vite
 * (5174). No real API key is ever used; the backend reaches the stub via OPENAI_BASE_URL.
 */

import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig, devices } from '@playwright/test'

const here = path.dirname(fileURLToPath(import.meta.url))
const backendDir = path.resolve(here, '../backend')
const python = path.join(backendDir, '.venv/bin/python')

export const E2E_DATABASE_URL =
  process.env.E2E_DATABASE_URL ??
  'postgresql+psycopg://opspilot:opspilot_local_dev@localhost:5432/opspilot_e2e'
export const EVAL_REPORTS_DIR = path.resolve(here, '.e2e/eval-reports')

const API_PORT = 8001
const WEB_PORT = 5174
const STUB_PORT = 8765

export const API_URL = `http://localhost:${API_PORT}`

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `${python} -m tests.e2e.openai_stub --port ${STUB_PORT}`,
      cwd: backendDir,
      url: `http://127.0.0.1:${STUB_PORT}/health`,
      reuseExistingServer: false,
    },
    {
      command: `${python} -m uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: backendDir,
      // Not /api/health: that probes the database, which global setup may not have created yet.
      url: `http://127.0.0.1:${API_PORT}/openapi.json`,
      reuseExistingServer: false,
      env: {
        ENVIRONMENT: 'test',
        DATABASE_URL: E2E_DATABASE_URL,
        OPENAI_API_KEY: 'e2e-dummy-not-a-key',
        OPENAI_MODEL: 'e2e-stub',
        OPENAI_BASE_URL: `http://127.0.0.1:${STUB_PORT}/v1`,
        OPENAI_MAX_RETRIES: '0',
        EVAL_MODEL_ENABLED: 'false',
        EVAL_REPORTS_DIR,
        CORS_ORIGINS: `http://localhost:${WEB_PORT}`,
        LOG_LEVEL: 'WARNING',
      },
    },
    {
      command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
      cwd: here,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      env: { VITE_API_BASE_URL: API_URL },
    },
  ],
})
