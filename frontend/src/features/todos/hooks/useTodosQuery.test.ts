import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { todosApi } from '../api/todos'
import { useTodosQuery } from './useTodosQuery'
import { todoFixture } from '../../../test/todoFixture'

vi.mock('../api/todos', () => ({
  todosApi: {
    list: vi.fn(),
  },
}))

function setup() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children)
  return { client, wrapper }
}

describe('useTodosQuery', () => {
  it('fetches todos and returns them', async () => {
    const todos = [todoFixture]
    vi.mocked(todosApi.list).mockResolvedValue(todos)
    const { wrapper } = setup()

    const { result } = renderHook(() => useTodosQuery(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(todos)
    expect(todosApi.list).toHaveBeenCalledWith(expect.any(AbortSignal))
  })
})
