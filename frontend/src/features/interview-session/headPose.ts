/**
 * Part 2 (docs/CURRENT_DECISIONS.md's "Proctoring Part 2 — head-pose
 * detection scope"): pure decomposition of `@mediapipe/tasks-vision`
 * FaceLandmarker's `facialTransformationMatrixes[i]` into Euler-style
 * angles, kept in its own file so it's testable in isolation from the
 * DOM/video/WASM pipeline in useFaceDetectionMonitor.ts.
 *
 * Real, confirmed API shape (node_modules/@mediapipe/tasks-vision/
 * vision.d.ts): `Matrix { rows: 4, columns: 4, data: number[] }`, a flat
 * 16-number array. The library's own bundled source
 * (vision_bundle.mjs) copies `rows`/`columns`/`data` straight off the
 * underlying protobuf with no transpose -- so the storage order is
 * whatever MediaPipe's native face-geometry pipeline produces natively,
 * not something this project chose.
 *
 * Layout assumption (column-major) — reasoned, not verified against a
 * live capture yet: the type's own doc comment says this matrix "is used
 * to transform the face landmarks in canonical face to the detected
 * face, so that users can apply face effects on the detected landmarks"
 * -- i.e. its stated purpose is feeding a WebGL/3D-engine model matrix,
 * which is uniformly column-major convention (this is also the
 * convention every public MediaPipe face-effect/head-pose sample project
 * uses when consuming this exact field). Extraction below reproduces the
 * standard, widely-published 'XYZ'-order rotation-matrix-to-Euler-angle
 * algorithm (the same one three.js's Euler.setFromRotationMatrix('XYZ')
 * implements) -- a well-established piece of linear algebra, not
 * MediaPipe-specific guesswork.
 *
 * REMAINING UNCERTAINTY, explicit rather than papered over: which of the
 * three returned angles best isolates "nodding down at a phone in the
 * lap" and its sign has NOT yet been confirmed against a real captured
 * matrix from a live camera (this sandbox's Browser pane blocks camera
 * access, same limitation PR-D hit). useFaceDetectionMonitor.ts logs all
 * three during the verification pass so a real test can confirm which
 * axis moves and in which direction before HEAD_DOWN_SUSPECTED's
 * threshold is trusted.
 */

export interface HeadPoseAngles {
  /** Rotation about the model's local X axis -- expected to be "nod
   *  up/down" if the canonical face model is X-right/Y-up/Z-toward-
   *  camera, MediaPipe's documented canonical_face_model convention. */
  pitchDegrees: number;
  /** Rotation about the local Y axis -- expected to be "turn left/right". */
  yawDegrees: number;
  /** Rotation about the local Z axis -- expected to be "tilt ear to
   *  shoulder". */
  rollDegrees: number;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/**
 * Decomposes a MediaPipe `Matrix` (4x4, column-major, see module
 * docstring) into XYZ Euler angles in degrees. Pure function, no DOM/WASM
 * dependency -- safe to unit test with hand-constructed matrices.
 */
export function decomposeHeadPose(matrix: { rows: number; columns: number; data: number[] }): HeadPoseAngles {
  if (matrix.rows !== 4 || matrix.columns !== 4 || matrix.data.length !== 16) {
    throw new Error(`decomposeHeadPose: expected a 4x4/16-element matrix, got ${matrix.rows}x${matrix.columns}/${matrix.data.length}`);
  }
  const d = matrix.data;
  // Column-major 4x4 -> mathematical R[row][col] = d[col*4 + row].
  const m11 = d[0], m21 = d[1], m31 = d[2];
  const m12 = d[4], m22 = d[5], m32 = d[6];
  const m13 = d[8], m23 = d[9], m33 = d[10];

  // Standard 'XYZ'-order Euler extraction from a rotation matrix (the
  // same algorithm three.js's Euler.setFromRotationMatrix('XYZ') uses,
  // reproduced here rather than importing a 3D engine for one function).
  let x: number, y: number, z: number;
  y = Math.asin(clamp(m13, -1, 1));
  if (Math.abs(m13) < 0.9999999) {
    x = Math.atan2(-m23, m33);
    z = Math.atan2(-m12, m11);
  } else {
    // Gimbal lock -- looking almost exactly along the local X axis.
    // Not a realistic head pose during an interview, but handled so this
    // never NaNs out on an extreme/degenerate detection.
    x = Math.atan2(m32, m22);
    z = 0;
  }

  const toDegrees = (radians: number) => (radians * 180) / Math.PI;
  return { pitchDegrees: toDegrees(x), yawDegrees: toDegrees(y), rollDegrees: toDegrees(z) };
}
