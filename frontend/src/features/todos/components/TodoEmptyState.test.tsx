import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { TodoEmptyState } from './TodoEmptyState'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))

it('shows the empty state for no matching tasks when todos exist', () => {
  render(<TodoEmptyState hasTodos={true} disabled={false} onCreate={vi.fn()} />)
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(
    'No matching tasks',
  )
  expect(
    screen.getByText('Change the status filter or search to find your tasks.'),
  ).toBeVisible()
  expect(
    screen.queryByRole('button', { name: 'Add your first task' }),
  ).not.toBeInTheDocument()
})

it('shows the empty state for no tasks at all and allows creating one', async () => {
  const user = userEvent.setup()
  const onCreate = vi.fn()
  render(
    <TodoEmptyState hasTodos={false} disabled={false} onCreate={onCreate} />,
  )
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(
    'Add your first task',
  )
  expect(
    screen.getByText('Write down what you need to do and get started.'),
  ).toBeVisible()

  const button = screen.getByRole('button', { name: 'Add your first task' })
  await user.click(button)
  expect(onCreate).toHaveBeenCalledTimes(1)
})

it('disables the create button when the disabled prop is true', () => {
  render(<TodoEmptyState hasTodos={false} disabled={true} onCreate={vi.fn()} />)
  expect(
    screen.getByRole('button', { name: 'Add your first task' }),
  ).toBeDisabled()
})
