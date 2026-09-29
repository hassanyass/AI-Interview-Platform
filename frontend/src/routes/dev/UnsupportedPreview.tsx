import { UnsupportedDeviceScreen } from "../../features/interview-session/UnsupportedDeviceScreen";

/**
 * DEV-ONLY harness for the device gate added in R5 (product decision D1).
 *
 * The gate itself only appears on a device that cannot take the interview,
 * which is exactly the device the screenshot harness is not running on — so
 * this route renders the screen directly. The *rule* that decides when it
 * shows is covered by `src/lib/deviceSupport.test.ts`, which can express an
 * iPhone and an Android phone that no harness viewport can.
 *
 * `IntroScreen` itself is deliberately not previewed here: it mounts
 * `DevicePreview`, which asks for camera and microphone access, so a
 * headless shot would only ever capture the permission-denied branch.
 */
export default function UnsupportedPreview() {
  return (
    <div>
      <div
        data-responsive-ignore
        className="border-b bg-amber-50 px-4 py-1.5 text-xs text-amber-800"
      >
        <strong>DEV PREVIEW</strong> — the D1 device gate, shown in place of the pre-flight screen.
      </div>
      <UnsupportedDeviceScreen onEnd={() => {}} />
    </div>
  );
}
