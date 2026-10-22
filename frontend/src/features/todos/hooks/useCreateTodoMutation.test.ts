import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { useCreateTodoMutation } from './useCreateTodoMutation'
import { todoFixture } from '../../../test/todoFixture'
import type { Todo } from '../types'

vi.mock('../api/todos', () => ({
  todosApi: {
    create: vi.fn(),
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

describe('useCreateTodoMutation', () => {
  it('creates a todo, prepends it to the list cache, and invalidates stats', async () => {
    const newTodo = { ...todoFixture, id: 8, title: 'New Todo' }
    vi.mocked(todosApi.create).mockResolvedValue(newTodo)
    const { client, wrapper } = setup()
    const invalidateQueries = vi.spyOn(client, 'invalidateQueries')

    const existingTodos: Todo[] = [todoFixture]
    client.setQueryData(todoKeys.list, existingTodos)

    const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        title: 'New Todo',
        description: '',
        priority: 'medium',
        due_date: null,
        completed: false,
      })
    })

    expect(todosApi.create).toHaveBeenCalled()
    expect(client.getQueryData(todoKeys.list)).toEqual([
      newTodo,
      ...existingTodos,
    ])
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: todoKeys.stats })
  })

  it('handles empty cache by creating a new list', async () => {
    const newTodo = { ...todoFixture, id: 8 }
    vi.mocked(todosApi.create).mockResolvedValue(newTodo)
    const { client, wrapper } = setup()

    const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(todoFixture)
    })

    expect(client.getQueryData(todoKeys.list)).toEqual([newTodo])
  })

  it('replaces an existing todo with the same ID in the cache', async () => {
    const savedTodo = { ...todoFixture, title: 'Updated' }
    vi.mocked(todosApi.create).mockResolvedValue(savedTodo)
    const { client, wrapper } = setup()

    client.setQueryData(todoKeys.list, [todoFixture])

    const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(todoFixture)
    })

    expect(client.getQueryData(todoKeys.list)).toEqual([savedTodo])
  })
})
