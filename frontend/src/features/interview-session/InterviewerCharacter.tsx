import { useEffect, useRef, useState, type CSSProperties } from 'react'
import './InterviewerCharacter.css'

// ── Public types ─────────────────────────────────────────────────

export type InterviewerCharacterState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'transition'
  | 'hidden'

export interface InterviewerCharacterProps {
  state: InterviewerCharacterState
  size?: 'small' | 'medium' | 'large'
  presence?: boolean
  className?: string
}

// ── Color palette ─────────────────────────────────────────────────
// Semantic tokens: swap these to adapt the character to a design system.

const C = {
  skin:         '#F2BE9B',
  skinHi:       '#FAD4B4',
  skinSh:       '#C8825A',
  ear:          '#D4946C',
  hair:         '#1B1228',
  hairHi:       '#2E1F40',
  blazer:       '#1C3454',
  blazerDk:     '#121F38',
  blazerHi:     '#264876',
  shirt:        '#EFEDE6',
  shirtSh:      '#D4D0C8',
  tie:          '#3D70BE',
  tieDk:        '#2A4E9A',
  eyeWhite:     '#F9FAF8',
  iris:         '#3A62BA',
  irisDk:       '#294A92',
  pupil:        '#080C1A',
  brow:         '#2E1E22',
  mouthStroke:  '#9A4535',
  mouthInt:     '#380D08',
  teeth:        '#EBE7DE',
  shadow:       'rgba(4, 8, 18, 0.32)',
} as const

// ── Mouth path definitions ────────────────────────────────────────
// Speaking variants differ in vertical aperture: A=16px B=22px C=10px

type ClosedMouth = { kind: 'closed'; d: string }
type OpenMouth   = { kind: 'open'; upper: string; fill: string; teeth: string }
type MouthDef    = ClosedMouth | OpenMouth

const MOUTHS: Record<string, MouthDef> = {
  neutral: {
    kind: 'closed',
    d: 'M 116 131 C 127 134 153 134 164 131',
  },
  smile: {
    kind: 'closed',
    d: 'M 114 128 C 126 140 154 140 166 128',
  },
  speakA: {
    kind: 'open',
    upper: 'M 117 127 C 128 134 152 134 163 127',
    fill:  'M 117 127 C 128 134 152 134 163 127 L 161 134 C 152 143 128 143 119 134 Z',
    teeth: 'M 119 128 C 128 133 152 133 161 128 L 160 132 C 152 137 128 137 120 132 Z',
  },
  speakB: {
    kind: 'open',
    upper: 'M 115 124 C 128 135 152 135 165 124',
    fill:  'M 115 124 C 128 135 152 135 165 124 L 163 135 C 152 146 128 146 117 135 Z',
    teeth: 'M 118 126 C 128 134 152 134 162 126 L 160 133 C 152 140 128 140 120 133 Z',
  },
  speakC: {
    kind: 'open',
    upper: 'M 118 129 C 128 133 152 133 162 129',
    fill:  'M 118 129 C 128 133 152 133 162 129 L 161 132 C 152 137 128 137 119 132 Z',
    teeth: 'M 120 130 C 128 132 152 132 160 130 L 159 132 C 152 134 128 134 121 132 Z',
  },
}

// Speaking mouth sequence — A→B→C→B loops naturally
const SPEAK_SEQ = ['speakA', 'speakB', 'speakC', 'speakB'] as const

function getMouthKey(state: InterviewerCharacterState, frame: number): string {
  if (state === 'idle') return 'smile'
  if (state === 'speaking') return SPEAK_SEQ[frame % SPEAK_SEQ.length]
  return 'neutral'
}

// ── Mouth renderer ────────────────────────────────────────────────

function MouthShape({ mouthKey }: { mouthKey: string }) {
  const def = MOUTHS[mouthKey] ?? MOUTHS.neutral
  if (def.kind === 'closed') {
    return (
      <path
        d={def.d}
        stroke={C.mouthStroke}
        strokeWidth="2.6"
        fill="none"
        strokeLinecap="round"
      />
    )
  }
  return (
    <g>
      <path d={def.fill}  fill={C.mouthInt} />
      <path d={def.teeth} fill={C.teeth} />
      <path
        d={def.upper}
        stroke={C.mouthStroke}
        strokeWidth="1.8"
        fill="none"
        strokeLinecap="round"
      />
    </g>
  )
}

