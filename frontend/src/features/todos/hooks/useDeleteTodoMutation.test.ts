import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { useDeleteTodoMutation } from './useDeleteTodoMutation'
import { todoFixture } from '../../../test/todoFixture'

vi.mock('../api/todos', () => ({
  todosApi: {
    remove: vi.fn(),
  },
}))

function setup() {
  const client = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
    },
  })
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children)
  return { client, wrapper }
}

describe('useDeleteTodoMutation', () => {
  it('removes only the deleted todo from the list cache and invalidates stats', async () => {
    vi.mocked(todosApi.remove).mockResolvedValue(undefined)
    const { client, wrapper } = setup()
    const invalidateQueries = vi.spyOn(client, 'invalidateQueries')

    const other = { ...todoFixture, id: 8 }
    client.setQueryData(todoKeys.list, [todoFixture, other])

    const { result } = renderHook(() => useDeleteTodoMutation(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(todoFixture.id)
    })

    expect(todosApi.remove).toHaveBeenCalledWith(todoFixture.id)
    expect(client.getQueryData(todoKeys.list)).toEqual([other])
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: todoKeys.stats })
  })
})
