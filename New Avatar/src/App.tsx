import { useState } from 'react'
import InterviewerCharacter, { InterviewerCharacterState } from './components/InterviewerCharacter'
import ArabInterviewerCharacter from './components/ArabInterviewerCharacter'

type CharacterVariant = 'western' | 'arab'

const VARIANT_META: Record<CharacterVariant, { label: string; sub: string; color: string }> = {
  western: { label: 'Western', sub: 'Blazer + Tie',             color: '#3D70BE' },
  arab:    { label: 'UAE',     sub: 'Kandura + Guthra + Agal',  color: '#B89040' },
}

// ── State metadata ─────────────────────────────────────────────────

const ALL_STATES: InterviewerCharacterState[] = [
  'idle', 'listening', 'thinking', 'speaking', 'transition', 'hidden',
]

const STATE_META: Record<InterviewerCharacterState, {
  label: string
  color: string
  dot: string
  desc: string
  mapping: string
}> = {
  idle: {
    label:   'Idle',
    color:   '#5A9ADE',
    dot:     '#5A9ADE',
    desc:    'AI interviewer present and ready. Subtle breathing, occasional blink.',
    mapping: 'Background interview idle / between questions',
  },
  listening: {
    label:   'Listening',
    color:   '#4AB8E8',
    dot:     '#4AB8E8',
    desc:    'Candidate is speaking. Character attentively listens — mouth closed, head slightly tilted.',
    mapping: 'Candidate speaking / STT receiving audio',
  },
  thinking: {
    label:   'Thinking',
    color:   '#9B84E8',
    dot:     '#9B84E8',
    desc:    'AI is generating its next response. Thoughtful posture, presence dots active.',
    mapping: 'Groq API / LLM generating response',
  },
  speaking: {
    label:   'Speaking',
    color:   '#38C5A0',
    dot:     '#38C5A0',
    desc:    'AI is speaking. Mouth cycles A→B→C, subtle body sway and arm gesture.',
    mapping: 'TTS audio playing / AI speaking audio',
  },
  transition: {
    label:   'Transition',
    color:   '#F0A840',
    dot:     '#F0A840',
    desc:    'Character exits the interview panel. One-way — cannot return to conversational states.',
    mapping: 'Technical interview phase starting (one-way)',
  },
  hidden: {
    label:   'Hidden',
    color:   '#4A6480',
    dot:     '#4A6480',
    desc:    'Zero visual presence. Technical interview has absolute priority. Component renders null.',
    mapping: 'Any technical question / code submission / eval / completion',
  },
}

// ── Layout constants ───────────────────────────────────────────────

const BG      = '#080E18'
const SURFACE = '#0D1826'
const PANEL   = '#101E30'
const BORDER  = 'rgba(255,255,255,0.06)'
const TEXT    = '#E2EAF4'
const MUTED   = '#7A90A8'
const MONO    = "'JetBrains Mono', monospace"

// ── Small helpers ──────────────────────────────────────────────────

function Badge({ state }: { state: InterviewerCharacterState }) {
  const m = STATE_META[state]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '4px 12px', borderRadius: 20,
      background: `${m.color}18`,
      border: `1px solid ${m.color}38`,
      color: m.color, fontSize: 12, fontWeight: 600,
      letterSpacing: '0.06em', fontFamily: MONO,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%',
        background: m.dot,
        boxShadow: `0 0 6px ${m.dot}`,
        animation: state === 'speaking' ? 'pulse-dot 0.75s ease-in-out infinite alternate' : 'none',
      }} />
      {m.label.toUpperCase()}
    </span>
  )
}

function StateButton({
  s, active, onClick,
}: {
  s: InterviewerCharacterState; active: boolean; onClick: () => void
}) {
  const m = STATE_META[s]
  return (
    <button onClick={onClick} style={{
      padding: '7px 16px', borderRadius: 8, border: `1px solid ${active ? m.color + '80' : BORDER}`,
      background: active ? `${m.color}18` : 'transparent',
      color: active ? m.color : MUTED,
      fontSize: 13, fontWeight: active ? 600 : 400, cursor: 'pointer',
      transition: 'all 180ms ease',
    }}>
      {m.label}
    </button>
  )
}

// ── State library card (small character preview) ───────────────────

