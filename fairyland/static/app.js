/* Fairyland — frontend interaction loop */

(function () {
  "use strict";

  let sessionId = null;
  let state = "init"; // init, handshake, active
  let debugVisible = false;
  let hudTapCount = 0;
  let hudTapTimer = null;

  const $ = (sel) => document.querySelector(sel);
  const messages = $("#messages");
  const input = $("#user-input");
  const breathRing = $("#breath-ring");
  const breathIcon = $("#breath-icon");
  const modeSelect = $("#mode-select");
  const anchorEl = $("#anchor");
  const pipOverlay = $("#pip-overlay");
  const hudMode = $("#hud-mode");
  const hudWeather = $("#hud-weather");
  const debugEl = $("#debug");

  // -- Session Management --------------------------------------------------

  async function createSession(mode) {
    const res = await fetch("/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    const data = await res.json();
    sessionId = data.session_id;
    return data;
  }

  async function sendStep(text) {
    const res = await fetch("/step", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, text }),
    });
    return res.json();
  }

  // -- Rendering -----------------------------------------------------------

  function addMessage(text, cls) {
    const div = document.createElement("div");
    div.className = "msg " + cls;
    div.textContent = text;
    messages.appendChild(div);
    // keep only last 20 messages visible
    while (messages.children.length > 20) {
      messages.removeChild(messages.firstChild);
    }
    div.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function updateBreath(breathData) {
    const st = (breathData.state || "CALM").toLowerCase();
    breathRing.className = "breath " + st;
    breathIcon.textContent = breathData.icon || "○";

    // haptic feedback if supported
    if (navigator.vibrate) {
      if (st === "calm") navigator.vibrate(80);
      else if (st === "flow") navigator.vibrate([40, 30, 40]);
      else if (st === "edge") navigator.vibrate([20, 10, 20]);
      // overdrive = silence, no vibration
    }
  }

  function showAnchor(word) {
    if (!word) {
      anchorEl.classList.add("hidden");
      return;
    }
    anchorEl.textContent = word;
    anchorEl.classList.remove("hidden");
    // anchor dissolves after 8 seconds if not interacted with
    setTimeout(() => anchorEl.classList.add("hidden"), 8000);
  }

  function showPipSilence() {
    pipOverlay.classList.remove("hidden");
    setTimeout(() => pipOverlay.classList.add("hidden"), 3000);
  }

  function updateHud(data) {
    if (data.oscillator_mode) {
      hudMode.textContent = data.oscillator_mode.toLowerCase();
    }
    if (data.weather) {
      const w = data.weather;
      hudWeather.textContent = `${w.rhythm} · ${w.tension} · ${w.flow}`;
    }
  }

  function updateDebug(data) {
    if (!debugVisible) return;
    const snap = data.snapshot || {};
    const sig = data.signals || {};
    debugEl.textContent =
      `phi:${snap.oscillator_phi || "?"} p:${snap.pressure || "?"} ` +
      `c:${snap.coherence || "?"} g:${snap.groove || "?"} ` +
      `s:${snap.stress || "?"} r:${snap.reserve || "?"} t:${snap.temperature || "?"}\n` +
      `tone:${sig.tone || "-"} rhythm:${sig.rhythm || "-"} ` +
      `rep:${sig.repetition || "-"} traj:${sig.trajectory || "-"}`;
  }

  // -- Interaction Loop ----------------------------------------------------

  async function handleInput(text) {
    if (!text.trim()) return;
    input.value = "";

    if (state === "init") {
      // first message starts handshake
      const sessionData = await createSession("ADULT");
      state = "handshake";
    }

    addMessage(text, "user");

    const data = await sendStep(text);

    // pip silence check
    if (data.pip_active) {
      showPipSilence();
      return;
    }

    // main response
    if (data.text) {
      addMessage(data.text, "system");
    }

    // ritual question
    if (data.ritual_question && data.ritual_question !== data.text) {
      addMessage(data.ritual_question, "ritual");
    }

    // intervention
    if (data.intervention) {
      addMessage(data.intervention, "intervention");
    }

    // drift nudge
    if (data.drift_nudge) {
      addMessage(data.drift_nudge, "nudge");
    }

    // breath
    if (data.breath) {
      updateBreath(data.breath);
    }

    // anchor
    showAnchor(data.anchor);

    // HUD
    updateHud(data);

    // debug
    updateDebug(data);

    // after handshake, move to active
    if (state === "handshake" && data.state !== "HANDSHAKE") {
      state = "active";
      modeSelect.classList.add("hidden");
    }
  }

  // -- Mode Selection ------------------------------------------------------

  function initModeSelect() {
    modeSelect.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const mode = btn.dataset.mode;
        await createSession(mode);
        state = "handshake";
        modeSelect.classList.add("hidden");
        addMessage(`${mode.toLowerCase()} mode`, "system");
        // send initial handshake
        const data = await sendStep(`I'm in ${mode.toLowerCase()} mode`);
        if (data.text) addMessage(data.text, "system");
        if (data.breath) updateBreath(data.breath);
        updateHud(data);
        state = "active";
      });
    });
  }

  // -- Event Listeners -----------------------------------------------------

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleInput(input.value);
    }
  });

  // triple-tap HUD to toggle debug
  $("#hud").addEventListener("click", () => {
    hudTapCount++;
    clearTimeout(hudTapTimer);
    hudTapTimer = setTimeout(() => (hudTapCount = 0), 500);
    if (hudTapCount >= 3) {
      debugVisible = !debugVisible;
      debugEl.classList.toggle("hidden", !debugVisible);
      hudTapCount = 0;
    }
  });

  // -- Init ----------------------------------------------------------------

  async function init() {
    // register service worker
    if ("serviceWorker" in navigator) {
      try {
        await navigator.serviceWorker.register("/static/sw.js");
      } catch (e) {
        // SW registration failed — app still works
      }
    }

    // auto-create session
    await createSession("ADULT");
    state = "handshake";

    // show mode selection
    modeSelect.classList.remove("hidden");

    // or just start with a greeting
    addMessage("Welcome. Choose your mode, or just start talking.", "system");
  }

  init();
})();
