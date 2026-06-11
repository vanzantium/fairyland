/* Parent Peek — three words of weather, refreshed quietly.
 *
 * No content. No history. No recommendations. If the viewer starts
 * prodding at the page for more than the weather, Pip closes it:
 * (.) then exit. The weather is the whole report.
 */

(function () {
  "use strict";

  const sky = document.getElementById("sky");
  const quiet = document.getElementById("quiet");
  const pipOverlay = document.getElementById("pip-overlay");
  const words = {
    rhythm: document.getElementById("w-rhythm"),
    tension: document.getElementById("w-tension"),
    flow: document.getElementById("w-flow"),
  };

  let taps = 0;
  let tapTimer = null;
  let closed = false;

  // -- weather ----------------------------------------------------------------

  async function refresh() {
    if (closed) return;
    try {
      const res = await fetch("/weather/current");
      const data = await res.json();
      if (!data.present || !data.weather) {
        quiet.classList.remove("hidden");
        quiet.classList.add("active");
        return;
      }
      quiet.classList.remove("active");
      quiet.classList.add("hidden");
      words.rhythm.textContent = data.weather.rhythm || "—";
      words.tension.textContent = data.weather.tension || "—";
      words.flow.textContent = data.weather.flow || "—";
    } catch (err) {
      // server gone: the sky goes quiet
      quiet.classList.remove("hidden");
      quiet.classList.add("active");
    }
  }

  refresh();
  setInterval(refresh, 10000);

  // -- extraction guard ---------------------------------------------------------

  // tapping around the page looking for more than the weather
  // counts as trying to extract meaning. pip (.) then exit.
  document.body.addEventListener("pointerdown", () => {
    if (closed) return;
    taps += 1;
    clearTimeout(tapTimer);
    tapTimer = setTimeout(() => { taps = 0; }, 4000);
    if (taps >= 5) {
      pipClose();
    }
  });

  function pipClose() {
    closed = true;
    sky.classList.add("faded");
    pipOverlay.classList.remove("hidden");
    pipOverlay.classList.add("active");
    setTimeout(() => {
      window.location.href = "/";
    }, 2500);
  }

  // installable alongside the canvas (root scope)
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
})();
