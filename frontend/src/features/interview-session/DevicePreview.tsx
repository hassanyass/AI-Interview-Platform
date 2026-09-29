import { useEffect, useRef, useState } from "react";
import { Mic, Video, VideoOff, AlertCircle, CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";

interface DevicePreviewProps {
  onReady: (hasCamera: boolean, hasMic: boolean) => void;
}

export function DevicePreview({ onReady }: DevicePreviewProps) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  // Camera-stays-on fix (2026-09-16): the cleanup below used to read the
  // `stream` STATE, which the mount-time closure captured as null -- so the
  // preview's tracks were never stopped and the camera/mic kept running
  // for the life of the page, through and after the interview (a second
  // capture, independent of LiveKit's, which releaseLocalMedia() could
  // never reach). A ref sees the real stream at cleanup time.
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [micLevel, setMicLevel] = useState(0);
  const [hasCamera, setHasCamera] = useState(false);
  const [hasMic, setHasMic] = useState(false);

  useEffect(() => {
    let active = true;
    let audioContext: AudioContext | null = null;
    let analyzer: AnalyserNode | null = null;
    // TS 5.9+/6 lib typing: getByteFrequencyData wants Uint8Array<ArrayBuffer>,
    // and a bare `Uint8Array` annotation widens to ArrayBufferLike.
    let dataArray: Uint8Array<ArrayBuffer> | null = null;
    let animationFrame: number;

    async function setupDevices() {
      try {
        const mediaStream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: true,
        });

        if (!active) {
          mediaStream.getTracks().forEach(track => track.stop());
          return;
        }

        streamRef.current = mediaStream;
        setStream(mediaStream);
        // NOTE: do NOT set videoRef.current.srcObject here — the <video>
        // element is not in the DOM yet at this point because it renders
        // conditionally on stream state. The dedicated useEffect below
        // reacts to stream changing and sets srcObject once the element exists.

        // Setup audio analyzer for live mic level
        audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
        analyzer = audioContext.createAnalyser();
        analyzer.fftSize = 256;
        const microphone = audioContext.createMediaStreamSource(mediaStream);
        microphone.connect(analyzer);
        dataArray = new Uint8Array(analyzer.frequencyBinCount);

        const checkAudioLevel = () => {
          if (!active || !analyzer || !dataArray) return;
          analyzer.getByteFrequencyData(dataArray);
          let sum = 0;
          for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
          const average = sum / dataArray.length;
          setMicLevel(Math.min(100, Math.round((average / 128) * 100)));
          animationFrame = requestAnimationFrame(checkAudioLevel);
        };
        checkAudioLevel();

        const camOk = mediaStream.getVideoTracks().length > 0;
        const micOk = mediaStream.getAudioTracks().length > 0;
        setHasCamera(camOk);
        setHasMic(micOk);
        onReady(camOk, micOk);

      } catch (err: any) {
        if (!active) return;
        console.error("Failed to get media devices", err);
        setError(t("intro.devices.error") || "Camera/microphone access was denied. The interview will continue without them — audio monitoring still applies.");
        onReady(false, false);
      }
    }

    setupDevices();

    return () => {
      active = false;
      if (animationFrame) cancelAnimationFrame(animationFrame);
      if (audioContext && audioContext.state !== "closed") {
        audioContext.close().catch(console.error);
      }
      const live = streamRef.current;
      streamRef.current = null;
      if (live) {
        live.getTracks().forEach(track => track.stop());
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Assign srcObject reactively — runs after React has committed the <video>
  // element to the DOM (which only happens after setStream triggers a render).
  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  return (
    <div className="grid gap-4 sm:grid-cols-[1fr_auto] items-stretch">
      {/* Camera Preview — taller, no title clutter */}
      <div className="relative overflow-hidden rounded-2xl bg-slate-900 shadow-inner aspect-video sm:aspect-auto sm:min-h-[220px] flex items-center justify-center order-1 sm:order-2 sm:w-72">
        {stream ? (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex flex-col items-center gap-2 text-slate-500">
            <VideoOff className="h-10 w-10" />
            <span className="text-xs font-medium">{t("intro.deviceCheck.waiting")}</span>
          </div>
        )}
        {/* Status pill */}
        <div className={`absolute bottom-3 start-3 flex items-center gap-1.5 rounded-full px-2.5 py-1 backdrop-blur-sm text-[11px] font-semibold ${hasCamera ? "bg-emerald-600/90 text-white" : "bg-black/60 text-slate-300"}`}>
          <Video className="h-3 w-3" />
          {hasCamera ? t("intro.deviceCheck.cameraOn") : t("intro.deviceCheck.cameraOff")}
        </div>
      </div>

      {/* Mic + status — left column */}
      <div className="flex flex-col gap-4 order-2 sm:order-1 sm:flex-1">
        {error ? (
          <div className="flex items-start gap-3 rounded-xl bg-amber-50 p-4 border border-amber-200 flex-1">
            <AlertCircle className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
            <p className="text-sm text-amber-800 leading-relaxed">{error}</p>
          </div>
        ) : (
          <>
            {/* Mic status card */}
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Mic className="h-4 w-4 text-slate-600" />
                  <span className="text-sm font-semibold text-slate-700">{t("intro.deviceCheck.microphone")}</span>
                </div>
                {hasMic && (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                )}
              </div>
              {/* Live level bar */}
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                <div
                  className={`h-full rounded-full transition-all duration-75 ease-out ${micLevel > 60 ? "bg-emerald-500" : micLevel > 20 ? "bg-emerald-400" : "bg-slate-300"}`}
                  style={{ width: `${micLevel}%` }}
                />
              </div>
              <p className="text-xs text-slate-500 mt-2">
                {hasMic ? t("intro.deviceCheck.micSpeak") : t("intro.deviceCheck.micMissing")}
              </p>
            </div>

            {/* Camera status card */}
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Video className="h-4 w-4 text-slate-600" />
                  <span className="text-sm font-semibold text-slate-700">{t("intro.deviceCheck.camera")}</span>
                </div>
                {hasCamera
                  ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  : <AlertCircle className="h-4 w-4 text-amber-500" />
                }
              </div>
              <p className="text-xs text-slate-500 mt-2">
                {hasCamera ? t("intro.deviceCheck.cameraLive") : t("intro.deviceCheck.cameraMissing")}
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
