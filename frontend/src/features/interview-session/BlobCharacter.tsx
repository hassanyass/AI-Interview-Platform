import { useEffect, useRef } from 'react';
import * as blobs2Animate from 'blobs/v2/animate';
import { createAudioAnalyser, type LocalAudioTrack, type RemoteAudioTrack } from 'livekit-client';
import './InterviewerCharacter.css';

export type InterviewerCharacterState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'hidden' | 'transition';

export interface BlobCharacterProps {
  state: InterviewerCharacterState;
  size?: 'small' | 'medium' | 'large';
  className?: string;
  // The agent's live audio track, if any. Sampled directly inside this
  // component's own animation-frame loop (see the audioTrack effect below)
  // rather than as a React-state number passed down from the parent —
  // that used to re-render this whole component tree 30-60x/sec just to
  // carry one float, fighting the canvas animation for the main thread.
  audioTrack?: LocalAudioTrack | RemoteAudioTrack;
}

const SIZE_DIMS = {
  small: { width: 160, height: 248 },
  medium: { width: 240, height: 372 },
  large: { width: 320, height: 496 },
};

// Stable identity constants
const BASE_SEED = 1337;
const EXTRA_POINTS = 4;
const BLOB_SIZE_RATIO = 0.85;

const STATE_CONFIG = {
  idle: { randomness: 2, duration: 4000 },
  listening: { randomness: 3, duration: 3000 },
  thinking: { randomness: 1, duration: 5000 },
  // Base/quiet-moment cadence while speaking — the live audioLevel (see
  // scheduleNextTransition) pushes this down to ~250ms and up in randomness
  // on loud syllables, so this is only what a silent gap between words falls
  // back to, not the typical pace.
  speaking: { randomness: 4, duration: 700 },
};

