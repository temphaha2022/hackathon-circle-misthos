/**
 * The sign-in gate's three steps, read off who is signed in (#181).
 *
 * The gate asks for a wallet, then a GitHub account, then a side. Everything it shows,
 * and everything the profile says is missing, comes from `gateStep`, so there is one
 * answer to "what is left" and the two cannot disagree. A step that is done is never
 * asked again: reopening the gate starts at the first one that is not.
 */

import type { MeOut } from './client'

export type Step = 'wallet' | 'github' | 'side'
export type GateStep = Step | 'done'

export const STEPS: { step: Step; label: string }[] = [
  { step: 'wallet', label: 'Wallet' },
  { step: 'github', label: 'GitHub' },
  { step: 'side', label: 'Side' },
]

/** The GitHub login the wallet linked: on its account, or held until it has one. */
export function linkedLogin(me: MeOut | null | undefined): string | null {
  return me?.account?.github_login ?? me?.pending_github_login ?? null
}

/** The first step that is not done, or `done` once the account has a login and a side. */
export function gateStep(me: MeOut | null | undefined): GateStep {
  if (!me) return 'wallet'
  if (!linkedLogin(me)) return 'github'
  if (!me.account) return 'side'
  return 'done'
}

/** Whether each step is done, for the gate's step list. */
export function stepsDone(me: MeOut | null | undefined): Record<Step, boolean> {
  return {
    wallet: Boolean(me),
    github: Boolean(linkedLogin(me)),
    side: Boolean(me?.account),
  }
}

/** What is still missing, in the words the profile uses for it. */
export function missing(me: MeOut | null | undefined): string | null {
  switch (gateStep(me)) {
    case 'wallet':
      return 'You are not signed in.'
    case 'github':
      return me?.account
        ? 'Your GitHub account is not linked yet.'
        : 'Your GitHub account is not linked yet, and you have not chosen a side.'
    case 'side':
      return 'You have not chosen a side yet.'
    case 'done':
      return null
  }
}

/**
 * Why GitHub's return came back refused. The API sends a reason code rather than the
 * login itself, so nothing about the account travels in the address bar.
 */
export function githubRefusal(params: URLSearchParams): string | null {
  switch (params.get('github')) {
    case 'taken':
      return (
        'That GitHub account is already linked to another wallet, or being linked by one. ' +
        'One GitHub account belongs to one wallet: sign in with that wallet, or link another account.'
      )
    case 'cancelled':
      return 'The link was not approved on GitHub, so nothing was linked. Try again when you are ready.'
    case 'busy':
      return 'That GitHub account was being linked at the same moment. Try again.'
    default:
      return null
  }
}

// ---------------------------------------------------------------- Circle sign-in id

const SIGN_IN_KEY = 'misthos.circle-sign-in'
const SIGN_IN_ID = /^[A-Za-z0-9_-]{16,64}$/

type Store = Pick<Storage, 'getItem' | 'setItem'>

function storage(): Store | null {
  try {
    return globalThis.localStorage ?? null
  } catch {
    return null
  }
}

/**
 * The random id this browser signs in to its Circle wallet with. It names the Circle
 * user and is kept so the same wallet comes back next time; it is not a secret Circle
 * trusts, since nothing is signed without the PIN set in Circle's frame.
 */
export function circleSignInId(
  store: Store | null = storage(),
  random: () => Uint8Array = () => crypto.getRandomValues(new Uint8Array(24)),
): string {
  let kept: string | null = null
  try {
    kept = store?.getItem(SIGN_IN_KEY) ?? null
  } catch {
    // Storage can be blocked; a fresh id for this page still signs in.
  }
  if (kept && SIGN_IN_ID.test(kept)) return kept
  const fresh = Array.from(random(), (b) => b.toString(16).padStart(2, '0')).join('')
  try {
    store?.setItem(SIGN_IN_KEY, fresh)
  } catch {
    // As above.
  }
  return fresh
}
