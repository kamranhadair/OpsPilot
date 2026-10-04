/**
 * The canonical OpsPilot demo story end to end, offline (Spec 15).
 * Model calls go to the local OpenAI stub; nothing reaches a paid API.
 */

import { expect, test } from '@playwright/test'

import { API_URL } from '../playwright.config'

interface RunAnomaly {
  evidence_id: string
  metric_key: string
  dimensions: Record<string, string>
  severity: string
}

interface RunBody {
  anomalies: RunAnomaly[]
  brief: { state: string; brief_id: number | null; status: string | null }
}

test('canonical demo: analysis -> grounded brief -> human approval -> mock investigation', async ({
  page,
  request,
}) => {
  // 1-2. Freshly reset dataset: the dashboard is in the pre-analysis state.
  await page.goto('/')
  await expect(page.getByText('No metrics computed yet')).toBeVisible()

  // 3. Run the analysis for the final window from the demo control.
  const runResponse = page.waitForResponse(
    (r) => r.url().endsWith('/api/demo/analysis/run') && r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Run analysis' }).click()
  const run = (await (await runResponse).json()) as RunBody
  const result = page.getByRole('status', { name: 'Analysis result' })
  await expect(result).toBeVisible()
  await expect(page.getByRole('region', { name: 'Ticket volume', exact: true })).toBeVisible()

  // 4. The planted Billing ticket-volume anomaly is high severity.
  const billing = run.anomalies.find(
    (a) => a.metric_key === 'ticket_volume' && a.dimensions.category === 'billing',
  )
  expect(billing?.severity).toBe('high')
  expect(run.brief).toMatchObject({ state: 'generated', status: 'valid' })

  // 5. Drill down: EMEA Enterprise is the top contributor.
  await page.goto(`/anomalies/${billing!.evidence_id}`)
  await expect(page.getByText(/EMEA \/ Enterprise/).first()).toBeVisible()

  // 6. The brief is validated and every claim carries citations.
  await page.goto(`/briefs/${run.brief.brief_id}`)
  await expect(page.getByText(/Validated against evidence/)).toBeVisible()
  const claims = page.getByRole('region', { name: 'Claims' })
  await expect(claims.getByRole('button', { name: /^Show evidence / }).first()).toBeVisible()

  // 7. A citation opens its provenance.
  const segment = claims.getByRole('button', { name: /^Show evidence SEG-/ }).first()
  await segment.click()
  const drawer = page.getByRole('dialog')
  await expect(drawer).toBeVisible()
  await expect(drawer.getByText(/EMEA \/ Enterprise/).first()).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()

  // 8. The deployment is described as temporal proximity, never cause.
  await expect(claims.getByText(/coincided with the increase/)).toBeVisible()
  await expect(claims.getByText(/caused by|due to|led to|because of/i)).toHaveCount(0)

  // 9. Propose an open_investigation; it waits for a human.
  await page.getByRole('button', { name: 'Propose investigation' }).click()
  await expect(page).toHaveURL(/\/actions\/\d+$/)
  const actionId = Number(page.url().split('/').pop())
  await expect(page.getByRole('heading', { name: 'Human review' })).toBeVisible()
  const create = page.getByRole('button', { name: 'Create investigation', exact: true })
  await expect(create).toHaveCount(0)

  // 10. Execute-before-approval is rejected by the backend, not just hidden in the UI.
  const early = await request.post(`${API_URL}/api/actions/${actionId}/execute`)
  expect(early.status()).toBe(409)
  expect((await early.json()).code).toBe('ACTION_INVALID_TRANSITION')

  // 11. The human edits the title and approves.
  const title = page.getByLabel('Title')
  await title.fill('Investigate EMEA Enterprise Billing volume after deployment window')
  await page.getByLabel('Comment (optional)').fill('Reviewed in the demo.')
  await page.getByRole('button', { name: 'Approve', exact: true }).click()
  await expect(create).toBeVisible()

  // 12. Mock execution yields exactly one INV-* reference, and replaying is idempotent.
  await create.click()
  await expect(page.getByText('Mock investigation created')).toBeVisible()
  await expect(page.getByText(/^INV-/)).toHaveCount(1)
  const replay = await request.post(`${API_URL}/api/actions/${actionId}/execute`)
  const detail = await (await request.get(`${API_URL}/api/actions/${actionId}`)).json()
  expect(replay.ok()).toBe(true)
  expect(detail.execution.external_ref).toMatch(/^INV-/)
  expect((await replay.json()).execution.external_ref).toBe(detail.execution.external_ref)

  // 13. Evaluation and system/LLM trace pages are usable.
  await page.getByRole('link', { name: 'Evaluations' }).click()
  await expect(page.getByRole('heading', { level: 2 }).first()).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)

  await page.getByRole('link', { name: 'System' }).click()
  await expect(page.getByText('e2e-stub').first()).toBeVisible()
  await expect(page.getByText(/brief generation/i).first()).toBeVisible()
})
