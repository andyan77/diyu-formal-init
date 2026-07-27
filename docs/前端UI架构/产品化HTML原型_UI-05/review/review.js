(() => {
  "use strict";

  const pages = [
    ["租户管理概览", "../product/admin-overview.html"],
    ["团队使用", "../product/team-usage.html"],
    ["成员与入口资格", "../product/members.html"],
    ["发布账号详情", "../product/publishing-account.html"],
    ["品牌资料库", "../product/brand-library.html"],
    ["当前可用与待补", "../product/readiness.html"],
    ["内容创作空状态", "../product/creator-empty.html"],
    ["生成过程与完整成品", "../product/creator-generating.html"],
  ];

  const one = (selector) => document.querySelector(selector);
  const all = (selector) => [...document.querySelectorAll(selector)];
  const list = one("[data-page-list]");
  const frame = one("[data-review-frame]");
  const canvas = one("[data-review-canvas]");
  const title = one("[data-review-title]");
  const position = one("[data-review-position]");
  const openRaw = one("[data-open-raw]");
  let current = 0;

  list.innerHTML = pages
    .map(([label], index) => `<button type="button" data-page="${index}">${index + 1}. ${label}</button>`)
    .join("");

  const show = (index) => {
    current = (index + pages.length) % pages.length;
    const [label, href] = pages[current];
    frame.src = href;
    title.textContent = label;
    position.textContent = `${current + 1} / ${pages.length}`;
    openRaw.href = href;
    all("[data-page]").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.page) === current);
    });
  };

  list.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-page]");
    if (trigger) show(Number(trigger.dataset.page));
  });
  one("[data-prev]").addEventListener("click", () => show(current - 1));
  one("[data-next]").addEventListener("click", () => show(current + 1));
  one("[data-desktop]").addEventListener("click", () => {
    canvas.classList.remove("mobile");
    all("[data-viewport]").forEach((button) => button.classList.toggle("active", button.dataset.viewport === "desktop"));
  });
  one("[data-mobile]").addEventListener("click", () => {
    canvas.classList.add("mobile");
    all("[data-viewport]").forEach((button) => button.classList.toggle("active", button.dataset.viewport === "mobile"));
  });
  document.addEventListener("keydown", (event) => {
    if (event.altKey && event.key === "ArrowRight") show(current + 1);
    if (event.altKey && event.key === "ArrowLeft") show(current - 1);
  });

  show(0);
})();
