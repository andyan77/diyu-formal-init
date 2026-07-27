(() => {
  "use strict";

  const journeys = {
    admin: {
      label: "租户管理员旅程",
      pages: [
        ["管理概览", "../product/admin-overview.html"],
        ["团队使用", "../product/team-usage.html"],
        ["成员与互斥入口资格", "../product/members.html"],
        ["发布账号与账号画像", "../product/publishing-account.html"],
        ["品牌资料库三级范围", "../product/brand-library.html"],
        ["当前可用与待补", "../product/readiness.html"],
        ["管理员访问创作端被拒绝", "../product/access-admin-creator.html"],
      ],
    },
    creator: {
      label: "租户用户创作旅程",
      pages: [
        [
          "选择账号、平台与自然交流",
          "../product/creator-empty.html?account=store&platform=xiaohongshu&format=graphic",
        ],
        [
          "婆媳关系开放输入",
          "../product/creator-relationship.html?account=store&platform=xiaohongshu&format=graphic",
        ],
        [
          "生成过程、V1/V2与历史",
          "../product/creator-generating.html?account=store&platform=xiaohongshu&format=graphic",
        ],
        [
          "生成失败与恢复",
          "../product/creator-failure.html?account=store&platform=xiaohongshu&format=graphic",
        ],
        ["租户用户访问管理端被拒绝", "../product/access-user-admin.html"],
      ],
    },
  };

  const one = (selector) => document.querySelector(selector);
  const all = (selector) => [...document.querySelectorAll(selector)];
  const list = one("[data-page-list]");
  const frame = one("[data-review-frame]");
  const canvas = one("[data-review-canvas]");
  const title = one("[data-review-title]");
  const position = one("[data-review-position]");
  const openRaw = one("[data-open-raw]");
  const home = one("[data-journey-home]");
  const previous = one("[data-prev]");
  const next = one("[data-next]");
  let journey = "";
  let pages = [];
  let current = 0;

  const show = (index) => {
    if (!pages.length) return;
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

  const chooseJourney = (name) => {
    journey = name;
    pages = journeys[name].pages;
    list.innerHTML = pages
      .map(
        ([label], index) =>
          `<button type="button" data-page="${index}">${index + 1}. ${label}</button>`
      )
      .join("");
    all("[data-journey]").forEach((button) => {
      button.classList.toggle("active", button.dataset.journey === name);
    });
    home.hidden = true;
    canvas.hidden = false;
    previous.hidden = false;
    next.hidden = false;
    openRaw.hidden = false;
    show(0);
  };

  const showHome = () => {
    journey = "";
    pages = [];
    list.innerHTML = "";
    frame.src = "about:blank";
    home.hidden = false;
    canvas.hidden = true;
    previous.hidden = true;
    next.hidden = true;
    openRaw.hidden = true;
    title.textContent = "选择评审旅程";
    position.textContent = "管理员与租户用户彼此独立";
    all("[data-journey]").forEach((button) => button.classList.remove("active"));
  };

  all("[data-journey]").forEach((button) => {
    button.addEventListener("click", () => chooseJourney(button.dataset.journey));
  });
  one("[data-home]").addEventListener("click", showHome);
  list.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-page]");
    if (trigger) show(Number(trigger.dataset.page));
  });
  previous.addEventListener("click", () => show(current - 1));
  next.addEventListener("click", () => show(current + 1));
  one("[data-desktop]").addEventListener("click", () => {
    canvas.classList.remove("mobile");
    all("[data-viewport]").forEach((button) => button.classList.toggle("active", button.dataset.viewport === "desktop"));
  });
  one("[data-mobile]").addEventListener("click", () => {
    canvas.classList.add("mobile");
    all("[data-viewport]").forEach((button) => button.classList.toggle("active", button.dataset.viewport === "mobile"));
  });
  document.addEventListener("keydown", (event) => {
    if (!journey) return;
    if (event.altKey && event.key === "ArrowRight") show(current + 1);
    if (event.altKey && event.key === "ArrowLeft") show(current - 1);
  });

  showHome();
})();
