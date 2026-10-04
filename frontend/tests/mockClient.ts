import { vi } from 'vitest'

import { llmTraceList, systemHealth, systemSummary } from './fixtures/api'

/** Every network call is replaced; each test sets the responses it needs. */
vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client')
  return {
    ...actual,
    getHealth: vi.fn(),
    getDashboardOverview: vi.fn(),
    listAnomalies: vi.fn(),
    getAnomaly: vi.fn(),
    getContributors: vi.fn(),
    computeContributors: vi.fn(),
    getBrief: vi.fn(),
    getLatestBrief: vi.fn(),
    getEvidence: vi.fn(),
    listActions: vi.fn(),
    getAction: vi.fn(),
    proposeAction: vi.fn(),
    approveAction: vi.fn(),
    rejectAction: vi.fn(),
    executeAction: vi.fn(),
    getLatestEvaluation: vi.fn(),
    getSystemHealth: vi.fn(),
    listLlmTraces: vi.fn(),
    getSystemSummary: vi.fn(),
  }
})

const client = await import('../src/api/client')

export const api = {
  getHealth: vi.mocked(client.getHealth),
  getDashboardOverview: vi.mocked(client.getDashboardOverview),
  listAnomalies: vi.mocked(client.listAnomalies),
  getAnomaly: vi.mocked(client.getAnomaly),
  getContributors: vi.mocked(client.getContributors),
  computeContributors: vi.mocked(client.computeContributors),
  getBrief: vi.mocked(client.getBrief),
  getLatestBrief: vi.mocked(client.getLatestBrief),
  getEvidence: vi.mocked(client.getEvidence),
  listActions: vi.mocked(client.listActions),
  getAction: vi.mocked(client.getAction),
  proposeAction: vi.mocked(client.proposeAction),
  approveAction: vi.mocked(client.approveAction),
  rejectAction: vi.mocked(client.rejectAction),
  executeAction: vi.mocked(client.executeAction),
  getLatestEvaluation: vi.mocked(client.getLatestEvaluation),
  getSystemHealth: vi.mocked(client.getSystemHealth),
  listLlmTraces: vi.mocked(client.listLlmTraces),
  getSystemSummary: vi.mocked(client.getSystemSummary),
}

export const pending = () => new Promise<never>(() => {})

export function resetApi() {
  for (const mock of Object.values(api)) mock.mockReset()
  api.getHealth.mockResolvedValue({ status: 'ok', service: 'opspilot-api', database: 'ok' })
  api.getSystemHealth.mockResolvedValue(systemHealth())
  api.listLlmTraces.mockResolvedValue(llmTraceList())
  api.getSystemSummary.mockResolvedValue(systemSummary())
}