function LibraryCard({
  s, active, onClick, CharComponent = InterviewerCharacter,
}: {
  s: InterviewerCharacterState; active: boolean; onClick: () => void
  CharComponent?: React.ComponentType<{ state: InterviewerCharacterState; size: 'small' | 'medium' | 'large' }>
}) {
  const m = STATE_META[s]
  return (
    <button onClick={onClick} style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      gap: 0, padding: '12px 6px 10px', borderRadius: 10,
      border: `1px solid ${active ? m.color + '60' : BORDER}`,
      background: active ? `${m.color}10` : PANEL,
      cursor: 'pointer', transition: 'all 180ms ease', position: 'relative',
    }}>
      <div style={{
        height: 96, display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
        overflow: 'hidden',
      }}>
        {s === 'hidden' ? (
          <div style={{
            width: 48, height: 48, borderRadius: '50%',
            border: `1.5px dashed ${BORDER}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#2A3A52', fontSize: 18,
          }}>∅</div>
        ) : s === 'transition' ? (
          <div style={{
            width: 48, height: 72, borderRadius: 8,
            border: `1.5px dashed ${BORDER}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#2A3A52', fontSize: 12, fontFamily: MONO,
          }}>↑</div>
        ) : (
          <CharComponent state={s} size="small" />
        )}
      </div>
      <span style={{
        fontSize: 10, fontWeight: 600, letterSpacing: '0.07em',
        color: active ? m.color : MUTED, fontFamily: MONO, marginTop: 6,
      }}>
        {m.label.toUpperCase()}
      </span>
    </button>
  )
}

// ── Technical interview panel (no character) ───────────────────────

function TechnicalPanel() {
  return (
    <div style={{
      background: SURFACE, borderRadius: 14,
      border: `1px solid ${BORDER}`,
      padding: '28px 24px', display: 'flex', flexDirection: 'column', gap: 16,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ color: MUTED, fontSize: 11, fontWeight: 600, letterSpacing: '0.07em', fontFamily: MONO }}>
          TECHNICAL INTERVIEW
        </span>
        <span style={{
          padding: '3px 10px', borderRadius: 12,
          background: 'rgba(244, 168, 64, 0.12)', border: '1px solid rgba(244,168,64,0.25)',
          color: '#F0A840', fontSize: 11, fontWeight: 600, fontFamily: MONO,
        }}>
          CHARACTER HIDDEN
        </span>
      </div>
      {/* Code editor mock */}
      <div style={{
        background: '#080E18', borderRadius: 8, padding: 16,
        border: `1px solid ${BORDER}`, fontFamily: MONO, fontSize: 12,
      }}>
        <div style={{ color: '#4A6480', marginBottom: 10, fontSize: 11 }}>
          {'// Question 1 of 3 — Write a function to reverse a linked list'}
        </div>
        <div style={{ color: '#7AB8E8' }}>
          {'function '}<span style={{ color: '#38C5A0' }}>{'reverseList'}</span>
          <span style={{ color: TEXT }}>{'(head) {'}</span>
        </div>
        <div style={{ color: MUTED, paddingLeft: 20 }}>{'let prev = null'}</div>
        <div style={{ color: MUTED, paddingLeft: 20 }}>{'let curr = head'}</div>
        <div style={{ color: TEXT, paddingLeft: 20 }}>{'// ...'}</div>
        <div style={{ color: TEXT }}>{'}'}</div>
      </div>
      <p style={{ color: '#3A5268', fontSize: 12, margin: 0, lineHeight: 1.5 }}>
        The conversational AI interviewer character is not rendered here.
        The <code style={{ color: MUTED, fontFamily: MONO }}>InterviewerCharacter</code> component
        has already received <code style={{ color: MUTED, fontFamily: MONO }}>state="hidden"</code> and returns null.
        Zero DOM nodes. Zero layout impact.
      </p>
    </div>
  )
}

// ── Main app ───────────────────────────────────────────────────────

