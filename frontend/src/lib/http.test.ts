import { afterEach, describe, expect, it, vi } from 'vitest'
import { request } from './http'

describe('request', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('prepends /api to the path and sets default headers', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: 'ok' }),
    })
    vi.stubGlobal('fetch', fetchSpy)

    const result = await request('/test')

    expect(fetchSpy).toHaveBeenCalledWith('/api/test', {
      headers: { 'Content-Type': 'application/json' },
    })
    expect(result).toEqual({ data: 'ok' })
  })

  it('merges custom headers', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    })
    vi.stubGlobal('fetch', fetchSpy)

    await request('/test', { headers: { 'X-Test': 'value' } })

    expect(fetchSpy).toHaveBeenCalledWith('/api/test', {
      headers: {
        'Content-Type': 'application/json',
        'X-Test': 'value',
      },
    })
  })

  it('returns undefined for 204 No Content', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
      }),
    )

    const result = await request('/test')
    expect(result).toBeUndefined()
  })

  it('throws a connection error on network failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    )

    await expect(request('/test')).rejects.toThrow(
      'Cannot connect to the server. Please try again.',
    )
  })

  it('rethrows the error if the request was aborted', async () => {
    const abortError = new DOMException('Aborted', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError))

    const controller = new AbortController()
    controller.abort()

    await expect(
      request('/test', { signal: controller.signal }),
    ).rejects.toThrow('Aborted')
  })

  it('throws a specific message for 422 Unprocessable Entity', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: () => Promise.resolve({ detail: 'Validation error' }),
      }),
    )

    await expect(request('/test')).rejects.toThrow(
      'Check the task details: title up to 120 characters, description up to 2000 characters, and a valid due date.',
    )
  })

  it('throws the detail message from the response body if available', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ detail: 'Custom error message' }),
      }),
    )

    await expect(request('/test')).rejects.toThrow('Custom error message')
  })

  it('throws a generic message for other errors without detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.resolve({}),
      }),
    )

    await expect(request('/test')).rejects.toThrow(
      'The operation failed. Please try again.',
    )
  })

  it('throws a generic message if the error response is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error('Not JSON')),
      }),
    )

    await expect(request('/test')).rejects.toThrow(
      'The operation failed. Please try again.',
    )
  })
})
