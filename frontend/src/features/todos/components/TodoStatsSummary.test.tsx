import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { TodoStatsSummary } from './TodoStatsSummary'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))

it('renders nothing when stats are missing', () => {
  const { container } = render(<TodoStatsSummary stats={undefined} />)
  expect(container).toBeEmptyDOMElement()
})

it('renders a empty state message when there are no tasks', () => {
  render(
    <TodoStatsSummary
      stats={{ total: 0, active: 0, completed: 0, overdue: 0 }}
    />,
  )
  expect(screen.getByText('No tasks yet.')).toBeVisible()
})

it('renders active and completed counts', () => {
  render(
    <TodoStatsSummary
      stats={{ total: 5, active: 3, completed: 2, overdue: 0 }}
    />,
  )
  expect(screen.getByText('3 active')).toBeVisible()
  expect(screen.getByText('2 completed')).toBeVisible()
  expect(screen.queryByText(/overdue/)).not.toBeInTheDocument()
})

it('renders overdue count when greater than zero', () => {
  render(
    <TodoStatsSummary
      stats={{ total: 5, active: 3, completed: 2, overdue: 1 }}
    />,
  )
  expect(screen.getByText('1 overdue')).toBeVisible()
})
