import { useEffect, useRef, useState } from 'react'
// Shares the same animation CSS as InterviewerCharacter
import './InterviewerCharacter.css'

export type InterviewerCharacterState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'hidden' | 'transition';

export interface InterviewerCharacterProps {
  state: InterviewerCharacterState
  size?: 'small' | 'medium' | 'large'
  presence?: boolean
  className?: string
}

// ── Semantic color tokens — UAE Traditional Attire ────────────────
// Kandura: white/cream long robe. Guthra: white headscarf.
// Agal: black rope ring. Beard: dark, well-groomed.

const T = {
  // Skin — warm olive-brown
  skin:        '#C8835A',
  skinHi:      '#DC9E74',
  skinSh:      '#A8622E',
  ear:         '#B86E3E',

  // Beard — very dark brown, trimmed
  beard:       '#18100A',
  beardHi:     '#2C1E10',
  beardEdge:   '#241608',
  mustache:    '#1A1208',

  // Eyes — dark brown
  eyeWhite:    '#F9FAF8',
  iris:        '#4A2C14',
  irisDk:      '#2E1A08',
  pupil:       '#060402',
  brow:        '#18100A',

  // Mouth
  mouthStroke: '#8C3C28',
  mouthInt:    '#2E0A04',
  teeth:       '#EAE6DC',

  // Kandura (thobe/dishdasha) — white robe
  kandura:     '#F2F0EA',
  kanduraSh:   '#DDDAD2',
  kanduraLn:   '#C8C5BC',

  // Guthra (headscarf) — white
  guthra:      '#F4F2EC',
  guthraSh:    '#DEDAD2',
  guthraFold:  '#E6E3DB',

  // Agal — near-black rope ring
  agal:        '#161010',
  agalHi:      '#241818',

  // Ground
  shadow:      'rgba(4, 8, 18, 0.28)',
} as const

// ── Mouth paths — positioned in the beard gap ─────────────────────
// Mouth visible between mustache (y≈127) and lower beard (y≈136).

type ClosedMouth = { kind: 'closed'; d: string }
type OpenMouth   = { kind: 'open'; upper: string; fill: string; teeth: string }
type MouthDef    = ClosedMouth | OpenMouth

const MOUTHS: Record<string, MouthDef> = {
  neutral: {
    kind: 'closed',
    d: 'M 120 133 C 128 136 152 136 160 133',
  },
  smile: {
    kind: 'closed',
    d: 'M 118 131 C 128 139 152 139 162 131',
  },
  speakA: {
    kind: 'open',
    upper: 'M 120 130 C 128 135 152 135 160 130',
    fill:  'M 120 130 C 128 135 152 135 160 130 L 158 136 C 152 144 128 144 122 136 Z',
    teeth: 'M 122 131 C 128 135 152 135 158 131 L 157 134 C 151 138 129 138 123 134 Z',
  },
  speakB: {
    kind: 'open',
    upper: 'M 118 127 C 128 136 152 136 162 127',
    fill:  'M 118 127 C 128 136 152 136 162 127 L 160 137 C 152 147 128 147 120 137 Z',
    teeth: 'M 120 129 C 128 135 152 135 160 129 L 158 135 C 152 142 128 142 122 135 Z',
  },
  speakC: {
    kind: 'open',
    upper: 'M 120 131 C 128 135 152 135 160 131',
    fill:  'M 120 131 C 128 135 152 135 160 131 L 159 135 C 152 140 128 140 121 135 Z',
    teeth: 'M 122 132 C 128 134 152 134 158 132 L 157 134 C 151 137 129 137 123 134 Z',
  },
}

const SPEAK_SEQ = ['speakA', 'speakB', 'speakC', 'speakB'] as const

function getMouthKey(state: InterviewerCharacterState, frame: number): string {
  if (state === 'idle') return 'smile'
  if (state === 'speaking') return SPEAK_SEQ[frame % SPEAK_SEQ.length]
  return 'neutral'
}

// ── Eyebrow paths — per state ─────────────────────────────────────

function getBrows(state: InterviewerCharacterState) {
  switch (state) {
    case 'listening':
      return {
        left:  'M 108 81 C 115 73 126 72 134 77',
        right: 'M 146 77 C 154 72 165 73 172 81',
      }
    case 'thinking':
      return {
        left:  'M 109 82 C 116 74 127 73 134 78',
        right: 'M 146 78 C 153 75 164 77 171 83',
      }
    default:
      return {
        left:  'M 108 83 C 115 76 126 75 134 80',
        right: 'M 146 80 C 154 75 165 76 172 83',
      }
  }
}

