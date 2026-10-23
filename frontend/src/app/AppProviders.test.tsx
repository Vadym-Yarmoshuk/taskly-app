import { QueryClient, useQueryClient } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { useTheme } from 'styled-components'
import { expect, it, vi } from 'vitest'
import { queryClient } from '../lib/queryClient'
import { AppProviders } from './AppProviders'

vi.mock('../design-system', () => ({
  GlobalStyles: () => <div data-testid="global-styles" />,
  theme: { name: 'test-theme' },
}))

let seenClient: QueryClient | undefined

function Probe() {
  seenClient = useQueryClient()
  const theme = useTheme() as { name?: string }
  return <p>Theme: {theme.name}</p>
}

it('provides the shared query client, the theme and global styles by default', () => {
  render(
    <AppProviders>
      <Probe />
    </AppProviders>,
  )
  expect(seenClient).toBe(queryClient)
  expect(screen.getByText('Theme: test-theme')).toBeVisible()
  expect(screen.getByTestId('global-styles')).toBeInTheDocument()
})

it('provides a custom query client when one is passed', () => {
  const client = new QueryClient()
  render(
    <AppProviders client={client}>
      <Probe />
    </AppProviders>,
  )
  expect(seenClient).toBe(client)
})
