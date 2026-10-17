import { describe, expect, it } from 'vitest'
import type { Account, MeOut } from './client'
import { circleSignInId, gateStep, githubRefusal, linkedLogin, missing, stepsDone } from './gate'

const ADDRESS = '0x00000000000000000000000000000000000000a1'

const account = (github_login: string | null = 'ada-dev'): Account => ({
  address: ADDRESS,
  role: 'contributor',
  party_id: 'CON-101',
  github_login,
  created_at: '2026-10-16T00:00:00Z',
})

const signedIn = (changes: Partial<MeOut> = {}): MeOut => ({
  address: ADDRESS,
  account: null,
  pending_github_login: null,
  ...changes,
})

describe('gateStep', () => {
  it('starts at the wallet for nobody signed in', () => {
    expect(gateStep(null)).toBe('wallet')
    expect(gateStep(undefined)).toBe('wallet')
  })

  it('asks for GitHub once a wallet is signed in, before the side', () => {
    expect(gateStep(signedIn())).toBe('github')
  })

  it('asks for the side once a login is held, and never for GitHub again', () => {
    const me = signedIn({ pending_github_login: 'ada-dev' })
    expect(gateStep(me)).toBe('side')
    expect(stepsDone(me)).toEqual({ wallet: true, github: true, side: false })
  })

  it('is done once the account carries the login', () => {
    expect(gateStep(signedIn({ account: account() }))).toBe('done')
  })

  // An account made before the gate, side first and GitHub after: it resumes at GitHub
  // and never asks for the side it already chose.
  it('resumes an older account without a login at GitHub, with its side kept', () => {
    const me = signedIn({ account: account(null) })
    expect(gateStep(me)).toBe('github')
    expect(stepsDone(me)).toEqual({ wallet: true, github: false, side: true })
    expect(missing(me)).toBe('Your GitHub account is not linked yet.')
  })
})

describe('linkedLogin', () => {
  it('is the account’s login, or the one held before the account', () => {
    expect(linkedLogin(signedIn({ account: account('on-account') }))).toBe('on-account')
    expect(linkedLogin(signedIn({ pending_github_login: 'held' }))).toBe('held')
    expect(linkedLogin(signedIn())).toBeNull()
  })
})

describe('missing', () => {
  it('names what the profile is waiting on, and nothing once done', () => {
    expect(missing(null)).toBe('You are not signed in.')
    expect(missing(signedIn({ pending_github_login: 'x' }))).toBe('You have not chosen a side yet.')
    expect(missing(signedIn({ account: account() }))).toBeNull()
  })
})

describe('githubRefusal', () => {
  it('says a login is another wallet’s without the login being in the address', () => {
    expect(githubRefusal(new URLSearchParams('signin=continue&github=taken'))).toMatch(
      /already linked to another wallet/,
    )
    expect(githubRefusal(new URLSearchParams('signin=continue&github=cancelled'))).toMatch(
      /nothing was linked/,
    )
    expect(githubRefusal(new URLSearchParams('signin=continue'))).toBeNull()
  })
})

describe('circleSignInId', () => {
  function memory() {
    const kept = new Map<string, string>()
    return {
      getItem: (k: string) => kept.get(k) ?? null,
      setItem: (k: string, v: string) => void kept.set(k, v),
    }
  }

  it('keeps one random id per browser, so the same Circle wallet comes back', () => {
    const store = memory()
    const first = circleSignInId(store)
    expect(first).toMatch(/^[0-9a-f]{48}$/)
    expect(circleSignInId(store)).toBe(first)
  })

  it('replaces a kept value that is not an id', () => {
    const store = memory()
    store.setItem('misthos.circle-sign-in', '../not an id')
    expect(circleSignInId(store, () => new Uint8Array(24).fill(1))).toBe('01'.repeat(24))
  })

  it('still signs in where storage is blocked', () => {
    const blocked = {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
    }
    expect(circleSignInId(blocked)).toMatch(/^[0-9a-f]{48}$/)
  })
})
