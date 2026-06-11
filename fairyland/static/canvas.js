/* Fairyland canvas — touch = mark. No presets. No scores. No replay.
 *
 * The client draws locally and sends only rhythm telemetry: timestamps,
 * normalised positions, stroke lengths. The marks themselves never leave
 * the device. At session end the web is eaten — canvas cleared, session
 * burned server-side.
 */

(function () {
  "use strict";

  const paper = document.getElementById("paper");
  const ctx = paper.getContext("2d");
  const breathRing = document.getElementById("breath-ring");
  const breathIcon = document.getElementById("breath-icon");
  const anchorEl = document.getElementById("anchor");
  const pipOverlay = document.getElementById("pip-overlay");
  const leaveBtn = document.getElementById("leave");
  const eatenEl = document.getElementById("eaten");

  let sessionId = null;
  let marks = [];           // telemetry batch (rhythm only — not the drawing)
  let drawing = false;
  let stroke = null;        // current stroke accumulator
  let pipActive = false;
  let ending = false;
  let anchorTimer = null;
  let lastPoint = null;

  const BATCH_MS = 2500;    // telemetry cadence
  const diag = () => Math.hypot(window.innerWidth, window.innerHeight);

  // -- canvas sizing --------------------------------------------------------

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    paper.width = window.innerWidth * dpr;
    paper.height = window.innerHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
  }
  window.addEventListener("resize", resize);
  resize();

  // -- session ----------------------------------------------------------------

  async function ensureSession() {
    if (sessionId) return sessionId;
    const res = await fetch("/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "KID" }),
    });
    const data = await res.json();
    sessionId = data.session_id;
    return sessionId;
  }

  // -- drawing ------------------------------------------------------------------

  function inkStyle() {
    // soft ink; slightly fainter under edge so the surface itself slows
    const edge = document.body.classList.contains("edge");
    ctx.strokeStyle = edge ? "rgba(212, 208, 200, 0.35)" : "rgba(212, 208, 200, 0.6)";
    ctx.lineWidth = edge ? 2.2 : 3.0;
  }

  function pointerDown(e) {
    if (pipActive || ending) return;
    drawing = true;
    lastPoint = { x: e.clientX, y: e.clientY };
    stroke = {
      t: performance.now(),
      x: e.clientX / window.innerWidth,
      y: e.clientY / window.innerHeight,
      len: 0,
    };
    ctx.beginPath();
    ctx.moveTo(e.clientX, e.clientY);
  }

  function pointerMove(e) {
    if (!drawing || pipActive || ending) return;
    inkStyle();
    ctx.lineTo(e.clientX, e.clientY);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(e.clientX, e.clientY);
    if (lastPoint) {
      stroke.len += Math.hypot(e.clientX - lastPoint.x, e.clientY - lastPoint.y);
    }
    lastPoint = { x: e.clientX, y: e.clientY };
  }

  function pointerUp() {
    if (!drawing) return;
    drawing = false;
    if (stroke) {
      marks.push({
        t: stroke.t,
        x: stroke.x,
        y: stroke.y,
        len: stroke.len / diag(),
        dur: performance.now() - stroke.t,
      });
      stroke = null;
    }
    lastPoint = null;
  }

  paper.addEventListener("pointerdown", pointerDown);
  paper.addEventListener("pointermove", pointerMove);
  paper.addEventListener("pointerup", pointerUp);
  paper.addEventListener("pointercancel", pointerUp);
  paper.addEventListener("pointerleave", pointerUp);

  // -- breath -------------------------------------------------------------------

  const HAPTICS = {
    long_low: [400],
    gentle_wave: [150, 80, 150],
    short_double_tap: [50, 50, 50],
    silence: null,
  };

  function updateBreath(breath) {
    const st = (breath.state || "CALM").toLowerCase();
    breathRing.className = st;
    breathIcon.textContent = breath.icon || "○";

    document.body.classList.toggle("edge", st === "edge");

    const pattern = HAPTICS[breath.haptic];
    if (pattern && navigator.vibrate) {
      navigator.vibrate(pattern);
    }
    // no vibration on silence — silence is the signal
  }

  // -- pip interrupt --------------------------------------------------------------

  function pipSilence() {
    pipActive = true;
    drawing = false;
    pipOverlay.classList.remove("hidden");
    pipOverlay.classList.add("active");
    if (navigator.vibrate) navigator.vibrate(0); // cancel any buzz
    setTimeout(() => {
      pipOverlay.classList.remove("active");
      pipOverlay.classList.add("hidden");
      pipActive = false;
    }, 3000);
  }

  // -- anchor ----------------------------------------------------------------------

  function showAnchor(word) {
    if (!word) return;
    anchorEl.textContent = word;
    anchorEl.classList.remove("hidden");
    anchorEl.classList.add("visible");
    clearTimeout(anchorTimer);
    // dissolves if ignored — no logging, no tap target
    anchorTimer = setTimeout(() => {
      anchorEl.classList.remove("visible");
      anchorEl.classList.add("hidden");
    }, 8000);
  }

  // -- telemetry loop ---------------------------------------------------------------

  async function sendRhythm() {
    if (ending) return;
    try {
      const sid = await ensureSession();
      const batch = marks;
      marks = [];
      const res = await fetch("/rhythm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid, marks: batch }),
      });
      const data = await res.json();

      if (data.breath) updateBreath(data.breath);
      if (data.pip_active) pipSilence();
      if (data.anchor) showAnchor(data.anchor);
    } catch (err) {
      // offline or server gone: the paper still works. fail silent.
    }
  }

  setInterval(sendRhythm, BATCH_MS);

  // -- the web is eaten ----------------------------------------------------------------

  async function eatTheWeb() {
    if (ending) return;
    ending = true;

    // strokes are consumed: progressive fade to black
    let alpha = 0;
    const fade = setInterval(() => {
      alpha += 0.06;
      ctx.fillStyle = `rgba(10, 10, 10, ${Math.min(alpha, 0.35)})`;
      ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);
      if (alpha >= 1.4) {
        clearInterval(fade);
        ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      }
    }, 120);

    eatenEl.querySelector("span").textContent = "";
    eatenEl.classList.remove("hidden");
    eatenEl.classList.add("active");

    try {
      if (sessionId) {
        await fetch("/burn", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId }),
        });
      }
    } catch (err) { /* burning is best-effort; nothing was stored anyway */ }

    sessionId = null;
    marks = [];

    // rest, then return to blank paper — a fresh web on next touch
    setTimeout(() => {
      eatenEl.classList.remove("active");
      eatenEl.classList.add("hidden");
      ending = false;
      breathRing.className = "calm";
      breathIcon.textContent = "○";
      document.body.classList.remove("edge");
    }, 4000);
  }

  leaveBtn.addEventListener("click", eatTheWeb);

  // burn on real exit too — sendBeacon survives page close
  window.addEventListener("pagehide", () => {
    if (sessionId && navigator.sendBeacon) {
      navigator.sendBeacon(
        "/burn",
        new Blob([JSON.stringify({ session_id: sessionId })], { type: "application/json" })
      );
    }
  });
})();
