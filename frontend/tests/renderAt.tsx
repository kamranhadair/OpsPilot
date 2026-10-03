import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AppRoutes } from '../src/App'

/** Render the routed application at a path, as the browser would. */
export function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}