// ── Mouth renderer ────────────────────────────────────────────────

function MouthShape({ mouthKey }: { mouthKey: string }) {
  const def = MOUTHS[mouthKey] ?? MOUTHS.neutral
  if (def.kind === 'closed') {
    return (
      <path d={def.d} stroke={T.mouthStroke} strokeWidth="2.4"
        fill="none" strokeLinecap="round" />
    )
  }
  return (
    <g>
      <path d={def.fill}  fill={T.mouthInt} />
      <path d={def.teeth} fill={T.teeth} />
      <path d={def.upper} stroke={T.mouthStroke} strokeWidth="1.8"
        fill="none" strokeLinecap="round" />
    </g>
  )
}

// ── Blink eyelid ──────────────────────────────────────────────────

function Eyelid({ cx, cy, rx, ry, blink }: {
  cx: number; cy: number; rx: number; ry: number; blink: boolean
}) {
  return (
    <ellipse
      className="ic-eyelid"
      cx={cx} cy={cy} rx={rx} ry={ry}
      fill={T.skin}
      style={{
        transform:  `scaleY(${blink ? 1 : 0})`,
        transition: blink ? 'transform 55ms linear' : 'transform 90ms ease-out',
      }}
    />
  )
}

// ── Presence indicator ────────────────────────────────────────────

// function PresenceIndicator({ state }: { state: InterviewerCharacterState }) {
//   return (
//     <div className={`ic-presence ic-presence--${state}`} aria-hidden="true">
//       <div className="ic-presence__dot" />
//       <div className="ic-presence__dot" />
//       <div className="ic-presence__dot" />
//     </div>
//   )
// }

// ── SVG character — UAE Traditional Dress ─────────────────────────
// ViewBox 0 0 280 480 — same as western character for layout parity.
//
// Layer order (back → front):
//   ground-shadow
//   guthra-side-drapes     (cloth falling behind arms/torso)
//   left-arm               (kandura sleeve)
//   right-arm              (kandura sleeve)
//   kandura-body           (white robe)
//   kandura-collar-detail
//   guthra-cap             (white cloth on head)
//   agal                   (black rope ring on guthra)
//   ears
//   head-ellipse           (skin)
//   beard
//   eyebrows, eyes, nose, mouth
//   cheek-flush

interface SVGCharProps {
  state: InterviewerCharacterState
  blink: boolean
  speakFrame: number
}

