/// <reference types="vite/client" />

// Every VITE_* variable the app reads (frontend/.env.example, src/config.ts).
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string;
  readonly VITE_FACE_DETECTION_INTERVAL_SECONDS?: string;
  readonly VITE_HEAD_DOWN_CONFIRM_THRESHOLD?: string;
  readonly VITE_HEAD_DOWN_PITCH_THRESHOLD_DEGREES?: string;
  readonly VITE_HEAD_POSE_DEBUG?: string;
}
