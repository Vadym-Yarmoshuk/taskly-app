import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { todoKeys } from '../api/queryKeys'
import { useTodosBusy } from './useTodosBusy'

function setup() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children)
  return { client, wrapper }
}

describe('useTodosBusy', () => {
  it('returns false when no todo mutations are active', () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useTodosBusy(), { wrapper })

    expect(result.current).toBe(false)
  })

  it('returns true while a todo mutation is active and false after completion', async () => {
    const { client, wrapper } = setup()
    const { result } = renderHook(() => useTodosBusy(), { wrapper })

    expect(result.current).toBe(false)

    let release: () => void = () => {}
    const pendingPromise = new Promise<void>((resolve) => {
      release = resolve
    })

    let mutationExecution: Promise<unknown>
    act(() => {
      mutationExecution = client
        .getMutationCache()
        .build(client, {
          mutationKey: todoKeys.create,
          mutationFn: () => pendingPromise,
        })
        .execute(undefined)
    })

    await waitFor(() => {
      expect(result.current).toBe(true)
    })

    act(() => {
      release()
    })
    await act(async () => {
      await mutationExecution
    })

    await waitFor(() => {
      expect(result.current).toBe(false)
    })
  })
})
