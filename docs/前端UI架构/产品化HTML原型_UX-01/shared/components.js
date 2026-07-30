(() => {
  "use strict";
  const esc = (value = "") =>
    String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  const logo = (inverse = false) =>
    `<img class="brand-logo" src="../../../../assets/brand/diyu-vi/svg/diyu-logo-horizontal${inverse ? "-ondark" : ""}.svg" alt="笛语">`;
  const button = (label, options = {}) =>
    `<button type="button" class="${options.primary ? "primary" : options.quiet ? "quiet" : ""}"
      ${options.go ? `data-go="${esc(options.go)}"` : ""}
      ${options.action ? `data-action="${esc(options.action)}"` : ""}>${esc(label)}</button>`;
  const status = (label, tone = "") => `<span class="status ${tone}">${esc(label)}</span>`;
  const shell = ({ role = "user", nav = [], active = "", title = "", meta = "", body = "" }) => `
    <div class="product-shell ${role}">
      <aside class="side-nav">
        <a class="brand-link" href="?scene=${role === "admin" ? "admin-overview" : "creator-empty"}">${logo()}</a>
        <nav aria-label="${role === "admin" ? "品牌管理" : "工作导航"}">
          ${nav.map(([id, label, scene]) =>
            `<a class="${active === id ? "active" : ""}" href="?scene=${scene}">${esc(label)}</a>`).join("")}
        </nav>
        <div class="side-account"><span class="avatar">${role === "admin" ? "林" : "周"}</span><span>${role === "admin" ? "林予 · 管理员" : "周宁 · 内容运营"}</span></div>
      </aside>
      <section class="shell-main">
        <header class="topbar"><div><strong>${esc(title)}</strong><small>${esc(meta)}</small></div><button class="icon-button" aria-label="打开个人菜单">•••</button></header>
        ${body}
      </section>
    </div>`;
  const adminNav = [
    ["overview", "概览", "admin-overview"], ["members", "成员与资格", "admin-members"],
    ["accounts", "发布账号", "admin-account"], ["library", "品牌资料库", "admin-library"],
    ["usage", "团队使用", "admin-usage"], ["readiness", "能力诊断", "admin-readiness"],
    ["security", "账户安全", "admin-security"]
  ];
  window.UX = { esc, logo, button, status, shell, adminNav };
})();
