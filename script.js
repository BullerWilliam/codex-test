const preview = document.getElementById("preview");
const statusEl = document.getElementById("status");
const streamMetaEl = document.getElementById("stream-meta");

const startCaptureBtn = document.getElementById("start-capture");
const stopCaptureBtn = document.getElementById("stop-capture");
const togglePipBtn = document.getElementById("toggle-pip");
const startRecordBtn = document.getElementById("start-record");
const stopRecordBtn = document.getElementById("stop-record");
const downloadLink = document.getElementById("download-link");

const swatch = document.getElementById("swatch");
const hexColorEl = document.getElementById("hex-color");
const rgbColorEl = document.getElementById("rgb-color");
const copyColorBtn = document.getElementById("copy-color");

let screenStream;
let mediaRecorder;
let recordedChunks = [];
let lastHex = "#000000";

const sampleCanvas = document.createElement("canvas");
const sampleCtx = sampleCanvas.getContext("2d", { willReadFrequently: true });

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function setControlsForStream(active) {
  startCaptureBtn.disabled = active;
  stopCaptureBtn.disabled = !active;
  togglePipBtn.disabled = !active;
  startRecordBtn.disabled = !active;
  if (!active) {
    stopRecordBtn.disabled = true;
    copyColorBtn.disabled = true;
  }
}

function rgbToHex(r, g, b) {
  return `#${[r, g, b].map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

function updateStreamMeta(track) {
  const settings = track.getSettings();
  const width = settings.width || "?";
  const height = settings.height || "?";
  const frameRate = settings.frameRate || "?";
  streamMetaEl.textContent = `Stream info: ${width}x${height} @ ${frameRate}fps`;
}

async function startCapture() {
  if (!navigator.mediaDevices?.getDisplayMedia) {
    setStatus("Your browser does not support screen capture.", true);
    return;
  }

  try {
    screenStream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: { ideal: 30, max: 60 } },
      audio: true
    });

    preview.srcObject = screenStream;
    const [videoTrack] = screenStream.getVideoTracks();

    updateStreamMeta(videoTrack);
    videoTrack.addEventListener("ended", stopCapture);

    setControlsForStream(true);
    copyColorBtn.disabled = false;
    setStatus("Capture started. Click the preview to sample colors.");
  } catch (error) {
    setStatus(`Capture failed: ${error.message}`, true);
  }
}

function stopCapture() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }

  if (screenStream) {
    for (const track of screenStream.getTracks()) {
      track.stop();
    }
  }

  preview.srcObject = null;
  screenStream = undefined;
  setControlsForStream(false);
  streamMetaEl.textContent = "Stream info: not active";
  setStatus("Capture stopped.");
}

function startRecording() {
  if (!screenStream) {
    setStatus("Start a capture before recording.", true);
    return;
  }

  recordedChunks = [];

  try {
    mediaRecorder = new MediaRecorder(screenStream, {
      mimeType: "video/webm;codecs=vp9,opus"
    });
  } catch {
    mediaRecorder = new MediaRecorder(screenStream);
  }

  mediaRecorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size > 0) {
      recordedChunks.push(event.data);
    }
  });

  mediaRecorder.addEventListener("stop", () => {
    const recordingBlob = new Blob(recordedChunks, { type: "video/webm" });
    const objectUrl = URL.createObjectURL(recordingBlob);
    downloadLink.href = objectUrl;
    downloadLink.hidden = false;
    setStatus("Recording finished. You can download the file.");
  });

  mediaRecorder.start(250);
  startRecordBtn.disabled = true;
  stopRecordBtn.disabled = false;
  setStatus("Recording in progress...");
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }

  startRecordBtn.disabled = false;
  stopRecordBtn.disabled = true;
}

async function togglePip() {
  if (!document.pictureInPictureEnabled) {
    setStatus("Picture-in-Picture is not supported in this browser.", true);
    return;
  }

  try {
    if (document.pictureInPictureElement) {
      await document.exitPictureInPicture();
      togglePipBtn.textContent = "Open Picture-in-Picture";
    } else {
      await preview.requestPictureInPicture();
      togglePipBtn.textContent = "Close Picture-in-Picture";
    }
  } catch (error) {
    setStatus(`PiP error: ${error.message}`, true);
  }
}

function sampleColorFromPreview(event) {
  if (!preview.videoWidth || !preview.videoHeight || !sampleCtx) {
    return;
  }

  sampleCanvas.width = preview.videoWidth;
  sampleCanvas.height = preview.videoHeight;
  sampleCtx.drawImage(preview, 0, 0, preview.videoWidth, preview.videoHeight);

  const bounds = preview.getBoundingClientRect();
  const x = Math.max(0, Math.min(preview.videoWidth - 1, Math.floor(((event.clientX - bounds.left) / bounds.width) * preview.videoWidth)));
  const y = Math.max(0, Math.min(preview.videoHeight - 1, Math.floor(((event.clientY - bounds.top) / bounds.height) * preview.videoHeight)));

  const [r, g, b] = sampleCtx.getImageData(x, y, 1, 1).data;
  lastHex = rgbToHex(r, g, b);

  swatch.style.backgroundColor = lastHex;
  hexColorEl.textContent = lastHex;
  rgbColorEl.textContent = `rgb(${r}, ${g}, ${b})`;
  setStatus(`Picked color ${lastHex}`);
}

async function copyHexColor() {
  try {
    await navigator.clipboard.writeText(lastHex);
    setStatus(`Copied ${lastHex} to clipboard.`);
  } catch {
    setStatus(`Could not copy automatically. Color: ${lastHex}`, true);
  }
}

startCaptureBtn.addEventListener("click", startCapture);
stopCaptureBtn.addEventListener("click", stopCapture);
startRecordBtn.addEventListener("click", startRecording);
stopRecordBtn.addEventListener("click", stopRecording);
togglePipBtn.addEventListener("click", togglePip);
copyColorBtn.addEventListener("click", copyHexColor);
preview.addEventListener("click", sampleColorFromPreview);
