(() => {
  "use strict";

  const one = (selector, root = document) => root.querySelector(selector);
  const all = (selector, root = document) => [...root.querySelectorAll(selector)];
  const body = document.body;
  let toastTimer = 0;

  function showToast(message) {
    const toast = one("[data-toast]");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2200);
  }

  function closeDrawer(drawer) {
    if (!drawer) return;
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    all(".drawer-backdrop").forEach((item) => item.classList.remove("is-open"));
    body.classList.remove("has-overlay");
  }

  function openDrawer(name) {
    const drawer = one(`[data-drawer="${name}"]`);
    if (!drawer) return;
    all(".drawer.is-open").forEach(closeDrawer);
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    one(".drawer-backdrop")?.classList.add("is-open");
    body.classList.add("has-overlay");
    one("input, select, textarea, button", drawer)?.focus();
  }

  all("[data-tabs]").forEach((tabset) => {
    const controls = all("[data-tab]", tabset);
    const scope = tabset.closest("[data-tab-scope]") || document;
    const panels = all("[data-tab-panel]", scope);
    controls.forEach((control) => {
      control.addEventListener("click", () => {
        const name = control.dataset.tab;
        controls.forEach((item) =>
          item.setAttribute("aria-selected", String(item === control)),
        );
        panels.forEach((panel) => {
          panel.hidden = panel.dataset.tabPanel !== name;
        });
      });
    });
  });

  all("[data-chip]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const next = chip.getAttribute("aria-pressed") !== "true";
      chip.setAttribute("aria-pressed", String(next));
    });
  });

  all("[data-open-drawer]").forEach((button) => {
    button.addEventListener("click", () => openDrawer(button.dataset.openDrawer));
  });

  all("[data-close-drawer]").forEach((button) => {
    button.addEventListener("click", () => closeDrawer(button.closest(".drawer")));
  });

  all(".drawer-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", () => {
      all(".drawer.is-open").forEach(closeDrawer);
    });
  });

  all("[data-open-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = one(`#${button.dataset.openDialog}`);
      if (!dialog) return;
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    });
  });

  all("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = button.closest("dialog");
      if (typeof dialog?.close === "function") dialog.close();
      else dialog?.removeAttribute("open");
    });
  });

  all("[data-confirm-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = button.closest("dialog");
      if (typeof dialog?.close === "function") dialog.close();
      else dialog?.removeAttribute("open");
      showToast(button.dataset.confirmDialog || "已完成。");
    });
  });

  all("[data-demo-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      showToast(form.dataset.demoForm || "原型操作已完成。");
    });
  });

  all("[data-demo-action]").forEach((button) => {
    button.addEventListener("click", () => {
      showToast(button.dataset.demoAction || "原型操作已完成。");
    });
  });

  all("[data-copy]").forEach((button) => {
    button.addEventListener("click", () => {
      showToast(button.dataset.copy || "已复制当前内容。");
    });
  });

  all("[data-mobile-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const workbench = button.closest(".workbench");
      if (!workbench) return;
      const view = button.dataset.mobileTab;
      workbench.dataset.mobileView = view;
      all("[data-mobile-tab]", workbench).forEach((item) =>
        item.setAttribute("aria-selected", String(item === button)),
      );
    });
  });

  const animation = one("[data-brand-animation]");
  if (animation) {
    const duration = Number(animation.dataset.durationMs || 7200);
    const homePage = animation.closest(".home-page");
    const skip = one("[data-animation-skip]");
    const replay = one("[data-animation-replay]");
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    let animationTimer = 0;

    const finish = () => {
      window.clearTimeout(animationTimer);
      animation.classList.remove("is-running");
      animation.classList.add("is-complete");
      animation.dataset.complete = "true";
    };

    const start = () => {
      window.clearTimeout(animationTimer);
      animation.classList.remove("is-complete", "is-running");
      homePage?.classList.remove("is-breathing");
      animation.dataset.complete = "false";
      void animation.offsetWidth;
      homePage?.classList.add("is-breathing");
      animation.classList.add("is-running");
      animationTimer = window.setTimeout(finish, duration);
    };

    skip?.addEventListener("click", finish);
    animation.addEventListener("click", finish);
    replay?.addEventListener("click", start);
    if (reduceMotion) finish();
    else start();
  }

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    all(".drawer.is-open").forEach(closeDrawer);
    all("dialog[open]").forEach((dialog) => dialog.close());
  });

  window.DiyuPrototype = {
    showToast,
    openDrawer,
    closeDrawer,
  };
})();
