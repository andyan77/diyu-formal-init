(() => {
  "use strict";

  const pages = [
    { name: "公开首页", url: "../product/home.html", group: "公开与认证" },
    { name: "登录", url: "../product/login.html?role=user", group: "公开与认证" },
    { name: "内容工作空间", url: "../product/content-workspace.html?view=content", group: "租户用户" },
    { name: "陈列参考方案", url: "../product/display-plan.html", group: "租户用户" },
    { name: "品牌管理概览", url: "../product/brand-overview.html", group: "品牌管理" },
    { name: "笛语运维首页", url: "../product/ops-home.html", group: "笛语运维" },
    { name: "动效实验室", url: "../motion-lab/index.html", group: "叙事动效" },
  ];

  const flows = {
    user: [
      { name: "公开首页", url: "../product/home.html" },
      { name: "租户用户登录", url: "../product/login.html?role=user" },
      { name: "用户首页", url: "../product/content-workspace.html?view=home" },
      { name: "开始一篇内容", url: "../product/content-workspace.html?view=content&mode=create" },
      { name: "开始一份陈列", url: "../product/display-plan.html?view=input" },
    ],
    brand: [
      { name: "品牌管理登录", url: "../product/login.html?role=brand" },
      { name: "品牌管理概览", url: "../product/brand-overview.html" },
      { name: "内容演示", url: "../product/content-workspace.html?view=content" },
    ],
    ops: [
      { name: "笛语运维登录", url: "../product/login.html?role=ops" },
      { name: "笛语运维首页", url: "../product/ops-home.html" },
    ],
    activate: [
      { name: "激活并设置密码", url: "../product/login.html?mode=activate&role=user" },
      { name: "用户首页", url: "../product/content-workspace.html?view=home" },
    ],
  };

  const one = (selector) => document.querySelector(selector);
  const frame = one("[data-review-frame]");
  const pageList = one("[data-page-list]");
  let mode = "free";
  let current = 0;
  let activeFlow = "user";

  function collection() {
    return mode === "flow" ? flows[activeFlow] : pages;
  }

  function renderList() {
    const list = collection();
    pageList.innerHTML = "";
    list.forEach((page, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = index === current ? "is-active" : "";
      button.innerHTML = `<span>${String(index + 1).padStart(2, "0")}</span><span>${page.name}</span>`;
      button.addEventListener("click", () => load(index));
      pageList.appendChild(button);
    });
  }

  function load(index) {
    const list = collection();
    current = Math.max(0, Math.min(index, list.length - 1));
    const page = list[current];
    frame.src = page.url;
    one("[data-current-name]").textContent = page.name;
    one("[data-current-count]").textContent = `${current + 1} / ${list.length}`;
    one("[data-open-page]").href = page.url;
    renderList();
    one("[data-sidebar]")?.classList.remove("is-open");
  }

  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      mode = button.dataset.mode;
      document.querySelectorAll("[data-mode]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      current = 0;
      load(0);
    });
  });

  document.querySelectorAll("[data-identity]").forEach((button) => {
    button.addEventListener("click", () => {
      activeFlow = button.dataset.identity;
      mode = "flow";
      document.querySelectorAll("[data-mode]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item.dataset.mode === "flow"));
      });
      current = 0;
      load(0);
    });
  });

  one("[data-prev]").addEventListener("click", () => load(current - 1));
  one("[data-next]").addEventListener("click", () => load(current + 1));

  document.querySelectorAll("[data-viewport]").forEach((button) => {
    button.addEventListener("click", () => {
      one("[data-canvas]").dataset.viewport = button.dataset.viewport;
      document.querySelectorAll("[data-viewport]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
    });
  });

  one("[data-menu]").addEventListener("click", () => {
    one("[data-sidebar]").classList.toggle("is-open");
  });

  load(0);
})();