export default function App() {
  const [activeState, setActiveState] = useState<InterviewerCharacterState>('idle')
  const [presence, setPresence] = useState(true)
  const [showTechnical, setShowTechnical] = useState(false)
  const [variant, setVariant] = useState<CharacterVariant>('western')

  const meta = STATE_META[activeState]

  const ActiveCharacter = variant === 'arab' ? ArabInterviewerCharacter : InterviewerCharacter

  return (
    <div style={{
      minHeight: '100vh', background: BG, color: TEXT,
      fontFamily: "'DM Sans', system-ui, sans-serif",
      display: 'flex', flexDirection: 'column',
    }}>
      <style>{`
        @keyframes pulse-dot {
          from { opacity: 0.5; transform: scale(0.85); }
          to   { opacity: 1;   transform: scale(1.2);  }
        }
      `}</style>

      {/* ── Header ── */}
      <header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '18px 28px', borderBottom: `1px solid ${BORDER}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, #1C3454 0%, #3D70BE 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 14, fontWeight: 700, color: '#A8CAFF',
          }}>AI</div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: TEXT }}>Interviewer Character System</div>
            <div style={{ fontSize: 11, color: MUTED, fontFamily: MONO }}>React + TypeScript + SVG</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {/* Character variant selector */}
          <div style={{
            display: 'flex', gap: 0, borderRadius: 8,
            border: `1px solid ${BORDER}`, overflow: 'hidden',
            marginRight: 8,
          }}>
            {(['western', 'arab'] as CharacterVariant[]).map(v => {
              const vm = VARIANT_META[v]
              const isActive = variant === v
              return (
                <button key={v} onClick={() => setVariant(v)} style={{
                  padding: '6px 14px', fontSize: 12, fontWeight: isActive ? 600 : 400,
                  border: 'none',
                  borderRight: v === 'western' ? `1px solid ${BORDER}` : 'none',
                  background: isActive ? `${vm.color}1A` : 'transparent',
                  color: isActive ? vm.color : MUTED,
                  cursor: 'pointer', fontFamily: 'inherit',
                  transition: 'all 160ms ease',
                }}>
                  {vm.label}
                  {isActive && (
                    <span style={{ fontSize: 10, color: vm.color + 'AA', marginLeft: 6, fontFamily: MONO }}>
                      {vm.sub}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          <button
            onClick={() => setShowTechnical(false)}
            style={{
              padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 500,
              border: `1px solid ${!showTechnical ? '#3D70BE80' : BORDER}`,
              background: !showTechnical ? 'rgba(61,112,190,0.15)' : 'transparent',
              color: !showTechnical ? '#7AB8E8' : MUTED, cursor: 'pointer',
            }}
          >
            Conversational
          </button>
          <button
            onClick={() => setShowTechnical(true)}
            style={{
              padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 500,
              border: `1px solid ${showTechnical ? '#F0A84080' : BORDER}`,
              background: showTechnical ? 'rgba(240,168,64,0.12)' : 'transparent',
              color: showTechnical ? '#F0A840' : MUTED, cursor: 'pointer',
            }}
          >
            Technical Interview
          </button>
        </div>
      </header>

      {/* ── Main content ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 360px',
        gap: 20, padding: 24, flex: 1,
        alignItems: 'start',
      }}>

        {/* ── LEFT: Main panel ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {showTechnical ? (
            <TechnicalPanel />
          ) : (
            <>
              {/* Interview panel */}
              <div style={{
                background: SURFACE, borderRadius: 16,
                border: `1px solid ${BORDER}`,
                overflow: 'hidden',
              }}>
                {/* Panel header */}
                <div style={{
                  padding: '14px 20px', borderBottom: `1px solid ${BORDER}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                      width: 8, height: 8, borderRadius: '50%', background: '#2A4462',
                    }} />
                    <span style={{ fontSize: 12, color: MUTED }}>AI Interviewer</span>
                  </div>
                  <Badge state={activeState} />
                </div>

                {/* Character area */}
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  padding: '52px 0 36px',
                  background: `radial-gradient(ellipse at 50% 60%, #112040 0%, ${SURFACE} 70%)`,
                  minHeight: 420, position: 'relative',
                }}>
                  {/* Ambient glow behind character */}
                  <div style={{
                    position: 'absolute', bottom: 60, left: '50%',
                    transform: 'translateX(-50%)',
                    width: 240, height: 240,
                    background: 'radial-gradient(circle, rgba(61,112,190,0.10) 0%, transparent 70%)',
                    borderRadius: '50%', pointerEvents: 'none',
                  }} />

                  <ActiveCharacter
                    key={activeState + variant}
                    state={activeState}
                    size="large"
                    presence={presence}
                  />
                </div>

                {/* Panel footer */}
                <div style={{
                  padding: '14px 20px', borderTop: `1px solid ${BORDER}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                  <span style={{ fontSize: 12, color: MUTED }}>{meta.mapping}</span>
                  <label style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    fontSize: 12, color: MUTED, cursor: 'pointer',
                  }}>
                    <span>Presence</span>
                    <div
                      onClick={() => setPresence(p => !p)}
                      style={{
                        width: 34, height: 18, borderRadius: 9,
                        background: presence ? '#3D70BE' : '#1A2E46',
                        border: `1px solid ${presence ? '#5A90DE' : BORDER}`,
                        position: 'relative', cursor: 'pointer', transition: 'all 200ms',
                      }}
                    >
                      <div style={{
                        position: 'absolute', top: 2, left: presence ? 16 : 2,
                        width: 12, height: 12, borderRadius: '50%',
                        background: presence ? '#A8CAFF' : MUTED,
                        transition: 'all 200ms',
                      }} />
                    </div>
                  </label>
                </div>
              </div>

              {/* State selector */}
              <div style={{
                background: SURFACE, borderRadius: 12,
                border: `1px solid ${BORDER}`, padding: '16px 18px',
              }}>
                <div style={{
                  fontSize: 11, fontWeight: 600, letterSpacing: '0.07em',
                  color: MUTED, fontFamily: MONO, marginBottom: 12,
                }}>
                  STATE SELECTOR
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {ALL_STATES.map(s => (
                    <StateButton
                      key={s} s={s} active={activeState === s}
                      onClick={() => setActiveState(s)}
                    />
                  ))}
                </div>
                <p style={{ margin: '12px 0 0', fontSize: 13, color: MUTED, lineHeight: 1.6 }}>
                  {meta.desc}
                </p>
              </div>
            </>
          )}

          {/* React integration contract */}
          <div style={{
            background: SURFACE, borderRadius: 12,
            border: `1px solid ${BORDER}`, padding: '16px 18px',
          }}>
            <div style={{
              fontSize: 11, fontWeight: 600, letterSpacing: '0.07em',
              color: MUTED, fontFamily: MONO, marginBottom: 12,
            }}>
              REACT INTEGRATION
            </div>
            <pre style={{
              margin: 0, background: BG, borderRadius: 8, padding: 14,
              border: `1px solid ${BORDER}`,
              fontFamily: MONO, fontSize: 12, lineHeight: 1.7,
              color: TEXT, overflowX: 'auto',
            }}>{`<InterviewerCharacter
  state="${showTechnical ? 'hidden' : activeState}"
  size="large"
  presence={${presence}}
/>`}</pre>
            <div style={{
              marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap',
            }}>
              {(['idle','listening','thinking','speaking','transition','hidden'] as const).map(s => (
                <code key={s} style={{
                  fontSize: 11, fontFamily: MONO, padding: '2px 8px',
                  borderRadius: 4, background: `${STATE_META[s].color}15`,
                  color: STATE_META[s].color, border: `1px solid ${STATE_META[s].color}30`,
                }}>
                  "{s}"
                </code>
              ))}
            </div>
          </div>
        </div>

        {/* ── RIGHT: State library + animation contract ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* State library grid */}
          <div style={{
            background: SURFACE, borderRadius: 12,
            border: `1px solid ${BORDER}`, padding: '16px 14px',
          }}>
            <div style={{
              fontSize: 11, fontWeight: 600, letterSpacing: '0.07em',
              color: MUTED, fontFamily: MONO, marginBottom: 14, padding: '0 4px',
            }}>
              STATE LIBRARY
            </div>
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6,
            }}>
              {ALL_STATES.map(s => (
                <LibraryCard
                  key={s + variant} s={s}
                  active={activeState === s && !showTechnical}
                  onClick={() => { setActiveState(s); setShowTechnical(false) }}
                  CharComponent={ActiveCharacter}
                />
              ))}
            </div>
          </div>

          {/* Animation contract */}
          <div style={{
            background: SURFACE, borderRadius: 12,
            border: `1px solid ${BORDER}`, padding: '16px 18px',
          }}>
            <div style={{
              fontSize: 11, fontWeight: 600, letterSpacing: '0.07em',
              color: MUTED, fontFamily: MONO, marginBottom: 14,
            }}>
              STATE MACHINE
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {[
                { from: 'idle',       to: 'listening',  arrow: true  },
                { from: 'listening',  to: 'thinking',   arrow: true  },
                { from: 'thinking',   to: 'speaking',   arrow: true  },
                { from: 'speaking',   to: 'idle',       arrow: true  },
                { from: null,         to: null,         arrow: false },
                { from: 'ANY STATE',  to: 'transition', arrow: true  },
                { from: 'transition', to: 'hidden',     arrow: true  },
              ].map((row, i) => row.from === null ? (
                <div key={i} style={{ height: 10 }} />
              ) : (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '3px 0',
                }}>
                  <code style={{
                    fontSize: 10, fontFamily: MONO, width: 88, flexShrink: 0,
                    color: row.from === 'ANY STATE' ? '#F0A840'
                      : STATE_META[row.from as InterviewerCharacterState]?.color ?? MUTED,
                  }}>
                    {row.from}
                  </code>
                  <span style={{ color: '#2A4462', fontSize: 12 }}>→</span>
                  <code style={{
                    fontSize: 10, fontFamily: MONO,
                    color: STATE_META[row.to as InterviewerCharacterState]?.color ?? MUTED,
                  }}>
                    {row.to}
                  </code>
                </div>
              ))}
            </div>
          </div>

          {/* Speaking loop */}
          <div style={{
            background: SURFACE, borderRadius: 12,
            border: `1px solid ${BORDER}`, padding: '16px 18px',
          }}>
            <div style={{
              fontSize: 11, fontWeight: 600, letterSpacing: '0.07em',
              color: MUTED, fontFamily: MONO, marginBottom: 14,
            }}>
              SPEAKING MOUTH LOOP
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              {['speakA', 'speakB', 'speakC', 'speakB', '↺'].map((label, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <code style={{
                    fontSize: 10, fontFamily: MONO, padding: '3px 8px',
                    borderRadius: 4,
                    background: label === '↺' ? 'transparent' : 'rgba(56,197,160,0.12)',
                    border: label === '↺' ? 'none' : '1px solid rgba(56,197,160,0.25)',
                    color: label === '↺' ? '#2A4462' : '#38C5A0',
                  }}>
                    {label}
                  </code>
                  {i < 4 && <span style={{ color: '#1E3450', fontSize: 12 }}>→</span>}
                </div>
              ))}
            </div>
            <p style={{ margin: '10px 0 0', fontSize: 11, color: '#4A6480', lineHeight: 1.6, fontFamily: MONO }}>
              210ms / frame · GPU: transform + opacity only
            </p>
          </div>

          {/* Component props */}
          <div style={{
            background: SURFACE, borderRadius: 12,
            border: `1px solid ${BORDER}`, padding: '16px 18px',
          }}>
            <div style={{
              fontSize: 11, fontWeight: 600, letterSpacing: '0.07em',
              color: MUTED, fontFamily: MONO, marginBottom: 12,
            }}>
              COMPONENT PROPS
            </div>
            <pre style={{
              margin: 0, fontSize: 11, fontFamily: MONO, color: MUTED,
              lineHeight: 1.8,
            }}>{`interface InterviewerCharacterProps {
  state:    InterviewerCharacterState
  size?:    "small" | "medium" | "large"
  presence?: boolean
  className?: string
}`}</pre>
          </div>

          {/* Accessibility note */}
          <div style={{
            borderRadius: 10, padding: '12px 14px',
            background: 'rgba(90,154,222,0.06)',
            border: '1px solid rgba(90,154,222,0.12)',
          }}>
            <div style={{ fontSize: 11, color: '#4A7AAE', lineHeight: 1.6 }}>
              <strong style={{ color: '#7AB8E8' }}>Accessibility:</strong>{' '}
              Component applies <code style={{ fontFamily: MONO }}>aria-hidden="true"</code>.
              Never captures keyboard focus. Supports <code style={{ fontFamily: MONO }}>prefers-reduced-motion</code> — all animations pause, character remains visible in correct state.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
