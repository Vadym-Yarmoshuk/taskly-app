import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { expect, it, vi } from 'vitest'
import { todosApi } from '../api/todos'
import { useTodoStats } from './useTodoStats'

vi.mock('../api/todos', () => ({
  todosApi: {
    stats: vi.fn(),
  },
}))

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children)
  return { client, wrapper }
}

it('fetches task statistics and passes the abort signal', async () => {
  const stats = { total: 10, active: 5, completed: 5, overdue: 1 }
  vi.mocked(todosApi.stats).mockResolvedValue(stats)
  const { wrapper } = setup()

  const { result } = renderHook(() => useTodoStats(), { wrapper })

  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data).toEqual(stats)
  expect(todosApi.stats).toHaveBeenCalledWith(expect.any(AbortSignal))
})
