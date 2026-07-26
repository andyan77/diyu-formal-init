(() => {
  "use strict";

  const one = (selector, root = document) => root.querySelector(selector);
  const all = (selector, root = document) => [...root.querySelectorAll(selector)];

  const flows = {
    auth: [
      ["公开首页与 A 动效", "../product/home.html"],
      ["创作空间登录", "../product/login.html?entry=creator"],
      ["品牌管理登录", "../product/login.html?entry=admin"],
      ["笛语运维登录", "../product/login.html?entry=ops"],
      ["激活与设置密码", "../product/login.html?entry=creator&mode=activate"],
      ["错误入口恢复", "../product/recovery.html?entry=admin"],
      ["正确进入创作空间", "../product/creator.html?role=store&task=content&state=empty"],
    ],
    admin: [
      ["品牌管理登录", "../product/login.html?entry=admin"],
      ["概览与待处理", "../product/tenant-admin.html?view=overview"],
      ["成员与权限", "../product/tenant-admin.html?view=members"],
      ["发布账号", "../product/tenant-admin.html?view=accounts"],
      ["品牌表达", "../product/tenant-admin.html?view=library&tab=brand"],
      ["商品资料", "../product/tenant-admin.html?view=library&tab=products"],
      ["组织素材", "../product/tenant-admin.html?view=library&tab=materials"],
      ["生产就绪与缺口", "../product/tenant-admin.html?view=readiness"],
    ],
    content: [
      ["门店 · 空状态", "../product/creator.html?role=store&task=content&state=empty"],
      ["创作方向展开", "../product/creator.html?role=store&task=content&state=empty&direction=open"],
      ["合法素材已选择", "../product/creator.html?role=store&task=content&state=empty&material=selected"],
      ["一次合并追问", "../product/creator.html?role=store&task=content&state=clarify"],
      ["完整成品 V1", "../product/creator.html?role=store&task=content&state=v1"],
      ["自然修改 V2", "../product/creator.html?role=store&task=content&state=v2"],
      ["回读完整 V1", "../product/creator.html?role=store&task=content&state=history"],
      ["无内容历史", "../product/creator.html?role=store&task=content&state=no-history"],
      ["加载状态", "../product/creator.html?role=store&task=content&state=loading"],
      ["可恢复失败", "../product/creator.html?role=store&task=content&state=error"],
      ["总部同壳 · V2", "../product/creator.html?role=hq&task=content&state=v2"],
      ["总部无陈列资格", "../product/creator.html?role=hq&task=display&state=no-capability"],
    ],
    display: [
      ["门店 · 陈列空状态", "../product/creator.html?role=store&task=display&state=empty"],
      ["文字参考方案 V1", "../product/creator.html?role=store&task=display&state=v1"],
      ["局部调整 V2", "../product/creator.html?role=store&task=display&state=v2"],
      ["回读文字 V1", "../product/creator.html?role=store&task=display&state=history"],
    ],
    ops: [
      ["笛语运维登录", "../product/login.html?entry=ops"],
      ["笛语运维首页", "../product/ops.html"],
    ],
  };

  const mode = one("[data-review-mode]");
  const flowSelect = one("[data-flow-select]");
  const flowField = one("[data-flow-field]");
  const pageList = one("[data-review-pages]");
  const frame = one("[data-review-frame]");
  const stage = one("[data-review-stage]");
  let currentPages = flows.auth;
  let currentIndex = 0;

  const allPages = () => {
    const seen = new Set();
    return Object.values(flows)
      .flat()
      .filter(([, src]) => {
        if (seen.has(src)) return false;
        seen.add(src);
        return true;
      });
  };

  const updateToolbar = () => {
    const current = currentPages[currentIndex] || currentPages[0];
    one("[data-current-index]").textContent = `${currentIndex + 1} / ${currentPages.length}`;
    one("[data-current-name]").textContent = current?.[0] || "产品页面";
    all("[data-review-pages] button").forEach((button, index) => {
      button.classList.toggle("is-current", index === currentIndex);
      if (index === currentIndex) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    one("[data-review-prev]").disabled = currentIndex === 0;
    one("[data-review-next]").disabled = currentIndex === currentPages.length - 1;
  };

  const go = (index) => {
    if (!currentPages.length) return;
    currentIndex = Math.max(0, Math.min(index, currentPages.length - 1));
    frame.src = currentPages[currentIndex][1];
    updateToolbar();
  };

  const renderList = () => {
    currentPages = mode.value === "free" ? allPages() : flows[flowSelect.value] || flows.auth;
    currentIndex = 0;
    pageList.replaceChildren();
    currentPages.forEach(([name], index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.innerHTML = `<span>${String(index + 1).padStart(2, "0")}</span><strong></strong>`;
      one("strong", button).textContent = name;
      button.addEventListener("click", () => go(index));
      pageList.append(button);
    });
    go(0);
  };

  mode.addEventListener("change", () => {
    flowField.hidden = mode.value === "free";
    renderList();
  });
  flowSelect.addEventListener("change", renderList);
  one("[data-review-prev]").addEventListener("click", () => go(currentIndex - 1));
  one("[data-review-next]").addEventListener("click", () => go(currentIndex + 1));

  all("[data-canvas]").forEach((button) => {
    button.addEventListener("click", () => {
      const canvas = button.dataset.canvas;
      stage.dataset.canvasSize = canvas;
      all("[data-canvas]").forEach((candidate) => {
        candidate.setAttribute("aria-pressed", String(candidate === button));
      });
    });
  });

  one("[data-open-raw]").addEventListener("click", () => {
    window.open(frame.src, "_blank", "noopener");
  });

  const identityPages = {
    admin: "../product/tenant-admin.html?view=overview",
    hq: "../product/creator.html?role=hq&task=content&state=v2",
    store: "../product/creator.html?role=store&task=content&state=v2",
    ops: "../product/ops.html",
  };
  all("[data-identity-entry]").forEach((button) => {
    button.addEventListener("click", () => {
      mode.value = "free";
      flowField.hidden = true;
      renderList();
      const target = identityPages[button.dataset.identityEntry];
      const index = currentPages.findIndex(([, src]) => src === target);
      if (index >= 0) go(index);
    });
  });

  frame.addEventListener("load", () => {
    try {
      const currentUrl = frame.contentWindow.location.href;
      const match = currentPages.findIndex(([, src]) => currentUrl.endsWith(src.replace("../", "")));
      if (match >= 0) {
        currentIndex = match;
        updateToolbar();
      } else {
        one("[data-current-name]").textContent = frame.contentDocument.title || "产品页面";
      }
    } catch (_error) {
      /* The prototype remains navigable when a browser isolates local file frames. */
    }
  });

  renderList();
})();