// ── Presence indicator ────────────────────────────────────────────

function PresenceIndicator({ state }: { state: InterviewerCharacterState }) {
  return (
    <div className={`ic-presence ic-presence--${state}`} aria-hidden="true">
      <div className="ic-presence__dot" />
      <div className="ic-presence__dot" />
      <div className="ic-presence__dot" />
    </div>
  )
}

// ── Eyelid (blink overlay) ────────────────────────────────────────

function Eyelid({ cx, cy, rx, ry, blink }: {
  cx: number; cy: number; rx: number; ry: number; blink: boolean
}) {
  const style: CSSProperties = {
    transformOrigin: `${cx}px ${cy - ry}px`,
    transform: `scaleY(${blink ? 1 : 0})`,
    transition: blink ? 'transform 55ms linear' : 'transform 90ms ease-out',
  }
  return <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill={C.skin} style={style} />
}

// ── SVG character ─────────────────────────────────────────────────
// ViewBox: 0 0 280 480 — upper body, roughly waist/hip level cropped.
// Layer order: shadow → left-arm → right-arm → torso → neck → head.

interface SVGProps {
  state: InterviewerCharacterState
  blink: boolean
  speakFrame: number
}

function CharacterSVG({ state, blink, speakFrame }: SVGProps) {
  const mouthKey = getMouthKey(state, speakFrame)

  const charClass = `ic-character ic-character--${state}`
  const headClass = [
    'ic-head',
    state === 'listening' ? 'ic-head--listening' : '',
    state === 'thinking'  ? 'ic-head--thinking'  : '',
  ].filter(Boolean).join(' ')
  const leftArmClass  = `ic-arm-left${state === 'speaking' ? ' ic-arm-left--speaking' : ''}`
  const rightArmClass = `ic-arm-right${state === 'thinking' ? ' ic-arm-right--thinking' : ''}`

  return (
    <svg
      viewBox="0 0 280 480"
      xmlns="http://www.w3.org/2000/svg"
      style={{ width: '100%', height: '100%', overflow: 'visible' }}
      aria-hidden="true"
    >
      {/* Ground shadow */}
      <ellipse cx="140" cy="475" rx="92" ry="7" fill={C.shadow} />

      {/* ── Character root: breathing / speaking sway applied here ── */}
      <g className={charClass}>

        {/* ─ Left arm (drawn behind torso) ─ */}
        <g className={leftArmClass}>
          {/* Upper arm */}
          <path
            d="M 80 178 C 62 198 42 244 26 292
               C 38 298 54 300 62 293
               C 77 248 92 206 104 184 Z"
            fill={C.blazer}
          />
          {/* Forearm */}
          <path
            d="M 26 292 C 18 312 14 336 16 358
               L 36 364
               C 40 342 44 320 62 295 Z"
            fill={C.blazer}
          />
          {/* Cuff */}
          <path
            d="M 16 352 C 14 362 16 372 20 376 L 40 376 C 44 370 44 358 38 354 Z"
            fill={C.shirt}
          />
          {/* Hand */}
          <path
            d="M 12 362 C 10 344 18 334 28 334
               C 40 334 48 344 46 364
               C 44 380 34 386 22 382
               C 12 378 12 372 12 362 Z"
            fill={C.skin}
          />
          <path
            d="M 14 354 C 18 344 26 340 34 343"
            stroke={C.skinSh} strokeWidth="1" fill="none" strokeLinecap="round"
          />
        </g>

        {/* ─ Right arm (drawn behind torso) ─ */}
        <g className={rightArmClass}>
          {/* Upper arm */}
          <path
            d="M 200 178 C 218 198 238 244 254 292
               C 242 298 226 300 218 293
               C 203 248 188 206 176 184 Z"
            fill={C.blazer}
          />
          {/* Forearm */}
          <path
            d="M 254 292 C 262 312 266 336 264 358
               L 244 364
               C 240 342 236 320 218 295 Z"
            fill={C.blazer}
          />
          {/* Cuff */}
          <path
            d="M 264 352 C 266 362 264 372 260 376 L 240 376 C 236 370 236 358 242 354 Z"
            fill={C.shirt}
          />
          {/* Hand */}
          <path
            d="M 268 362 C 270 344 262 334 252 334
               C 240 334 232 344 234 364
               C 236 380 246 386 258 382
               C 268 378 268 372 268 362 Z"
            fill={C.skin}
          />
          <path
            d="M 266 354 C 262 344 254 340 246 343"
            stroke={C.skinSh} strokeWidth="1" fill="none" strokeLinecap="round"
          />
        </g>

        {/* ─ Torso / Blazer ─ */}

        {/* Base trapezoid — full blazer body */}
        <path
          d="M 0 480 L 14 208 C 20 180 50 172 84 170
             L 196 170
             C 230 172 260 180 266 208 L 280 480 Z"
          fill={C.blazer}
        />

        {/* Left side panel shading */}
        <path
          d="M 0 480 L 14 208 C 20 180 50 172 84 170
             L 120 170 L 116 212 L 82 256 L 44 480 Z"
          fill={C.blazerDk}
          opacity="0.48"
        />

        {/* Right side panel shading */}
        <path
          d="M 280 480 L 266 208 C 260 180 230 172 196 170
             L 160 170 L 164 212 L 198 256 L 236 480 Z"
          fill={C.blazerDk}
          opacity="0.48"
        />

        {/* Shirt — V-neck area */}
        <path
          d="M 122 170 C 126 186 134 210 140 330
             C 146 210 154 186 158 170 Z"
          fill={C.shirt}
        />
        {/* Shirt shadow at left edge */}
        <path
          d="M 122 170 C 125 182 129 200 132 244
             C 129 230 126 208 124 186 Z"
          fill={C.shirtSh} opacity="0.65"
        />
        {/* Shirt shadow at right edge */}
        <path
          d="M 158 170 C 155 182 151 200 148 244
             C 151 230 154 208 156 186 Z"
          fill={C.shirtSh} opacity="0.65"
        />

        {/* Left lapel */}
        <path
          d="M 0 480 L 14 208 C 20 180 50 172 84 170
             L 122 170 L 116 212 L 82 256 L 44 480 Z"
          fill={C.blazer}
        />

        {/* Right lapel */}
        <path
          d="M 280 480 L 266 208 C 260 180 230 172 196 170
             L 158 170 L 164 212 L 198 256 L 236 480 Z"
          fill={C.blazer}
        />

        {/* Lapel roll highlights */}
        <path
          d="M 122 170 C 118 184 116 200 116 212"
          stroke={C.blazerHi} strokeWidth="1.5" fill="none" strokeLinecap="round" opacity="0.55"
        />
        <path
          d="M 158 170 C 162 184 164 200 164 212"
          stroke={C.blazerHi} strokeWidth="1.5" fill="none" strokeLinecap="round" opacity="0.55"
        />

        {/* Pocket square */}
        <path d="M 52 222 L 68 222 L 71 236 L 49 236 Z" fill={C.blazerHi} opacity="0.28" />
        <path d="M 54 222 L 56 215 L 60 218 L 64 215 L 66 222" fill={C.shirt} opacity="0.82" />

        {/* Blazer button */}
        <circle cx="140" cy="278" r="5" fill={C.blazerHi} opacity="0.45" />
        <circle cx="140" cy="278" r="3" fill={C.blazer} />

        {/* Left collar wing */}
        <path
          d="M 118 175 C 124 162 131 157 140 157 L 140 162 C 132 162 126 166 122 175 Z"
          fill={C.shirt}
        />
        {/* Right collar wing */}
        <path
          d="M 162 175 C 156 162 149 157 140 157 L 140 162 C 148 162 154 166 158 175 Z"
          fill={C.shirt}
        />

        {/* Tie */}
        <path
          d="M 134 178 L 130 196 L 137 216 L 140 348 L 143 216 L 150 196 L 146 178 Z"
          fill={C.tie}
        />
        <path
          d="M 134 178 L 130 196 L 136 210 L 140 280 C 139 260 136 220 134 178"
          fill={C.tieDk} opacity="0.45"
        />
        {/* Tie knot */}
        <path
          d="M 134 176 C 136 169 144 169 146 176 L 143 184 L 140 186 L 137 184 Z"
          fill={C.tieDk}
        />

        {/* ─ Neck ─ */}
        <path d="M 122 152 L 118 175 L 162 175 L 158 152 Z" fill={C.skin} />
        {/* Neck shading */}
        <path d="M 122 152 L 120 168 L 125 175 L 118 175 Z" fill={C.skinSh} opacity="0.30" />
        <path d="M 158 152 L 160 168 L 155 175 L 162 175 Z" fill={C.skinSh} opacity="0.30" />

        {/* ── Head group (rotates for listening / thinking tilt) ── */}
        <g className={headClass}>

          {/* Ears — drawn before head ellipse so head overlaps them */}
          <ellipse cx="83"  cy="99" rx="10" ry="14" fill={C.skin} />
          <path d="M 83 88 C 86 91 87 97 86 105 C 85 109 83 111 81 109"
            stroke={C.ear} strokeWidth="1" fill="none" opacity="0.5" />
          <ellipse cx="197" cy="99" rx="10" ry="14" fill={C.skin} />
          <path d="M 197 88 C 194 91 193 97 194 105 C 195 109 197 111 199 109"
            stroke={C.ear} strokeWidth="1" fill="none" opacity="0.5" />

          {/* Head ellipse */}
          <ellipse cx="140" cy="94" rx="58" ry="63" fill={C.skin} />

          {/* Face highlight */}
          <ellipse cx="136" cy="74" rx="29" ry="23" fill={C.skinHi} opacity="0.28" />

          {/* Jaw shadow */}
          <ellipse cx="140" cy="138" rx="44" ry="18" fill={C.skinSh} opacity="0.10" />

          {/* ─ Hair ─ */}
          <path
            d="M 83 96
               C 83 28 197 28 197 96
               C 180 52 164 34 140 34
               C 116 34 100 52 83 96 Z"
            fill={C.hair}
          />
          {/* Hair highlight */}
          <path
            d="M 96 80 C 96 42 122 30 140 30 C 128 38 110 52 100 74 Z"
            fill={C.hairHi} opacity="0.42"
          />
          {/* Sideburns */}
          <path d="M 83 96 C 82 106 83 116 85 122"
            stroke={C.hair} strokeWidth="5.5" fill="none" strokeLinecap="round" />
          <path d="M 197 96 C 198 106 197 116 195 122"
            stroke={C.hair} strokeWidth="5.5" fill="none" strokeLinecap="round" />

          {/* ─ Eyebrows ─ */}
          {/* Left */}
          <path
            d="M 107 82 C 114 75 125 74 133 79"
            stroke={C.brow} strokeWidth="4" fill="none" strokeLinecap="round"
          />
          {/* Right */}
          <path
            d="M 147 79 C 155 74 166 75 173 82"
            stroke={C.brow} strokeWidth="4" fill="none" strokeLinecap="round"
          />

          {/* ─ Eyes ─ */}
          {/* Left eye */}
          <g>
            <ellipse cx="120" cy="96" rx="13" ry="14" fill={C.eyeWhite} />
            <circle  cx="121" cy="97" r="9" fill={C.iris} />
            <circle  cx="120" cy="97" r="9" fill={C.irisDk} opacity="0.38" />
            <circle  cx="122" cy="97" r="5.2" fill={C.pupil} />
            <circle  cx="125" cy="93" r="3" fill="white" opacity="0.88" />
            {/* Upper eyelid crease */}
            <path
              d="M 107 91 C 113 85 127 85 133 91"
              stroke={C.skinSh} strokeWidth="1.4" fill="none" strokeLinecap="round" opacity="0.5"
            />
            {/* Blink overlay */}
            <Eyelid cx={120} cy={96} rx={13} ry={14} blink={blink} />
          </g>

          {/* Right eye */}
          <g>
            <ellipse cx="160" cy="96" rx="13" ry="14" fill={C.eyeWhite} />
            <circle  cx="161" cy="97" r="9" fill={C.iris} />
            <circle  cx="160" cy="97" r="9" fill={C.irisDk} opacity="0.38" />
            <circle  cx="162" cy="97" r="5.2" fill={C.pupil} />
            <circle  cx="165" cy="93" r="3" fill="white" opacity="0.88" />
            {/* Upper eyelid crease */}
            <path
              d="M 147 91 C 153 85 167 85 173 91"
              stroke={C.skinSh} strokeWidth="1.4" fill="none" strokeLinecap="round" opacity="0.5"
            />
            {/* Blink overlay */}
            <Eyelid cx={160} cy={96} rx={13} ry={14} blink={blink} />
          </g>

          {/* ─ Nose ─ */}
          <path
            d="M 134 112 C 132 118 135 123 140 124
               C 145 123 148 118 146 112"
            stroke={C.skinSh} strokeWidth="1.5" fill="none"
            strokeLinecap="round" opacity="0.5"
          />
          <ellipse cx="135" cy="120" rx="4.5" ry="3.5" fill={C.skinSh} opacity="0.20" />
          <ellipse cx="145" cy="120" rx="4.5" ry="3.5" fill={C.skinSh} opacity="0.20" />

          {/* ─ Mouth ─ */}
          <MouthShape mouthKey={mouthKey} />

          {/* Cheek flush */}
          <ellipse cx="98"  cy="116" rx="17" ry="13" fill="#D87060" opacity="0.08" />
          <ellipse cx="182" cy="116" rx="17" ry="13" fill="#D87060" opacity="0.08" />
        </g>
        {/* end head group */}

      </g>
      {/* end character group */}
    </svg>
  )
}