export default function BlobCharacter({
  state,
  size = 'medium',
  className = '',
  audioTrack,
}: BlobCharacterProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const animPrimary = useRef<any>(null);
  const animSecondary = useRef<any>(null);
  const rafId = useRef<number | null>(null);

  const configRef = useRef(STATE_CONFIG['idle']);
  const forceTransitionRef = useRef<(() => void) | null>(null);
  const stateRef = useRef(state);
  // The cadence actually in use, vs. configRef's target — normally these
  // snap together instantly (see the [state] effect). When speech just
  // ended they're allowed to diverge briefly so scheduleNextTransition can
  // glide the pace from speaking's fast cycle back to idle's slow one
  // instead of cutting straight to it mid-morph.
  const easedConfigRef = useRef(STATE_CONFIG['idle']);
  const easingOutRef = useRef(false);
  // Live agent voice amplitude, sampled fresh every render() frame directly
  // from the analyser below — see the audioTrack effect.
  const audioLevelRef = useRef(0);
  const volumeFnRef = useRef<(() => number) | null>(null);
  const reducedMotionRef = useRef(false);

  // e& Color Theme (Vivid Red to Crimson/Deep Maroon)
  const eCoral = '#ff4d4d';
  const eRed = '#e00003';
  const eMaroon = '#9c0f2e';

  useEffect(() => {
    reducedMotionRef.current = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }, []);

  // Own the analyser directly instead of consuming a React-state number:
  // this is the only piece of state tied to the track itself (which changes
  // rarely — only on (re)publish), so it re-runs far less often than a
  // per-frame value ever could.
  useEffect(() => {
    if (!audioTrack) {
      volumeFnRef.current = null;
      return;
    }
    let cancelled = false;
    let cleanup: (() => Promise<void>) | null = null;
    try {
      const analyser = createAudioAnalyser(audioTrack, { smoothingTimeConstant: 0.8 });
      if (cancelled) {
        analyser.cleanup();
      } else {
        volumeFnRef.current = analyser.calculateVolume;
        cleanup = analyser.cleanup;
      }
    } catch (err) {
      // AudioContext can fail to construct in some environments (e.g. no
      // user-gesture yet) — degrade to a non-audio-reactive blob rather
      // than crash the interview over an avatar animation.
      console.warn('BlobCharacter: audio analyser unavailable', err);
    }
    return () => {
      cancelled = true;
      volumeFnRef.current = null;
      cleanup?.();
    };
  }, [audioTrack]);

  useEffect(() => {
    const prevState = stateRef.current;
    stateRef.current = state;
    if (state === 'hidden' || state === 'transition') return;

    configRef.current = reducedMotionRef.current
      ? { randomness: 1, duration: 8000 }
      : STATE_CONFIG[state] || STATE_CONFIG['idle'];

    const leavingSpeaking = prevState === 'speaking' && state !== 'speaking';
    if (leavingSpeaking && !reducedMotionRef.current) {
        // Don't cut off the in-flight fast/mid-syllable morph — let it
        // finish on its own schedule and have scheduleNextTransition ease
        // the pace down toward idle's cadence over the next few cycles.
        easingOutRef.current = true;
    } else if (forceTransitionRef.current) {
        // Any other transition (most importantly idle/listening/thinking ->
        // speaking, and reduced-motion) still snaps immediately, so picking
        // up speech stays responsive.
        easingOutRef.current = false;
        easedConfigRef.current = configRef.current;
        forceTransitionRef.current();
    }
  }, [state]);

  useEffect(() => {
    if (!canvasRef.current || state === 'hidden') return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const { width: cssWidth, height: cssHeight } = SIZE_DIMS[size];
    
    // We must scale the canvas for high DPI without triggering continuous layout recalculations
    canvas.width = cssWidth * dpr;
    canvas.height = cssHeight * dpr;
    ctx.scale(dpr, dpr);

    if (!animPrimary.current) animPrimary.current = blobs2Animate.canvasPath();
    if (!animSecondary.current) animSecondary.current = blobs2Animate.canvasPath();

    const blobSize = cssWidth * BLOB_SIZE_RATIO;
    const offsetX = (cssWidth - blobSize) / 2;
    // Shift down slightly to balance visually in the container
    const offsetY = (cssHeight - blobSize) / 2 + 10;

    const baseBlobOptions = {
        seed: BASE_SEED,
        extraPoints: EXTRA_POINTS,
        size: blobSize,
    };
    
    const scheduleNextTransition = () => {
       let targetConfig = configRef.current;

       // Sampled fresh at the start of each morph cycle (not on every
       // audioLevel tick — see the [state]-only effect above) so a loud
       // syllable makes THIS cycle faster/wilder and a pause lets it settle
       // back toward the base speaking cadence, without restarting an
       // in-flight transition on every animation frame.
       if (stateRef.current === 'speaking' && !reducedMotionRef.current) {
           const level = audioLevelRef.current;
           targetConfig = {
               randomness: targetConfig.randomness + level * 4,
               duration: Math.max(250, targetConfig.duration - level * 450),
           };
       }

       let currentConfig = targetConfig;
       if (easingOutRef.current) {
           // Glide 40% of the remaining distance toward the target each
           // cycle (a fast cycle right after speech ends, easing longer
           // each time) instead of snapping straight to idle's pace.
           const eased = easedConfigRef.current;
           currentConfig = {
               randomness: eased.randomness + (targetConfig.randomness - eased.randomness) * 0.4,
               duration: eased.duration + (targetConfig.duration - eased.duration) * 0.4,
           };
           if (Math.abs(currentConfig.duration - targetConfig.duration) < 150) {
               easingOutRef.current = false;
           }
       }
       easedConfigRef.current = currentConfig;

       // Varying the seed smoothly rotates the random displacement vectors without changing the base topology
       const nextSeed = Math.random();

       animPrimary.current.transition({
           duration: currentConfig.duration,
           timingFunction: 'ease',
           callback: scheduleNextTransition,
           blobOptions: {
               ...baseBlobOptions,
               randomness: currentConfig.randomness,
               seed: nextSeed,
           },
           canvasOptions: { offsetX, offsetY }
       });

       animSecondary.current.transition({
           duration: currentConfig.duration * 1.4, // Slower transition creates the motion echo trail
           timingFunction: 'ease',
           blobOptions: {
               ...baseBlobOptions,
               randomness: currentConfig.randomness,
               seed: nextSeed,
           },
           canvasOptions: { offsetX, offsetY }
       });
    };

    forceTransitionRef.current = scheduleNextTransition;

    // Start the first transition loop
    scheduleNextTransition();

    const primaryGradient = ctx.createLinearGradient(offsetX, offsetY, offsetX + blobSize, offsetY + blobSize);
    primaryGradient.addColorStop(0, eCoral);
    primaryGradient.addColorStop(0.3, eRed);
    primaryGradient.addColorStop(1, eMaroon);

    const centerX = offsetX + blobSize / 2;
    const centerY = offsetY + blobSize / 2;

    const render = () => {
        ctx.clearRect(0, 0, cssWidth, cssHeight);

        // Sampled fresh from the analyser every single animation frame —
        // same rAF loop that drives the canvas itself, so there's no cross-
        // loop timing skew and no React re-render anywhere in this path.
        // Raw per-frame FFT volume is genuinely noisy at 60fps, and that
        // noise goes straight into a scale transform below — visually reads
        // as shaking — so it's EMA-smoothed here too (a ref update, still
        // free of React; this is just math, not the re-render mechanism
        // that made the old approach expensive).
        const rawLevel = volumeFnRef.current
            ? Math.max(0, Math.min(1, volumeFnRef.current()))
            : 0;
        audioLevelRef.current = audioLevelRef.current * 0.65 + rawLevel * 0.35;

        // Continuous per-frame pulse driven directly off the live TTS
        // waveform — this, not the (much slower) shape-morph cadence above,
        // is what makes the avatar visibly track the agent's voice in real
        // time instead of on a ~1s lag. Deliberately NOT gated on
        // state === 'speaking': the analyser reads ~0 on its own once the
        // track goes quiet, so gating it would instead snap the scale to 1
        // the instant speaking ends — its own small "cut".
        const pulseLevel = reducedMotionRef.current ? 0 : audioLevelRef.current;
        const pulseScale = 1 + pulseLevel * 0.14;

        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.scale(pulseScale, pulseScale);
        ctx.translate(-centerX, -centerY);

        // Draw Secondary Layer (Motion Echo) first so it goes behind
        const secondaryPath = animSecondary.current.renderFrame();
        ctx.fillStyle = primaryGradient;
        ctx.globalAlpha = 0.25;
        ctx.fill(secondaryPath);

        // Draw Primary Layer
        const primaryPath = animPrimary.current.renderFrame();
        ctx.globalAlpha = 1.0;
        ctx.fill(primaryPath);

        ctx.restore();

        rafId.current = requestAnimationFrame(render);
    };

    render();

    return () => {
        if (rafId.current) cancelAnimationFrame(rafId.current);
        forceTransitionRef.current = null;
    };
  }, [size, state === 'hidden']); // Re-initialize only when mounting, unhiding, or resizing

  if (state === 'hidden') return null;

  const { width, height } = SIZE_DIMS[size];

  return (
    <div
      className={['interviewer-character', `interviewer-character--${size}`, `interviewer-character--${state}`, className].filter(Boolean).join(' ')}
      style={{ width, height, position: 'relative' }}
      aria-hidden="true"
      data-character-state={state}
      data-character-variant="blob"
    >
      <canvas
        ref={canvasRef}
        style={{ 
            width: `${width}px`, 
            height: `${height}px`,
            position: 'absolute',
            top: 0,
            left: 0,
            filter: 'drop-shadow(0px 16px 32px rgba(156, 15, 46, 0.3))' 
        }}
      />
    </div>
  );
}
