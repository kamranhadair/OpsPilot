import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ApiError,
  approveAction,
  executeAction,
  getDemoStatus,
  getLatestEvaluation,
  getSystemHealth,
  getSystemSummary,
  listLlmTraces,
  rejectAction,
  runDemoAnalysis,
} from './client'

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('action transition client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('posts an approval as JSON and keeps the Accept header', async () => {
    const fetchMock = stubFetch(200, { id: 5 })
    await approveAction(5, { reviewer: 'Operations Manager', edits: { title: 'New' } })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/actions\/5\/approve$/)
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({
      Accept: 'application/json',
      'Content-Type': 'application/json',
    })
    expect(JSON.parse(init.body as string)).toEqual({
      reviewer: 'Operations Manager',
      edits: { title: 'New' },
    })
  })

  it('posts a rejection to its own endpoint', async () => {
    const fetchMock = stubFetch(200, { id: 5 })
    await rejectAction(5, { reviewer: 'Operations Manager', comment: 'No' })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/actions\/5\/reject$/)
    expect(JSON.parse(init.body as string)).toEqual({ reviewer: 'Operations Manager', comment: 'No' })
  })

  it('executes with no body and surfaces typed error fields', async () => {
    const fetchMock = stubFetch(409, {
      code: 'APPROVAL_REQUIRED',
      message: 'Approve the action before executing it.',
    })
    const error = await executeAction(5).catch((e: unknown) => e)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/actions\/5\/execute$/)
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()
    expect(init.headers).toEqual({ Accept: 'application/json' })
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(409)
    expect((error as ApiError).code).toBe('APPROVAL_REQUIRED')
  })
})

describe('evaluation client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('reads the latest report', async () => {
    const fetchMock = stubFetch(200, { state: 'not_run', report: null, message: 'none' })
    const result = await getLatestEvaluation()
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/evaluations\/latest$/)
    expect(result.state).toBe('not_run')
  })

  it('surfaces EVAL_REPORT_INVALID as a typed error', async () => {
    stubFetch(500, { code: 'EVAL_REPORT_INVALID', message: 'Stored report is invalid.' })
    const error = await getLatestEvaluation().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(500)
    expect((error as ApiError).code).toBe('EVAL_REPORT_INVALID')
  })
})

describe('system client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('reads detailed system health', async () => {
    const fetchMock = stubFetch(200, { status: 'ok' })
    await getSystemHealth()
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/system\/health$/)
  })

  it('keeps the health body on 503 DATABASE_UNAVAILABLE', async () => {
    stubFetch(503, {
      code: 'DATABASE_UNAVAILABLE',
      message: 'Database is unreachable.',
      health: { status: 'error', database: { status: 'error', migration_revision: null } },
    })
    const error = await getSystemHealth().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(503)
    expect((error as ApiError).code).toBe('DATABASE_UNAVAILABLE')
    expect((error as ApiError).body?.health?.status).toBe('error')
  })

  it('builds the trace list query and omits undefined params', async () => {
    const fetchMock = stubFetch(200, { items: [], total: 0, limit: 25, offset: 25 })
    await listLlmTraces({ limit: 25, offset: 25, status: 'error', operation: undefined })
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/system\/llm-traces\?limit=25&offset=25&status=error$/)
  })

  it('lists traces with no query string by default', async () => {
    const fetchMock = stubFetch(200, { items: [], total: 0, limit: 25, offset: 0 })
    await listLlmTraces()
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/system\/llm-traces$/)
  })

  it('requests the summary for a period, defaulting to 7d', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })))
    vi.stubGlobal('fetch', fetchMock)
    await getSystemSummary()
    await getSystemSummary('24h')
    expect((fetchMock.mock.calls[0] as [string])[0]).toMatch(/\/api\/system\/summary\?period=7d$/)
    expect((fetchMock.mock.calls[1] as [string])[0]).toMatch(/\/api\/system\/summary\?period=24h$/)
  })

  it('surfaces SYSTEM_ENDPOINTS_DISABLED as a typed 404', async () => {
    stubFetch(404, { code: 'SYSTEM_ENDPOINTS_DISABLED', message: 'Disabled.' })
    const error = await getSystemSummary().catch((e: unknown) => e)
    expect((error as ApiError).status).toBe(404)
    expect((error as ApiError).code).toBe('SYSTEM_ENDPOINTS_DISABLED')
  })
})

describe('demo client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('reads demo status with a GET', async () => {
    const fetchMock = stubFetch(200, { enabled: true })
    await getDemoStatus()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/demo\/status$/)
    expect(init.method).toBeUndefined()
  })

  it('posts the analysis run and surfaces DEMO_DISABLED', async () => {
    const fetchMock = stubFetch(404, {
      code: 'DEMO_DISABLED',
      message: 'Demo endpoints are disabled outside demo environments.',
    })
    const error = await runDemoAnalysis().catch((e: unknown) => e)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/demo\/analysis\/run$/)
    expect(init.method).toBe('POST')
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('DEMO_DISABLED')
  })
})
