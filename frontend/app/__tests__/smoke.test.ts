import { describe, it, expect } from 'vitest'

describe('smoke', () => {
  it('true is true', () => {
    expect(true).toBe(true)
  })

  it('basic arithmetic works', () => {
    expect(1 + 2).toBe(3)
    expect(2 * 3).toBe(6)
    expect(5 - 2).toBe(3)
    expect(9 / 3).toBe(3)
  })

  it('NODE_ENV is defined (env sanity)', () => {
    // Vitest sets NODE_ENV in most setups; we only check it exists (string) without asserting a specific value.
    expect(typeof process.env.NODE_ENV).toBe('string')
  })
})
