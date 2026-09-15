import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { Maximize2, Minimize2, VideoOff } from "lucide-react";

/**
 * Self-view (picture-in-picture) of the candidate's own camera during a
 * live interview -- the same "see yourself, like a real meeting" widget
 * every video-call app has. Takes the RAW MediaStreamTrack, not a LiveKit
 * TrackReference -- same shape as useFaceDetectionMonitor's `cameraTrack`
 * prop, and for the same reason: this is the room's own already-published
 * local camera track (InterviewSession.tsx's <LiveKitRoom video={true}>,
 * tied to the recording consent already given -- PR-C), never a second
 * getUserMedia() call.
 *
 * Preview only, by explicit product decision (2026-09-14): no camera
 * on/off control here. Camera stays on for the whole interview exactly as
 * already designed; this widget only makes that existing state visible to
 * the candidate, it doesn't add a way to opt out of it mid-interview.
 *
 * Positioning: fixed bottom-right of the viewport by default (clearing
 * the sticky controller bar's height), freely draggable anywhere after
 * that -- once dragged, the candidate's own placement wins and is never
 * snapped back, including across an expand/collapse toggle (only
 * reclamped to stay on-screen, never re-defaulted).
 *
 * BUG FIX (2026-09-14, real regression from the first drag-enabled pass):
 * the <video> element must mount UNCONDITIONALLY whenever cameraTrack
 * exists, not conditionally on `position` being computed yet -- the
 * effect that attaches the stream to it only depends on `cameraTrack`
 * (which never changes after mount), so if the video element didn't
 * exist in the DOM the first time that effect ran, it would never get
 * attached at all (dark screen, no re-run to fix it). Exactly the same
 * "<video> not in the DOM yet" hazard DevicePreview.tsx already documents
 * and avoids -- this component broke that guarantee by gating render on
 * a second, independently-changing piece of state. Fixed by always
 * rendering the <video> once a track exists, and only using `position`
 * to decide where on screen it sits (visually hidden off-canvas for the
 * one frame before layout is measured, never unmounted).
 *
 * Renders nothing at all when there's no camera track -- consistent with
 * this app's existing graceful-degradation stance (camera denied/
 * unavailable just means no camera-dependent UI appears, not an error
 * state to explain).
 */

const BOTTOM_MARGIN_PX = 110; // clears the sticky controller bar's height + a gap
const SIDE_MARGIN_PX = 16;
const COLLAPSED_SIZE = { width: 160, height: 112 }; // matches w-40 h-28 at sm+
const EXPANDED_SIZE = { width: 320, height: 256 }; // matches w-80 h-64 at sm+
const VIEWPORT_MARGIN_PX = 8;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function SelfViewVideo({ cameraTrack }: { cameraTrack: MediaStreamTrack | null | undefined }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const hasBeenDraggedRef = useRef(false);
  const dragStateRef = useRef<{ pointerId: number; startX: number; startY: number; originTop: number; originLeft: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const size = isExpanded ? EXPANDED_SIZE : COLLAPSED_SIZE;

  const clampToViewport = useCallback((top: number, left: number, forSize: { width: number; height: number }) => {
    const maxLeft = window.innerWidth - forSize.width - VIEWPORT_MARGIN_PX;
    const maxTop = window.innerHeight - forSize.height - VIEWPORT_MARGIN_PX;
    return {
      top: clamp(top, VIEWPORT_MARGIN_PX, Math.max(VIEWPORT_MARGIN_PX, maxTop)),
      left: clamp(left, VIEWPORT_MARGIN_PX, Math.max(VIEWPORT_MARGIN_PX, maxLeft)),
    };
  }, []);

  // Default: fixed bottom-right of the viewport. Recomputed on resize and
  // on expand/collapse -- but ONLY until the candidate actually drags it,
  // at which point their placement wins from then on (reclamped to stay
  // on-screen, never re-defaulted to the corner).
  useLayoutEffect(() => {
    const reposition = () => {
      if (hasBeenDraggedRef.current) {
        setPosition((prev) => (prev ? clampToViewport(prev.top, prev.left, size) : prev));
        return;
      }
      const top = window.innerHeight - size.height - BOTTOM_MARGIN_PX;
      const left = window.innerWidth - size.width - SIDE_MARGIN_PX;
      setPosition(clampToViewport(top, left, size));
    };

    reposition();
    window.addEventListener("resize", reposition);
    return () => window.removeEventListener("resize", reposition);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isExpanded, clampToViewport]);

  // Attach the stream as soon as the track exists -- independent of
  // `position`, so this never races against the video element mounting.
  // See the module docstring's BUG FIX note for why this matters.
  useLayoutEffect(() => {
    const video = videoRef.current;
    if (!video || !cameraTrack) return;
    video.srcObject = new MediaStream([cameraTrack]);
    return () => {
      video.srcObject = null;
    };
  }, [cameraTrack]);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!position) return;
    // Let the expand/collapse button's own click through untouched.
    if ((e.target as HTMLElement).closest("[data-selfview-toggle]")) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragStateRef.current = { pointerId: e.pointerId, startX: e.clientX, startY: e.clientY, originTop: position.top, originLeft: position.left };
    setIsDragging(true);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragStateRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    const deltaX = e.clientX - drag.startX;
    const deltaY = e.clientY - drag.startY;
    // A few pixels of jitter shouldn't count as "the candidate moved it" --
    // only commit to drag-mode (and stop auto-realigning) past a small
    // threshold, so a slightly imprecise click on the expand button
    // doesn't accidentally lock in a barely-moved position.
    if (!hasBeenDraggedRef.current && Math.hypot(deltaX, deltaY) > 4) {
      hasBeenDraggedRef.current = true;
    }
    setPosition(clampToViewport(drag.originTop + deltaY, drag.originLeft + deltaX, size));
  };

  const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (dragStateRef.current?.pointerId !== e.pointerId) return;
    dragStateRef.current = null;
    setIsDragging(false);
  };

  if (!cameraTrack) return null;

  // Rendered unconditionally once a track exists (see BUG FIX note) --
  // just visually parked off-canvas for the one frame before `position`
  // is measured, never left unmounted.
  const style = position
    ? { top: position.top, left: position.left, width: size.width, height: size.height }
    : { top: -9999, left: -9999, width: size.width, height: size.height, visibility: "hidden" as const };

  return (
    <div
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      style={style}
      className={`fixed z-30 touch-none select-none overflow-hidden rounded-2xl border border-white/10 bg-slate-900 shadow-lg transition-[width,height] duration-300 ease-out ${
        isDragging ? "cursor-grabbing shadow-2xl" : "cursor-grab"
      }`}
    >
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="h-full w-full object-cover [transform:scaleX(-1)]"
      />

      {/* Camera-off fallback -- the track can exist but be temporarily
          disabled by the platform (not the candidate, see the module
          docstring) without being torn down; a black frame with no
          indication would read as broken, not off. */}
      {!cameraTrack.enabled && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-900 text-slate-500">
          <VideoOff className="h-6 w-6" />
        </div>
      )}

      <button
        type="button"
        data-selfview-toggle
        onClick={() => setIsExpanded((v) => !v)}
        aria-label={isExpanded ? "Shrink self-view" : "Expand self-view"}
        title={isExpanded ? "Shrink" : "Expand"}
        className="absolute end-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/50 text-white/90 backdrop-blur-sm transition-colors hover:bg-black/70"
      >
        {isExpanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}
