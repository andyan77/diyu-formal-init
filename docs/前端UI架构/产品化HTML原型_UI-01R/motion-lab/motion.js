(() => {
  "use strict";

  const stage = document.querySelector("[data-motion-stage]");
  if (!stage) return;
  const duration = Number(stage.dataset.duration || 7200);
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let timer = 0;

  function finish() {
    window.clearTimeout(timer);
    stage.classList.add("is-complete");
    stage.dataset.complete = "true";
  }

  function replay() {
    window.clearTimeout(timer);
    stage.classList.remove("is-complete");
    stage.dataset.complete = "false";
    void stage.offsetWidth;
    if (reduce) {
      finish();
      return;
    }
    timer = window.setTimeout(finish, duration);
  }

  stage.addEventListener("click", finish);
  document.querySelector("[data-skip]")?.addEventListener("click", finish);
  document.querySelector("[data-replay]")?.addEventListener("click", replay);
  replay();
})();
