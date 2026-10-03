import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { api, pending, resetApi } from '../../../tests/mockClient'
import { ApiError } from '../../api/client'
import { HealthPanel } from './HealthPanel'

describe('HealthPanel', () => {
  beforeEach(resetApi)

  it('shows the loading state while the health check is in flight', () => {
    api.getHealth.mockReturnValue(pending())
    render(<HealthPanel />)
    expect(screen.getByRole('status')).toHaveTextContent(/checking backend health/i)
  })

  it('shows the success state when the backend and database are healthy', async () => {
    render(<HealthPanel />)
    await waitFor(() => expect(screen.getByText('opspilot-api')).toBeInTheDocument())
    expect(screen.getByText('Database')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the error state with the backend error code on a 503', async () => {
    api.getHealth.mockRejectedValue(
      new ApiError('Database connectivity check failed.', 503, 'DATABASE_UNAVAILABLE'),
    )
    render(<HealthPanel />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Backend unavailable')
    expect(alert).toHaveTextContent('DATABASE_UNAVAILABLE')
  })

  it('never fabricates a healthy database when the backend is unreachable', async () => {
    api.getHealth.mockRejectedValue(
      new ApiError('Could not reach the OpsPilot API.', 0, 'NETWORK_UNREACHABLE'),
    )
    render(<HealthPanel />)
    await screen.findByRole('alert')
    expect(screen.queryByText('opspilot-api')).not.toBeInTheDocument()
    expect(screen.queryByText('ok')).not.toBeInTheDocument()
  })
})