function SVGCharacter({ state, blink, speakFrame }: SVGCharProps) {
  const mouthKey = getMouthKey(state, speakFrame)
  const brows    = getBrows(state)

  const charCls = `ic-character ic-character--${state}`
  const headCls = [
    'ic-head',
    state === 'listening' ? 'ic-head--listening' : '',
    state === 'thinking'  ? 'ic-head--thinking'  : '',
  ].filter(Boolean).join(' ')

  const leftBrowCls = [
    'ic-brow',
    state === 'listening' ? 'ic-brow--raised'      : '',
    state === 'thinking'  ? 'ic-brow--left-raised' : '',
    state === 'speaking'  ? 'ic-brow--speaking'    : '',
  ].filter(Boolean).join(' ')

  const rightBrowCls = [
    'ic-brow',
    state === 'listening' ? 'ic-brow--raised'    : '',
    state === 'speaking'  ? 'ic-brow--speaking'  : '',
  ].filter(Boolean).join(' ')

  const leftArmCls  = `ic-arm-left${state === 'speaking'  ? ' ic-arm-left--speaking'   : ''}`
  const rightArmCls = `ic-arm-right${state === 'thinking' ? ' ic-arm-right--thinking'  : ''}`

  return (
    <svg
      viewBox="0 0 280 480"
      xmlns="http://www.w3.org/2000/svg"
      style={{ width: '100%', height: '100%', overflow: 'visible' }}
      aria-hidden="true"
    >
      {/* Ground shadow */}
      <ellipse cx="140" cy="475" rx="94" ry="7" fill={T.shadow} />

      {/* ══ Guthra side drapes — behind everything, fall to shoulders ══ */}
      {/* These are drawn BEFORE the character group so they sit behind arms/torso */}
      {/* Left drape */}
      <path
        d="M 88 92
           C 76 110 64 148 58 180
           L 84 188 C 90 168 94 138 108 104 Z"
        fill={T.guthra}
      />
      {/* Left drape inner shadow fold */}
      <path
        d="M 88 92 C 84 108 80 136 78 164 C 82 150 86 120 100 98 Z"
        fill={T.guthraSh} opacity="0.5"
      />
      {/* Right drape */}
      <path
        d="M 192 92
           C 204 110 216 148 222 180
           L 196 188 C 190 168 186 138 172 104 Z"
        fill={T.guthra}
      />
      {/* Right drape inner shadow fold */}
      <path
        d="M 192 92 C 196 108 200 136 202 164 C 198 150 194 120 180 98 Z"
        fill={T.guthraSh} opacity="0.5"
      />

      {/* ══ Character root — breathing / speaking sway ══ */}
      <g className={charCls}>

        {/* ── Left arm — kandura sleeve (white) ─────────── */}
        <g className={leftArmCls}>
          {/* Upper arm */}
          <path
            d="M 80 178
               C 62 200 42 246 26 292
               C 38 298 54 300 62 294
               C 77 248 92 208 104 185 Z"
            fill={T.kandura}
          />
          {/* Sleeve shadow inner */}
          <path
            d="M 80 178 C 72 196 60 234 48 276
               C 56 278 62 280 62 276
               C 72 244 84 208 96 186 Z"
            fill={T.kanduraSh} opacity="0.55"
          />
          {/* Forearm */}
          <path
            d="M 26 292
               C 18 313 14 338 16 360
               L 36 366
               C 40 344 44 321 62 296 Z"
            fill={T.kandura}
          />
          {/* Cuff fold */}
          <path
            d="M 16 354 C 14 364 16 374 20 378
               L 40 378 C 44 372 44 360 38 356 Z"
            fill={T.kanduraSh}
          />
          {/* Hand */}
          <path
            d="M 12 364
               C 10 346 18 336 28 336
               C 40 336 48 346 46 366
               C 44 382 34 388 22 384
               C 12 380 12 374 12 364 Z"
            fill={T.skin}
          />
          <path
            d="M 14 356 C 18 346 27 341 35 344"
            stroke={T.skinSh} strokeWidth="1" fill="none" strokeLinecap="round"
          />
        </g>

        {/* ── Right arm — kandura sleeve ─────────────────── */}
        <g className={rightArmCls}>
          {/* Upper arm */}
          <path
            d="M 200 178
               C 218 200 238 246 254 292
               C 242 298 226 300 218 294
               C 203 248 188 208 176 185 Z"
            fill={T.kandura}
          />
          {/* Sleeve shadow inner */}
          <path
            d="M 200 178 C 208 196 220 234 232 276
               C 224 278 218 280 218 276
               C 208 244 196 208 184 186 Z"
            fill={T.kanduraSh} opacity="0.55"
          />
          {/* Forearm */}
          <path
            d="M 254 292
               C 262 313 266 338 264 360
               L 244 366
               C 240 344 236 321 218 296 Z"
            fill={T.kandura}
          />
          {/* Cuff fold */}
          <path
            d="M 264 354 C 266 364 264 374 260 378
               L 240 378 C 236 372 236 360 242 356 Z"
            fill={T.kanduraSh}
          />
          {/* Hand */}
          <path
            d="M 268 364
               C 270 346 262 336 252 336
               C 240 336 232 346 234 366
               C 236 382 246 388 258 384
               C 268 380 268 374 268 364 Z"
            fill={T.skin}
          />
          <path
            d="M 266 356 C 262 346 253 341 245 344"
            stroke={T.skinSh} strokeWidth="1" fill="none" strokeLinecap="round"
          />
        </g>

        {/* ── Kandura body ────────────────────────────────── */}
        {/* Main robe */}
        <path
          d="M 0 480
             L 16 206
             C 22 180 52 170 86 168
             L 194 168
             C 228 170 258 180 264 206
             L 280 480 Z"
          fill={T.kandura}
        />
        {/* Robe left shadow */}
        <path
          d="M 0 480 L 16 206 C 22 180 52 170 86 168
             L 120 168 L 116 212 L 80 260 L 40 480 Z"
          fill={T.kanduraSh} opacity="0.38"
        />
        {/* Robe right shadow */}
        <path
          d="M 280 480 L 264 206 C 258 180 228 170 194 168
             L 160 168 L 164 212 L 200 260 L 240 480 Z"
          fill={T.kanduraSh} opacity="0.38"
        />
        {/* Center front seam — subtle */}
        <line x1="140" y1="168" x2="140" y2="480"
          stroke={T.kanduraLn} strokeWidth="0.8" opacity="0.4" />
        {/* Center button placket (top few buttons) */}
        <rect x="138" y="175" width="4" height="44"
          rx="2" fill={T.kanduraSh} opacity="0.5" />
        {[186, 200, 214].map(y => (
          <circle key={y} cx="140" cy={y} r="2.5"
            fill={T.kanduraLn} opacity="0.7" />
        ))}

        {/* Kandura collar (small standing mandarin collar) */}
        <path
          d="M 124 154
             C 126 144 132 138 140 138
             C 148 138 154 144 156 154
             L 158 172 L 122 172 Z"
          fill={T.kandura}
        />
        {/* Collar shadow */}
        <path
          d="M 124 154 C 126 146 130 140 136 138 L 136 142 C 131 144 128 150 128 158 L 122 172 Z"
          fill={T.kanduraSh} opacity="0.5"
        />
        {/* Collar right shadow */}
        <path
          d="M 156 154 C 154 146 150 140 144 138 L 144 142 C 149 144 152 150 152 158 L 158 172 Z"
          fill={T.kanduraSh} opacity="0.5"
        />

        {/* Neck skin (visible between collar flaps) */}
        <path d="M 128 152 L 124 172 L 156 172 L 152 152 Z" fill={T.skin} />
        {/* Neck shadow */}
        <path d="M 128 152 L 126 166 L 130 172 L 124 172 Z" fill={T.skinSh} opacity="0.3" />
        <path d="M 152 152 L 154 166 L 150 172 L 156 172 Z" fill={T.skinSh} opacity="0.3" />

        {/* ══ Head group — tilts for listening / thinking ══ */}
        <g className={headCls}>

          {/* ── Guthra cap — white cloth on head ────────── */}
          {/* Main dome shape covering crown */}
          <path
            d="M 86 80
               C 84 34 108 14 140 14
               C 172 14 196 34 194 80
               L 194 90
               C 188 84 168 78 140 78
               C 112 78 92 84 86 90 Z"
            fill={T.guthra}
          />
          {/* Guthra subtle highlight on crown */}
          <path
            d="M 116 16 C 108 24 100 40 98 58 C 108 40 120 26 140 20 Z"
            fill="white" opacity="0.28"
          />
          {/* Guthra front fold shadow (where cloth meets forehead) */}
          <path
            d="M 88 78 C 92 72 108 66 140 66 C 172 66 188 72 192 78 L 192 88 C 188 82 168 78 140 78 C 112 78 92 82 88 88 Z"
            fill={T.guthraSh} opacity="0.45"
          />

          {/* ── Agal — black rope ring ───────────────────── */}
          {/* Outer ring */}
          <path
            d="M 88 52
               C 88 38 110 30 140 30
               C 170 30 192 38 192 52
               L 192 66
               C 192 76 170 82 140 82
               C 110 82 88 76 88 66 Z"
            fill={T.agal}
          />
          {/* Agal inner highlight (double-ring look) */}
          <path
            d="M 92 52 C 92 42 114 36 140 36 C 166 36 188 42 188 52 L 188 58 C 188 64 166 68 140 68 C 114 68 92 64 92 58 Z"
            fill={T.agalHi}
          />
          {/* Agal rope texture hint */}
          <path d="M 90 56 C 100 52 120 50 140 50 C 160 50 180 52 190 56"
            stroke={T.agal} strokeWidth="2.5" fill="none" opacity="0.6" />
          {/* Agal second cord (slightly below) */}
          <path d="M 90 64 C 100 60 120 58 140 58 C 160 58 180 60 190 64"
            stroke={T.agal} strokeWidth="2" fill="none" opacity="0.5" />

          {/* ── Ears ─────────────────────────────────────── */}
          <ellipse cx="82"  cy="100" rx="10" ry="14" fill={T.skin} />
          <path d="M 82 90 C 85 93 86 99 85 108 C 84 112 82 114 80 112"
            stroke={T.ear} strokeWidth="1.2" fill="none" opacity="0.55" />
          <ellipse cx="198" cy="100" rx="10" ry="14" fill={T.skin} />
          <path d="M 198 90 C 195 93 194 99 195 108 C 196 112 198 114 200 112"
            stroke={T.ear} strokeWidth="1.2" fill="none" opacity="0.55" />

          {/* ── Head skin ─────────────────────────────────── */}
          <ellipse cx="140" cy="95" rx="58" ry="63" fill={T.skin} />
          {/* Face highlight */}
          <ellipse cx="136" cy="78" rx="26" ry="20" fill={T.skinHi} opacity="0.22" />

          {/* ── Beard — full groomed beard ─────────────────
               Layers: jaw beard → mustache → cheek beard sides.
               Mouth draws on top of beard (beard parts for speech). */}

          {/* Main jaw beard + lower face coverage */}
          <path
            d="M 100 122
               C 90 134 86 152 90 168
               C 96 186 118 196 140 196
               C 162 196 184 186 190 168
               C 194 152 190 134 180 122
               C 170 116 156 112 140 112
               C 124 112 110 116 100 122 Z"
            fill={T.beard}
          />
          {/* Beard highlight (subtle depth on lower beard) */}
          <path
            d="M 118 114 C 108 122 104 138 108 154 C 116 148 126 144 130 140 C 124 132 120 122 118 114 Z"
            fill={T.beardHi} opacity="0.45"
          />
          {/* Beard right highlight */}
          <path
            d="M 162 114 C 172 122 176 138 172 154 C 164 148 154 144 150 140 C 156 132 160 122 162 114 Z"
            fill={T.beardHi} opacity="0.45"
          />
          {/* Beard center chin highlight */}
          <path
            d="M 128 168 C 130 180 134 190 140 193 C 146 190 150 180 152 168 C 148 174 144 178 140 178 C 136 178 132 174 128 168 Z"
            fill={T.beardHi} opacity="0.35"
          />
          {/* Mustache — sits between nose and open mouth gap */}
          <path
            d="M 118 124
               C 122 118 130 115 140 115
               C 150 115 158 118 162 124
               C 158 130 152 133 140 132
               C 128 133 122 130 118 124 Z"
            fill={T.mustache}
          />
          {/* Mustache highlight */}
          <path
            d="M 122 120 C 126 116 132 114 140 114 C 136 116 128 118 122 120 Z"
            fill={T.beardHi} opacity="0.4"
          />
          {/* Cheek beard — left side (connects mustache to main beard) */}
          <path
            d="M 100 122
               C 96 128 96 136 98 144
               C 104 136 110 128 118 122 Z"
            fill={T.beard}
          />
          {/* Cheek beard — right side */}
          <path
            d="M 180 122
               C 184 128 184 136 182 144
               C 176 136 170 128 162 122 Z"
            fill={T.beard}
          />

          {/* ── Eyebrows ─────────────────────────────────── */}
          <path
            className={leftBrowCls}
            d={brows.left}
            stroke={T.brow} strokeWidth="4.8"
            fill="none" strokeLinecap="round"
          />
          <path
            className={rightBrowCls}
            d={brows.right}
            stroke={T.brow} strokeWidth="4.8"
            fill="none" strokeLinecap="round"
          />

          {/* ── Eyes ─────────────────────────────────────── */}
          {/* Left eye */}
          <g>
            <ellipse cx="120" cy="98" rx="13" ry="14" fill={T.eyeWhite} />
            <circle  cx="121" cy="99" r="9"   fill={T.iris} />
            <circle  cx="120" cy="99" r="9"   fill={T.irisDk} opacity="0.4" />
            <circle  cx="122" cy="99" r="5.2" fill={T.pupil} />
            <circle  cx="125" cy="95" r="3"   fill="white" opacity="0.85" />
            {/* Eyelid crease */}
            <path d="M 107 93 C 113 87 127 87 133 93"
              stroke={T.skinSh} strokeWidth="1.4" fill="none" strokeLinecap="round" opacity="0.45" />
            {/* Lower lash */}
            <path d="M 108 104 C 114 109 126 109 132 104"
              stroke={T.skinSh} strokeWidth="0.9" fill="none" strokeLinecap="round" opacity="0.20" />
            <Eyelid cx={120} cy={98} rx={13} ry={14} blink={blink} />
          </g>
          {/* Right eye */}
          <g>
            <ellipse cx="160" cy="98" rx="13" ry="14" fill={T.eyeWhite} />
            <circle  cx="161" cy="99" r="9"   fill={T.iris} />
            <circle  cx="160" cy="99" r="9"   fill={T.irisDk} opacity="0.4" />
            <circle  cx="162" cy="99" r="5.2" fill={T.pupil} />
            <circle  cx="165" cy="95" r="3"   fill="white" opacity="0.85" />
            {/* Eyelid crease */}
            <path d="M 147 93 C 153 87 167 87 173 93"
              stroke={T.skinSh} strokeWidth="1.4" fill="none" strokeLinecap="round" opacity="0.45" />
            {/* Lower lash */}
            <path d="M 148 104 C 154 109 166 109 172 104"
              stroke={T.skinSh} strokeWidth="0.9" fill="none" strokeLinecap="round" opacity="0.20" />
            <Eyelid cx={160} cy={98} rx={13} ry={14} blink={blink} />
          </g>

          {/* ── Nose ─────────────────────────────────────── */}
          <path
            d="M 134 110 C 132 117 135 122 140 123 C 145 122 148 117 146 110"
            stroke={T.skinSh} strokeWidth="1.5" fill="none"
            strokeLinecap="round" opacity="0.48"
          />
          <ellipse cx="135" cy="120" rx="4.5" ry="3.5" fill={T.skinSh} opacity="0.20" />
          <ellipse cx="145" cy="120" rx="4.5" ry="3.5" fill={T.skinSh} opacity="0.20" />

          {/* ── Mouth — drawn on top of beard ────────────── */}
          <MouthShape mouthKey={mouthKey} />

          {/* Subtle cheek warmth */}
          <ellipse cx="96"  cy="118" rx="16" ry="12" fill="#C06040" opacity="0.06" />
          <ellipse cx="184" cy="118" rx="16" ry="12" fill="#C06040" opacity="0.06" />

        </g>
        {/* end head group */}

      </g>
      {/* end character group */}
    </svg>
  )
}

