import { vi } from 'vitest'

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
}

export const pending = () => new Promise<never>(() => {})

export function resetApi() {
  for (const mock of Object.values(api)) mock.mockReset()
  api.getHealth.mockResolvedValue({ status: 'ok', service: 'opspilot-api', database: 'ok' })
}
