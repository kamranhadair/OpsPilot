import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, approveAction, executeAction, rejectAction } from './client'

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
