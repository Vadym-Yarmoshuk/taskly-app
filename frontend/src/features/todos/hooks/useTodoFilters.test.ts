import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import type { Todo } from '../types'
import { useTodoFilters } from './useTodoFilters'

const active: Todo = {
  ...todoFixture,
  id: 1,
  title: 'Active task',
  priority: 'high',
  created_at: '2026-10-01T10:00:00Z',
}
const completed: Todo = {
  ...todoFixture,
  id: 2,
  title: 'Completed task',
  priority: 'low',
  completed: true,
  created_at: '2026-10-01T12:00:00Z',
}
const todos = [active, completed]

describe('useTodoFilters', () => {
  it('starts with all tasks, newest first', () => {
    const { result } = renderHook(() => useTodoFilters(todos))
    expect(result.current.filter).toBe('all')
    expect(result.current.search).toBe('')
    expect(result.current.sort).toBe('newest')
    expect(result.current.visible).toEqual([completed, active])
  })

  it('filters visible tasks by status', () => {
    const { result } = renderHook(() => useTodoFilters(todos))
    act(() => result.current.setFilter('active'))
    expect(result.current.visible).toEqual([active])
    act(() => result.current.setFilter('completed'))
    expect(result.current.visible).toEqual([completed])
  })

  it('filters visible tasks by search text', () => {
    const { result } = renderHook(() => useTodoFilters(todos))
    act(() => result.current.setSearch('active'))
    expect(result.current.search).toBe('active')
    expect(result.current.visible).toEqual([active])
  })

  it('reorders visible tasks when the sort changes', () => {
    const { result } = renderHook(() => useTodoFilters(todos))
    act(() => result.current.setSort('priority'))
    expect(result.current.sort).toBe('priority')
    expect(result.current.visible).toEqual([active, completed])
  })

  it('recomputes visible tasks when the input list changes', () => {
    const { result, rerender } = renderHook(
      ({ list }) => useTodoFilters(list),
      {
        initialProps: { list: [active] },
      },
    )
    expect(result.current.visible).toEqual([active])
    rerender({ list: todos })
    expect(result.current.visible).toEqual([completed, active])
  })
})
