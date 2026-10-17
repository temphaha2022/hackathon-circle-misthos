import {
  createContext,
  lazy,
  Suspense,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useMe } from '../lib/session'
import { gateStep, githubRefusal, type GateStep } from '../lib/gate'

/**
 * The sign-in gate (#181): the one way into the app.
 *
 * Every way in from the landing page, and the app's own "Sign in", opens the same
 * gate while it is unfinished: a wallet, then a GitHub account, then a side. Closing it
 * costs nothing, and reopening it starts at the first step that is not done. Finishing
 * it closes it and opens the app at its overview.
 *
 * This file is the light part every page loads. The dialog itself signs, which carries
 * the curve arithmetic, so it loads the first time the gate opens.
 */

const GateDialog = lazy(() => import('./GateDialog'))

type Gate = {
  /** Open the gate at the first unfinished step. */
  open: () => void
  /** Where the gate stands; null until the API has said who is signed in. */
  step: GateStep | null
  /** All three steps are done, so the ways in lead straight into the app. */
  finished: boolean
}

const GateContext = createContext<Gate | null>(null)

export function useGate(): Gate {
  const gate = useContext(GateContext)
  if (!gate) throw new Error('useGate needs a GateProvider')
  return gate
}

export function GateProvider({ children }: { children: ReactNode }) {
  const me = useMe()
  const navigate = useNavigate()
  const location = useLocation()
  const step = me.isLoading ? null : gateStep(me.data)
  const [isOpen, setOpen] = useState(false)
  const [refusal, setRefusal] = useState<string | null>(null)
  const opener = useRef<HTMLElement | null>(null)

  const open = useCallback(() => {
    // Focus goes back to whatever opened the gate when it closes.
    const active = document.activeElement
    opener.current = active instanceof HTMLElement ? active : null
    setOpen(true)
  }, [])

  const close = useCallback(() => {
    setOpen(false)
    setRefusal(null)
    const back = opener.current
    opener.current = null
    if (back?.isConnected) requestAnimationFrame(() => back.focus())
  }, [])

  const finish = useCallback(() => {
    setOpen(false)
    setRefusal(null)
    opener.current = null
    navigate('/overview')
  }, [navigate])

  // GitHub's return lands on `/?signin=continue`: the gate opens again where it was,
  // and says why if GitHub's answer was refused.
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    if (params.get('signin') !== 'continue') return
    setRefusal(githubRefusal(params))
    setOpen(true)
    navigate({ pathname: location.pathname, search: '' }, { replace: true })
  }, [location.search, location.pathname, navigate])

  const gate = useMemo(() => ({ open, step, finished: step === 'done' }), [open, step])

  return (
    <GateContext.Provider value={gate}>
      {/* Everything behind the gate is out of reach while it is open. */}
      <div style={{ display: 'contents' }} inert={isOpen}>
        {children}
      </div>
      {isOpen && (
        <Suspense fallback={null}>
          <GateDialog onClose={close} onDone={finish} refusal={refusal} />
        </Suspense>
      )}
    </GateContext.Provider>
  )
}

/**
 * A way into the app. Once the gate is finished it is a plain link; until then a click
 * opens the gate instead of the page, so nobody reaches the app halfway through.
 */
export function GateLink({
  to,
  className,
  style,
  children,
}: {
  to: string
  className?: string
  style?: CSSProperties
  children: ReactNode
}) {
  const gate = useGate()
  if (gate.finished) {
    return (
      <Link to={to} className={className} style={style}>
        {children}
      </Link>
    )
  }
  return (
    <a
      href={to}
      className={className}
      style={style}
      aria-haspopup="dialog"
      onClick={(e) => {
        e.preventDefault()
        gate.open()
      }}
      // A middle click would open the page in a new tab, past the gate.
      onAuxClick={(e) => {
        if (e.button !== 1) return
        e.preventDefault()
        gate.open()
      }}
    >
      {children}
    </a>
  )
}
