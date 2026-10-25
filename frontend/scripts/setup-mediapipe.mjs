/*
 * setup-mediapipe.mjs — puts the face-tracking files in public/mediapipe so eye tracking
 * works offline. Run from the frontend folder:   npm run setup-mediapipe
 *
 * 1. copies node_modules/@mediapipe/tasks-vision/wasm  ->  public/mediapipe/wasm
 * 2. downloads face_landmarker.task (needs internet once) and checks it is a real model file
 */
import { cp, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC_WASM = path.join(ROOT, "node_modules", "@mediapipe", "tasks-vision", "wasm");
const OUT_DIR = path.join(ROOT, "public", "mediapipe");
const OUT_WASM = path.join(OUT_DIR, "wasm");
const OUT_MODEL = path.join(OUT_DIR, "face_landmarker.task");

// A .task file is model data with a zip archive at the END, so look for the zip
// "end of archive" marker (PK 05 06) in the last 64 KB instead of checking the first bytes.
function isModel(buf) {
  if (!buf || buf.length < 1_000_000) return false;
  const stop = Math.max(0, buf.length - 66_000);
  for (let i = buf.length - 22; i >= stop; i -= 1) {
    if (buf[i] === 0x50 && buf[i + 1] === 0x4b && buf[i + 2] === 0x05 && buf[i + 3] === 0x06) return true;
  }
  return false;
}
const mb = (n) => (n / 1024 / 1024).toFixed(1) + " MB";

async function main() {
  console.log("1/2  Copying the MediaPipe runtime files...");
  if (!existsSync(SRC_WASM)) {
    console.error("     [FAIL] node_modules/@mediapipe/tasks-vision is missing. Run:  npm install");
    process.exit(1);
  }
  await mkdir(OUT_DIR, { recursive: true });
  await rm(OUT_WASM, { recursive: true, force: true });
  await cp(SRC_WASM, OUT_WASM, { recursive: true });
  const wasmFile = path.join(OUT_WASM, "vision_wasm_internal.wasm");
  console.log(`     [OK] public/mediapipe/wasm  (vision_wasm_internal.wasm ${mb((await stat(wasmFile)).size)})`);

  console.log("2/2  Face-tracking model...");
  if (existsSync(OUT_MODEL)) {
    const current = await readFile(OUT_MODEL);
    if (isModel(current)) {
      console.log(`     [OK] already present and valid (${mb(current.length)})`);
      return done();
    }
    console.log(`     Existing file is broken (${current.length} bytes) — downloading again.`);
    await rm(OUT_MODEL, { force: true });
  }

  let data;
  try {
    const res = await fetch(MODEL_URL);
    if (!res.ok) throw new Error(`server answered ${res.status}`);
    data = Buffer.from(await res.arrayBuffer());
  } catch (err) {
    console.error(`     [FAIL] download failed: ${err.message}`);
    console.error("     Connect to the internet (college Wi-Fi may block it — try a phone hotspot) and run again.");
    process.exit(1);
  }
  if (!isModel(data)) {
    console.error(`     [FAIL] the download is not a model file (${data.length} bytes). A network login page may have`);
    console.error("     blocked it. Try a different network and run again.");
    process.exit(1);
  }
  await writeFile(OUT_MODEL, data);
  console.log(`     [OK] public/mediapipe/face_landmarker.task (${mb(data.length)})`);
  done();
}

function done() {
  console.log("\nDone. Restart  npm run dev  and reload the page (Ctrl + Shift + R).");
}

main().catch((err) => {
  console.error("[FAIL]", err.message);
  process.exit(1);
});