// ── Size map — mirrors InterviewerCharacter for layout parity ─────

const SIZE_DIMS = {
  small:  { width: 160, height: 248 },
  medium: { width: 240, height: 372 },
  large:  { width: 320, height: 496 },
}

// ── Main exported component ───────────────────────────────────────

/**
 * ArabInterviewerCharacter — UAE traditional dress variant.
 * Kandura (white robe) · Guthra (headscarf) · Agal (black rope ring) · Beard.
 *
 * Identical state machine and prop interface as InterviewerCharacter.
 * Drop-in replacement: swap the import, keep <InterviewerCharacter state="..." />.
 *
 * Pure presentational. Zero interview logic. aria-hidden="true".
 * state="hidden" → returns null (zero DOM footprint during technical interview).
 */
export default function InterviewerCharacter({
  state,
  size = 'medium',
  presence = false,
  className = '',
}: InterviewerCharacterProps) {
  const [blink, setBlink]           = useState(false)
  const [speakFrame, setSpeakFrame] = useState(0)
  const blinkRef = useRef<ReturnType<typeof setTimeout>  | null>(null)
  const speakRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (state === 'hidden' || state === 'transition') return
    const schedule = () => {
      const delay = 2600 + Math.random() * 3600
      blinkRef.current = setTimeout(() => {
        setBlink(true)
        setTimeout(() => setBlink(false), 140)
        schedule()
      }, delay)
    }
    schedule()
    return () => { if (blinkRef.current) clearTimeout(blinkRef.current) }
  }, [state])

  useEffect(() => {
    if (state !== 'speaking') { setSpeakFrame(0); return }
    speakRef.current = setInterval(() => {
      setSpeakFrame(f => (f + 1) % SPEAK_SEQ.length)
    }, 210)
    return () => { if (speakRef.current) clearInterval(speakRef.current) }
  }, [state])

  if (state === 'hidden') return null

  const { width, height } = SIZE_DIMS[size]

  return (
    <div
      className={[
        'interviewer-character',
        `interviewer-character--${size}`,
        `interviewer-character--${state}`,
        className,
      ].filter(Boolean).join(' ')}
      style={{ width, height }}
      aria-hidden="true"
      data-character-state={state}
      data-character-variant="arab"
    >
      <SVGCharacter state={state} blink={blink} speakFrame={speakFrame} />
      {presence && (state === 'thinking' || state === 'speaking') && (
        <div className={`ic-presence ic-presence--${state}`} aria-hidden="true">
          <div className="ic-presence__dot" />
          <div className="ic-presence__dot" />
          <div className="ic-presence__dot" />
        </div>
      )}
    </div>
  )
}
