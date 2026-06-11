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
  const musicBtn = document.getElementById("music");
  const player = document.getElementById("player");

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
    const wasPlaying = !player.paused && !player.ended && player.src;
    if (wasPlaying) player.pause(); // silence is the strongest signal
    setTimeout(() => {
      pipOverlay.classList.remove("active");
      pipOverlay.classList.add("hidden");
      pipActive = false;
      if (wasPlaying && musicState === "playing") player.play().catch(() => {});
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
    stopMusic();

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

  // -- music: the spiral dealer ----------------------------------------------
  //
  // The household's own files, played through the Proper Shuffle:
  // three tracks, enforced silence, one anchor word, then the music
  // ends. Tapping ♪ again while playing stops it early.

  let musicState = "idle"; // idle | playing | silence | done-for-session
  const SILENCE_MS = 15000;

  // -- the ear: feel the music while it plays, settle after -------------------
  //
  // Web Audio taps the playing track: band energies + onsets sampled at
  // ~15 Hz, batched to /listen. Nothing is judged in real time — the
  // impressions accumulate, and meaning settles server-side during the
  // dealer's enforced silence. If Web Audio fails, the music still plays
  // (the organism is deaf, not mute).

  let audioCtx = null;
  let analyser = null;
  let earTimer = null;
  let earFlush = null;
  let packets = [];
  let prevEnergy = 0;

  function openEar() {
    if (analyser) return true;
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtx.createMediaElementSource(player);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      analyser.connect(audioCtx.destination);
      return true;
    } catch (err) {
      analyser = null;
      return false;
    }
  }

  function startListening() {
    if (!openEar()) return;
    if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
    const bins = new Uint8Array(analyser.frequencyBinCount);
    const nyquist = audioCtx.sampleRate / 2;
    const binHz = nyquist / analyser.frequencyBinCount;
    const band = (lo, hi) => {
      let sum = 0, n = 0;
      for (let i = Math.floor(lo / binHz); i < Math.min(Math.ceil(hi / binHz), bins.length); i++) {
        sum += bins[i]; n++;
      }
      return n ? (sum / n) / 255 : 0;
    };
    earTimer = setInterval(() => {
      if (musicState !== "playing" || player.paused) return;
      analyser.getByteFrequencyData(bins);
      const low = band(20, 250), mid = band(250, 2000), high = band(4000, 14000);
      const amp = (low + mid + high) / 3;
      const onset = amp - prevEnergy > 0.07; // energy flux transient
      prevEnergy = amp;
      packets.push({ t: performance.now(), low: +low.toFixed(3), mid: +mid.toFixed(3),
                     high: +high.toFixed(3), amp: +amp.toFixed(3), onset });
    }, 66);
    earFlush = setInterval(flushPackets, 2500);
  }

  async function flushPackets() {
    if (!packets.length || !sessionId) return;
    const batch = packets;
    packets = [];
    try {
      await fetch("/listen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, packets: batch }),
      });
    } catch (err) { /* impressions fade; the music keeps playing */ }
  }

  async function settleListening() {
    clearInterval(earTimer); earTimer = null;
    clearInterval(earFlush); earFlush = null;
    await flushPackets();
    if (!sessionId) return;
    try {
      await fetch("/listen/settle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch (err) { /* the residue simply fades */ }
  }

  async function startMusic() {
    const sid = await ensureSession();
    const listRes = await fetch("/music/list");
    const { tracks } = await listRes.json();

    if (!tracks.length) {
      // nothing in the folder: the note dims, wordlessly
      musicBtn.classList.add("empty");
      setTimeout(() => musicBtn.classList.remove("empty"), 2500);
      return;
    }

    await fetch("/shuffle/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sid, tracks }),
    });

    musicState = "playing";
    musicBtn.classList.add("playing");
    player.volume = 0.6;
    startListening();
    advanceMusic();
  }

  async function advanceMusic() {
    if (musicState !== "playing") return;
    let data;
    try {
      const sid = await ensureSession();
      const res = await fetch("/shuffle/next", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid }),
      });
      data = await res.json();
    } catch (err) {
      stopMusic();
      return;
    }

    if (data.track) {
      player.src = "/music/file/" + encodeURIComponent(data.track.id);
      player.play().catch(() => stopMusic());
      return; // 'ended' listener advances
    }

    if (data.silence) {
      // enforced silence — the dealer rests, and meaning settles
      player.pause();
      player.removeAttribute("src");
      musicState = "silence";
      settleListening(); // the silence is the settle window
      setTimeout(() => {
        if (data.anchor_cue) {
          // after silence -> material anchor. one word, outward.
          const verbs = ["Make", "Sit", "Read", "Walk", "Find"];
          showAnchor(verbs[Math.floor(performance.now() / 1000) % verbs.length]);
        }
        // after the anchor -> exit. one more call returns the exit cue.
        musicState = "playing";
        advanceMusic();
      }, SILENCE_MS);
      return;
    }

    // exit cue (or empty playlist): the music is over for this session
    stopMusic();
  }

  function stopMusic() {
    player.pause();
    player.removeAttribute("src");
    const wasListening = !!earTimer;
    musicState = "idle";
    musicBtn.classList.remove("playing");
    if (wasListening) settleListening(); // stopped early: meaning still settles
  }

  player.addEventListener("ended", () => {
    if (musicState === "playing") advanceMusic();
  });
  player.addEventListener("error", () => {
    if (musicState === "playing") advanceMusic(); // skip unreadable files
  });

  musicBtn.addEventListener("click", () => {
    if (ending) return;
    if (musicState === "idle") startMusic();
    else stopMusic();
  });

  // installable: register the service worker (root scope)
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => { /* paper still works */ });
  }

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
