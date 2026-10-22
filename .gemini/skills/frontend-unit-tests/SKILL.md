---
name: frontend-unit-tests
description: Conventions for writing Vitest and React Testing Library unit tests for the Taskly React frontend (frontend/src). Use before creating or editing any *.test.ts or *.test.tsx file.
---

# Frontend unit tests (Vitest + React Testing Library)

## Layout

- Test file sits next to the source: `Foo.tsx` → `Foo.test.tsx`,
  `foo.ts` → `foo.test.ts`.
- Import test APIs explicitly: `import { describe, expect, it, vi } from 'vitest'`.
- `src/test/setup.ts` already loads `@testing-library/jest-dom/vitest` and
  runs `cleanup` after each test.
- Use `todoFixture` from `src/test/todoFixture.ts` for a default task.

## Mocking

- Design system: always mock it in component tests, with the async factory:
  `vi.mock('../../../design-system', () => import('../../../design-system/mocks'))`
  (adjust the relative path).
- HTTP: mock `lib/http` (`vi.mock('../../../lib/http', () => ({ request: vi.fn() }))`)
  or the `todosApi` object; never call `fetch` for real. To test
  `lib/http.ts` itself, stub `fetch` with `vi.stubGlobal('fetch', vi.fn())`
  and restore it with `vi.unstubAllGlobals()` in `afterEach`.
- Child components may be replaced with simple stubs (see `TodoList.test.tsx`).
- Call `vi.clearAllMocks()` in `beforeEach` when mocks are shared.

## Hooks with React Query

Render the hook with a fresh client per test:

```tsx
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper }
}
```

Use `renderHook(() => useX(), { wrapper })`, then `act` / `waitFor`. Assert
the cache with `client.getQueryData(todoKeys.list)`. A hook test that needs
JSX must use the `.test.tsx` extension.

Checklist for React Query hooks:

- Query hook: mock `todosApi`, assert the data and that the abort `signal`
  is passed.
- Mutation hook: mock the `todosApi` method, seed the cache with
  `client.setQueryData(todoKeys.list, [...])`, call `mutateAsync`, then
  assert the API call and the new cache content. Also cover the empty cache.
- Pending state (`useIsMutating`): start a mutation whose promise you control
  (`new Promise(resolve => { release = resolve })`) with
  `client.getMutationCache().build(client, { mutationKey, mutationFn }).execute(undefined)`
  inside `act`, assert `true` inside `waitFor`, then
  `await act(async () => { release(); await done })` and assert `false`.

Import types with `import type { ReactNode } from 'react'`.

## Components

- Query by role and accessible name (`getByRole('button', { name: ... })`),
  then by label or text. Avoid test IDs and class names.
- Use `userEvent.setup()` and `await user.click(...)`.
- Assert callbacks with `toHaveBeenCalledTimes` / `toHaveBeenCalledWith`.

## Time

Use `vi.useFakeTimers()` and `vi.setSystemTime(...)` for code that depends on
the current date or timers; call `vi.useRealTimers()` in `afterEach`.

## Style

- Top-level `it(...)` for a single subject; `describe` only to group several
  functions in one file.
- Test names are sentences in present tense: `it('removes the deleted task from the cache')`.
- Prettier style: single quotes, no semicolons, trailing commas.