// ── Main exported component ───────────────────────────────────────

const SIZE_DIMS = {
  small:  { width: 160, height: 248 },
  medium: { width: 240, height: 372 },
  large:  { width: 320, height: 496 },
}

/**
 * InterviewerCharacter — pure presentational component.
 *
 * Usage:
 *   <InterviewerCharacter state="speaking" size="large" presence />
 *
 * The parent controls `state`; this component owns no interview logic.
 * Set aria-hidden="true" on the wrapper (already applied internally).
 * During technical interview, pass state="hidden" — the component renders null.
 */
export default function InterviewerCharacter({
  state,
  size = 'medium',
  presence = false,
  className = '',
}: InterviewerCharacterProps) {
  const [blink, setBlink]           = useState(false)
  const [speakFrame, setSpeakFrame] = useState(0)
  const blinkTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const speakInterval = useRef<ReturnType<typeof setInterval> | null>(null)

  // Randomised blink loop — cancels when character is invisible
  useEffect(() => {
    if (state === 'hidden' || state === 'transition') return

    const schedule = () => {
      const delay = 2600 + Math.random() * 3400
      blinkTimeout.current = setTimeout(() => {
        setBlink(true)
        setTimeout(() => setBlink(false), 140)
        schedule()
      }, delay)
    }
    schedule()

    return () => {
      if (blinkTimeout.current) clearTimeout(blinkTimeout.current)
    }
  }, [state])

  // Speaking mouth cycle — A→B→C→B repeating at ~210ms per frame
  useEffect(() => {
    if (state !== 'speaking') {
      setSpeakFrame(0)
      return
    }
    speakInterval.current = setInterval(() => {
      setSpeakFrame(f => (f + 1) % SPEAK_SEQ.length)
    }, 210)
    return () => {
      if (speakInterval.current) clearInterval(speakInterval.current)
    }
  }, [state])

  // Hidden: renders nothing — zero visual footprint during technical interview
  if (state === 'hidden') return null

  const { width, height } = SIZE_DIMS[size]

  const wrapperClass = [
    'interviewer-character',
    `interviewer-character--${size}`,
    `interviewer-character--${state}`,
    className,
  ].filter(Boolean).join(' ')

  return (
    <div
      className={wrapperClass}
      style={{ width, height }}
      aria-hidden="true"
      data-state={state}
    >
      <CharacterSVG state={state} blink={blink} speakFrame={speakFrame} />
      {presence && (state === 'thinking' || state === 'speaking') && (
        <PresenceIndicator state={state} />
      )}
    </div>
  )
}
