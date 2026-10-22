import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { useUpdateTodoMutation } from './useUpdateTodoMutation'
import { todoFixture } from '../../../test/todoFixture'

vi.mock('../api/todos', () => ({
  todosApi: {
    update: vi.fn(),
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

describe('useUpdateTodoMutation', () => {
  it('replaces only the updated todo in the list cache', async () => {
    const updatedTodo = { ...todoFixture, title: 'Updated Title' }
    vi.mocked(todosApi.update).mockResolvedValue(updatedTodo)
    const { client, wrapper } = setup()

    const other = { ...todoFixture, id: 8 }
    client.setQueryData(todoKeys.list, [todoFixture, other])

    const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        id: todoFixture.id,
        input: { title: 'Updated Title' },
      })
    })

    expect(todosApi.update).toHaveBeenCalledWith(todoFixture.id, {
      title: 'Updated Title',
    })
    expect(client.getQueryData(todoKeys.list)).toEqual([updatedTodo, other])
  })
})
