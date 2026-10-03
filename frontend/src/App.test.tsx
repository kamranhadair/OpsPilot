import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { ApiError } from './api/client'

vi.mock('./api/client', async () => {
  const actual = await vi.importActual<typeof import('./api/client')>(
    './api/client',
  )
  return { ...actual, getHealth: vi.fn() }
})

const { getHealth } = await import('./api/client')
const getHealthMock = vi.mocked(getHealth)

describe('App shell', () => {
  beforeEach(() => {
    getHealthMock.mockReset()
  })

  it('renders the OpsPilot shell with placeholder navigation', () => {
    getHealthMock.mockReturnValue(new Promise(() => {}))

    render(<App />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'OpsPilot' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('AI Support Operations Command Center'),
    ).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument()
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Anomalies')).toBeInTheDocument()
  })

  it('shows the loading state while the health check is in flight', () => {
    getHealthMock.mockReturnValue(new Promise(() => {}))

    render(<App />)

    expect(screen.getByRole('status')).toHaveTextContent(
      /checking backend health/i,
    )
  })

  it('shows the success state when the backend and database are healthy', async () => {
    getHealthMock.mockResolvedValue({
      status: 'ok',
      service: 'opspilot-api',
      database: 'ok',
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('opspilot-api')).toBeInTheDocument()
    })
    expect(screen.getByText('Database')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the error state with the backend error code on a 503', async () => {
    getHealthMock.mockRejectedValue(
      new ApiError(
        'Database connectivity check failed.',
        503,
        'DATABASE_UNAVAILABLE',
      ),
    )

    render(<App />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Backend unavailable')
    expect(alert).toHaveTextContent('Database connectivity check failed.')
    expect(alert).toHaveTextContent('DATABASE_UNAVAILABLE')
  })

  it('never fabricates a healthy database when the backend is unreachable', async () => {
    getHealthMock.mockRejectedValue(
      new ApiError('Could not reach the OpsPilot API.', 0, 'NETWORK_UNREACHABLE'),
    )

    render(<App />)

    await screen.findByRole('alert')
    expect(screen.queryByText('opspilot-api')).not.toBeInTheDocument()
    expect(screen.queryByText('ok')).not.toBeInTheDocument()
  })
})
