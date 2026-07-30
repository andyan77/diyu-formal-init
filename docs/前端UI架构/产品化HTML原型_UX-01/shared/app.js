(() => {
  "use strict";

  const { esc, logo, button, status, shell, adminNav } = window.UX;
  const app = document.querySelector("#app");
  const demoActivationUrl = "https://diyuai.cc/activate/ux01-example-token";
  let currentScene = new URLSearchParams(location.search).get("scene") || "home";
  let drawer = null;
  let drawerTrigger = null;
  const supportedActions = new Set([
    "activate-demo", "apply-direction-custom", "clear-directions", "close-drawer",
    "confirm-platform", "copy-current", "copy-link", "export-current",
    "open-account-profile", "open-admin-menu", "open-directions", "open-material",
    "open-personal-menu", "open-platform-drawer", "open-series", "open-versions",
    "replay-motion", "save-account", "save-directions", "save-library",
    "save-material", "save-password", "save-profile", "save-series",
    "select-direction", "send-chat", "show-direction-more", "skip-motion",
    "usage-7", "usage-30",
  ]);

  const state = {
    memberRole: "user",
    accountCreated: currentScene === "admin-account-created",
    platformAdded: false,
    libraryAdded: false,
    usageDays: 7,
    directions: {},
    series: "",
    material: "",
    drafts: {},
  };

  const pageHead = (eyebrow, title, action = "") => `
    <header class="page-heading"><div><p class="eyebrow">${esc(eyebrow)}</p><h1>${esc(title)}</h1></div>${action}</header>`;
  const metric = (label, value, note) =>
    `<div class="metric card"><small>${esc(label)}</small><strong>${esc(value)}</strong><small>${esc(note)}</small></div>`;
  const admin = (active, title, body) => shell({
    role: "admin",
    nav: adminNav,
    active,
    title,
    meta: "笛语服饰",
    body: `<main id="main" class="page">${body}</main>`,
  });

  const toast = (message) => {
    document.querySelector(".toast")?.remove();
    const node = document.createElement("div");
    node.className = "toast";
    node.setAttribute("role", "status");
    node.textContent = message;
    document.body.append(node);
    window.setTimeout(() => node.remove(), 1800);
  };

  const closeDrawer = (restoreFocus = true) => {
    if (!drawer) return;
    drawer.remove();
    drawer = null;
    document.querySelector("#main")?.removeAttribute("inert");
    if (restoreFocus) drawerTrigger?.focus();
    drawerTrigger = null;
  };

  const openDrawer = ({ title, eyebrow = "当前操作", content, trigger, wide = false }) => {
    closeDrawer(false);
    drawerTrigger = trigger || document.activeElement;
    drawer = document.createElement("div");
    drawer.className = "drawer-layer";
    drawer.innerHTML = `<aside class="drawer${wide ? " drawer-wide" : ""}" role="dialog" aria-modal="true" aria-labelledby="ux-drawer-title">
      <header><div><p class="eyebrow">${esc(eyebrow)}</p><h2 id="ux-drawer-title">${esc(title)}</h2></div>
      ${button("关闭", { action: "close-drawer", id: "drawer-close" })}</header>${content}</aside>`;
    document.querySelector("#main")?.setAttribute("inert", "");
    document.body.append(drawer);
    drawer.querySelector("input,select,textarea,button,a")?.focus();
  };

  const rememberDraft = () => {
    const field = document.querySelector(".composer textarea");
    if (field) state.drafts[field.dataset.draftKey] = field.value;
  };

  const go = (next, { replace = false } = {}) => {
    rememberDraft();
    closeDrawer(false);
    currentScene = next;
    const url = `?scene=${encodeURIComponent(next)}`;
    history[replace ? "replaceState" : "pushState"]({ scene: next }, "", url);
    render();
  };

  const auth = ({
    kind = "user",
    title,
    intro,
    action = "登录",
    note = "",
    expired = false,
    recoveryGo = "",
    recoveryLabel = "",
  }) => {
    const destination = recoveryGo || (kind === "admin" ? "login-admin" : "login-user");
    const label = recoveryLabel || (kind === "admin" ? "返回品牌管理登录" : "返回内容创作登录");
    return `<main id="main" class="auth">
      <section class="auth-story">
        ${logo(true)}
        <div><p class="eyebrow">让品牌每天都有话可说</p><h1>${esc(intro)}</h1>
        <p>一句想法、一段流水账或一个商品，就可以开始。</p></div>
        <small>笛语 · 品牌内容工作台</small>
      </section>
      <section class="auth-panel">
        <div class="auth-card">
          <div class="auth-choice">
            <a class="${kind === "user" ? "active" : ""}" href="?scene=login-user">内容创作</a>
            <a class="${kind === "admin" ? "active" : ""}" href="?scene=login-admin">品牌管理</a>
          </div>
          <p class="eyebrow">${kind === "admin" ? "品牌管理" : kind === "activate" ? "账户设置" : "内容创作"}</p>
          <h1>${esc(title)}</h1>
          ${note ? `<p class="${expired ? "status bad" : "muted"}">${esc(note)}</p>` : ""}
          ${expired ? `<div class="button-row">${button(label, { primary: true, go: destination })}</div>` : `
          <form>
            ${kind === "activate" ? "" : `<label>用户名<input autocomplete="username" value="${kind === "admin" ? "brand-admin" : "zhou-ning"}"></label>`}
            <label>${kind === "activate" ? "设置密码" : "密码"}<input type="password" value="long-password-demo" autocomplete="${kind === "activate" ? "new-password" : "current-password"}"></label>
            ${kind === "activate" ? `<label>再次输入<input type="password" value="long-password-demo" autocomplete="new-password"></label>` : ""}
            ${button(action, { primary: true, go: kind === "admin" ? "admin-overview" : "creator-empty" })}
          </form>`}
        </div>
      </section>
    </main>`;
  };

  const memberTable = () => `<div class="table-card card">
    <div class="table-row"><strong>周宁</strong><span>内容创作</span><span>品牌官方账号</span>${status("可使用", "good")}</div>
    <div class="table-row"><strong>苏予</strong><span>陈列参考</span><span>柯桥门店</span>${status("可使用", "good")}</div>
    <div class="table-row"><strong>林予</strong><span>品牌管理</span><span>不进入创作端</span>${status("可使用", "good")}</div>
  </div>`;

  const memberQualification = () => {
    const user = state.memberRole === "user";
    return admin("members", "成员与资格", `${pageHead("添加成员", "分配入口与工作资格")}
      <div class="drawer-layer static-drawer"><aside class="drawer" role="dialog" aria-modal="false" aria-labelledby="member-role-title">
      <header><div><p class="eyebrow">第 2 步</p><h2 id="member-role-title">这个成员要做什么</h2></div>${button("关闭", { go: "admin-members" })}</header>
      <form>
        <fieldset class="role-choice"><legend>入口资格</legend>
          <label class="role-card"><input type="radio" name="member-role" value="user" ${user ? "checked" : ""}>
            <span><strong>租户用户</strong><small>进入内容创作或陈列参考</small></span></label>
          <label class="role-card"><input type="radio" name="member-role" value="admin" ${user ? "" : "checked"}>
            <span><strong>租户管理员</strong><small>只进入品牌管理</small></span></label>
        </fieldset>
        <div data-user-qualification ${user ? "" : "hidden"}>
          <label>工作资格<select data-user-field><option value="content">内容创作</option><option value="display">陈列参考</option></select></label>
          <label>可操作的发布账号<select data-user-field><option value="brand">笛语服饰品牌官方账号</option></select></label>
        </div>
        <div class="status good" data-admin-qualification ${user ? "hidden" : ""}>只进入品牌管理，不分配内容、陈列或发布账号。</div>
        ${button("创建并生成激活链接", { primary: true, go: "admin-activation" })}
      </form></aside></div>`);
  };

  const accountCard = (created = false) => `<article class="card account-card">
    <div class="page-heading"><div><h2>${created ? "柯桥门店日常" : "笛语服饰品牌官方账号"}</h2>
    <p class="muted">${created ? "个人 IP · 浙江区域门店" : "机构账号 · 总部品牌内容组"}</p></div>
    ${button("查看五段画像", { action: "open-account-profile" })}</div>
    <div class="button-row">${status(created ? "小红书视频" : "小红书图文", "good")}
    ${created ? "" : `${status("小红书视频", "good")}${status("抖音视频", "good")}`}
    ${button("管理平台", { go: "admin-platforms" })}</div></article>`;

  const platformRows = () => `<div class="table-card card" data-platform-list>
    <div class="table-row"><strong>小红书</strong><span>图文</span><span>周宁</span>${status("已启用", "good")}</div>
    <div class="table-row"><strong>小红书</strong><span>视频</span><span>周宁</span>${status("已启用", "good")}</div>
    <div class="table-row"><strong>抖音</strong><span>视频</span><span>宋言</span>${status("已启用", "good")}</div>
    ${state.platformAdded ? `<div class="table-row added"><strong>微信视频号</strong><span>视频</span><span>周宁</span>${status("刚添加", "good")}</div>` : ""}
  </div>`;

  const libraryRows = () => `<div class="table-card card" data-library-list>
    ${state.libraryAdded ? `<div class="table-row added"><strong>浙江区域门店拍摄补充</strong><span>指定区域</span><span>浙江区域 · 待处理</span>${status("V1", "good")}</div>` : ""}
    <div class="table-row"><strong>品牌表达基线</strong><span>品牌全员</span><span>总部品牌部 · V3</span>${status("当前", "good")}</div>
    <div class="table-row"><strong>ZX-C218 商品事实</strong><span>总部专用</span><span>商品部 · V2</span>${status("当前", "good")}</div>
    <div class="table-row"><strong>浙江门店拍摄条件</strong><span>指定区域</span><span>浙江区域 · V1</span>${status("当前", "good")}</div>
  </div>`;

  const usageBody = () => {
    const days = state.usageDays;
    const values = days === 7
      ? [["活跃成员", "5", "7 名已启用"], ["内容尝试", "18", "成功 14"], ["陈列尝试", "3", "成功 3"], ["已记录用量", "28,640", "仅为系统记录"]]
      : [["活跃成员", "7", "7 名已启用"], ["内容尝试", "61", "成功 49"], ["陈列尝试", "9", "成功 8"], ["已记录用量", "96,320", "仅为系统记录"]];
    const rows = days === 7
      ? `<div class="table-row"><strong>周宁</strong><span>11 次内容</span><span>小红书图文</span>${status("今天使用", "good")}</div><div class="table-row"><strong>苏予</strong><span>3 次陈列</span><span>柯桥门店</span>${status("3 天前")}</div>`
      : `<div class="table-row"><strong>周宁</strong><span>36 次内容</span><span>小红书图文</span>${status("本月活跃", "good")}</div><div class="table-row"><strong>苏予</strong><span>9 次陈列</span><span>柯桥门店</span>${status("本月活跃", "good")}</div><div class="table-row"><strong>宋言</strong><span>13 次内容</span><span>抖音视频</span>${status("本月活跃", "good")}</div>`;
    return `<div data-usage-content>
      <p class="muted">统计口径：近 ${days} 日</p>
      <div class="metric-grid">${values.map((item) => metric(...item)).join("")}</div>
      <div class="table-card card">${rows}</div></div>`;
  };

  const adminScenes = {
    "admin-overview": () => admin("overview", "概览", `
      ${pageHead("品牌管理", "今天需要处理什么")}
      <section class="work-list"><h2>当前待办</h2>
        <article class="work-item card"><div><h3>补充 ZX-C218 的公开商品事实</h3><p class="muted">缺少面料与适用范围，暂不支持对应商品表达。</p></div>${button("去补资料", { primary: true, go: "admin-library" })}</article>
        <article class="work-item card"><div><h3>把新成员加入发布账号</h3><p class="muted">周宁已有内容资格，还没有可操作的发布账号。</p></div>${button("查看成员", { go: "admin-members" })}</article>
      </section>
      <h2 class="section-title">近期变化</h2>
      <div class="metric-grid">${metric("已启用成员", "7", "比上周 +1")}${metric("近 7 日使用", "5 人", "有真实操作")}${metric("待补资料", "2 项", "影响商品内容")}${metric("账号变化", "1 项", "新增小红书图文")}</div>`),
    "admin-members": () => admin("members", "成员与资格", `${pageHead("成员与资格", "谁可以进入哪里", button("添加成员", { primary: true, go: "admin-member-create" }))}${memberTable()}`),
    "admin-member-create": () => admin("members", "成员与资格", `${pageHead("添加成员", "先建立登录身份")}
      <div class="drawer-layer static-drawer"><aside class="drawer" role="dialog" aria-modal="false" aria-labelledby="member-create-title"><header><div><p class="eyebrow">第 1 步</p><h2 id="member-create-title">成员基本信息</h2></div>${button("关闭", { go: "admin-members" })}</header>
      <form><label>姓名或工作名<input value="门店内容小周"></label><label>登录用户名<input value="store-zhou"></label>
      <label>所属团队<select><option>浙江区域门店</option></select></label>${button("继续分配资格", { primary: true, go: "admin-member-qualify" })}</form></aside></div>`),
    "admin-member-qualify": memberQualification,
    "admin-activation": () => admin("members", "成员与资格", `${pageHead("成员已创建", "把链接安全交给本人")}
      <div class="card activation-card"><div class="flow"><div class="done">身份已建立</div><div class="done">资格已分配</div><div class="active">等待本人设置密码</div><div>首次登录</div></div>
      <div class="link-box"><strong>一次性激活链接</strong><a href="${demoActivationUrl}" data-action="activate-demo">${demoActivationUrl}</a><small>演示链接不会请求生产；使用一次后失效。</small></div>
      <div class="button-row">${button("复制完整链接", { primary: true, action: "copy-link" })}${button("返回成员列表", { go: "admin-members" })}</div></div>`),
    "admin-account": () => admin("accounts", "发布账号", `${pageHead("发布账号", "一套表达身份，可以去多个平台", button("创建发布账号", { primary: true, go: "admin-account-create" }))}
      <div class="work-list">${state.accountCreated ? accountCard(true) : ""}${accountCard(false)}</div>`),
    "admin-account-create": () => admin("accounts", "发布账号", `${pageHead("创建发布账号", "先建立一套清楚的表达身份")}
      <div class="card form-card"><form>
      <label>账号名称<input value="柯桥门店日常"></label>
      <fieldset><legend>账号类型</legend><div class="inline-radios"><label><input type="radio" name="speaker" checked> 个人 IP</label><label><input type="radio" name="speaker"> 机构账号</label></div></fieldset>
      <label>负责组织<select><option>浙江区域门店</option><option>总部品牌内容组</option></select></label>
      <label>表达身份<select><option>门店日常观察者</option><option>品牌定义者</option></select></label>
      <label>初始平台目标<select><option>小红书 · 视频</option><option>小红书 · 图文</option><option>抖音 · 视频</option></select></label>
      <div class="button-row">${button("保存发布账号", { primary: true, action: "save-account" })}${button("取消", { go: "admin-account" })}</div>
      </form></div>`),
    "admin-account-created": () => admin("accounts", "发布账号", `${pageHead("账号已创建", "柯桥门店日常")}
      <div class="status good">账号、表达身份和初始平台目标已经保存。</div>${accountCard(true)}
      <div class="button-row">${button("返回发布账号", { primary: true, go: "admin-account" })}</div>`),
    "admin-platforms": () => admin("accounts", "发布账号", `${pageHead("笛语服饰品牌官方账号", "选择这个账号可以去哪里")}
      ${platformRows()}<div class="button-row page-actions">${button("添加平台", { primary: true, action: "open-platform-drawer" })}${button("返回账号", { go: "admin-account" })}</div>`),
    "admin-profile": () => admin("accounts", "账号画像", `${pageHead("笛语服饰品牌官方账号", "五段画像")}
      <div class="card profile-card">${profileContent()}<div class="button-row">${button("保存新版本", { primary: true, action: "save-profile" })}${button("返回账号", { go: "admin-account" })}</div></div>`),
    "admin-library": () => admin("library", "品牌资料库", `${pageHead("品牌资料库", "资料来自哪里，谁可以使用", button("新增资料", { primary: true, go: "admin-library-create" }))}
      <div class="button-row scope-summary">${status("品牌全员", "good")}${status("总部专用")}${status("指定区域")}</div>${libraryRows()}`),
    "admin-library-create": () => admin("library", "品牌资料库", `${pageHead("新增资料", "记录来源和可用范围")}
      <div class="card form-card"><form>
      <label>资料名称<input value="浙江区域门店拍摄补充"></label>
      <label>资料类型<select><option>品牌表达资料</option><option>商品事实</option><option>制作条件</option></select></label>
      <label>来源说明<textarea>浙江区域负责人整理，2026 年 7 月确认。</textarea></label>
      <label>适用范围<select data-library-scope><option value="all">品牌全员</option><option value="hq">总部专用</option><option value="region">指定区域</option></select></label>
      <label data-region-choice hidden>选择区域<select><option>浙江区域</option><option>江苏区域</option></select></label>
      <p class="status warn">保存后为 V1 · 待处理，不会自动变成已确认事实。</p>
      <div class="button-row">${button("保存资料", { primary: true, action: "save-library" })}${button("取消", { go: "admin-library" })}</div>
      </form></div>`),
    "admin-usage": () => admin("usage", "团队使用", `${pageHead("团队使用", "最近谁在使用，做了什么")}
      <div class="segmented" role="group" aria-label="统计时间">
        ${button("近 7 日", { action: "usage-7", className: state.usageDays === 7 ? "active" : "" })}
        ${button("近 30 日", { action: "usage-30", className: state.usageDays === 30 ? "active" : "" })}
      </div>${usageBody()}`),
    "admin-readiness": () => admin("readiness", "能力诊断", `${pageHead("能力诊断", "缺什么，会影响哪项工作")}
      <div class="work-list">
      <article class="work-item card"><div>${status("待补", "warn")}<h3>商品内容</h3><p>依据：ZX-C218 已有名称和品类。缺少：公开面料与适用范围。影响：不能写商品硬事实。</p></div>${button("去补商品资料", { primary: true, go: "admin-library" })}</article>
      <article class="work-item card"><div>${status("可用", "good")}<h3>非商品内容</h3><p>依据：品牌表达基线 V3、账号画像 V2。当前可直接创作。</p></div></article>
      <article class="work-item card"><div>${status("有条件", "warn")}<h3>陈列参考</h3><p>依据：柯桥店挂杆结构已记录。缺少本次库存时，需要先补一份商品清单。</p></div></article>
      </div>`),
    "admin-security": () => admin("security", "账户安全", `${pageHead("账户安全", "保护你的管理入口")}
      <div class="card security-card"><h2>修改密码</h2><p class="muted">更新后，其他浏览器中的管理会话会退出。</p>
      <label>当前密码<input type="password" value="current-password"></label><label>新密码<input type="password" value="new-password-long"></label>
      <div class="button-row">${button("更新密码", { primary: true, action: "save-password" })}</div></div>`),
  };

  function profileContent() {
    return `<div class="work-list">
      <div><small>身份位置</small><p>品牌日常表达的组织者，不代替门店或顾客讲经历。</p></div>
      <div><small>可以代表什么</small><p>已确认的品牌选择、商品事实与当篇观察。</p></div>
      <div><small>与受众的关系</small><p>平等、克制，像熟悉服装的人认真分享。</p></div>
      <div><small>长期内容领地</small><p>穿搭选择、门店观察、女性日常与品牌判断。</p></div>
      <div><small>默认制作条件</small><p>一人、一部手机、普通室内和已有商品素材。</p></div>
    </div>`;
  }

  const artifactText = {
    v1: `标题｜忙完一天，别让两只碗替你们吵架

今天店里忙了一天。回到家，因为洗碗拌了两句。

一种理解是：很多摩擦并不是谁更有道理，而是两个人都已经没有余量。先把眼前的小事放下，不等于逃避；只是给彼此一点重新说话的空间。

如果下次又遇到类似时刻，不妨先说一句：“我们都累了，晚一点再聊。”

发布配文｜有些争执需要的不是结论，是先喘口气。你会怎么让一天慢下来？`,
    v2: `标题｜今晚，两只碗决定暂时休战

今天店里忙了一天。回到家，因为洗碗拌了两句。

情景演绎｜厨房临时召开圆桌会议，两只碗一致表决：暂停代表人类发言。

荒诞归荒诞，真正值得留下的是那一点停顿。累的时候，先别急着把一句气话升级成一场胜负。

发布配文｜本段为情景演绎。碗没有立场，人可以先休息。`,
  };

  const versionHistory = (version, viewed) => {
    if (!version) return `<p class="muted history-empty">最近还没有内容</p>`;
    const currentLabel = version === 1 ? "忙完一天，别让两只碗替你们吵架" : "今晚，两只碗决定暂时休战";
    const rows = [`<button class="${viewed === version ? "active" : ""}" data-go="${version === 1 ? "creator-v1" : "creator-current"}">${esc(currentLabel)}<small> 当前 V${version}</small></button>`];
    if (version >= 2) rows.push(`<button class="${viewed === 1 ? "active" : ""}" data-go="creator-history-v1">忙完一天，别让两只碗替你们吵架<small> 历史 V1</small></button>`);
    return rows.join("");
  };

  const creator = (view, body, options = {}) => {
    const version = options.version || 0;
    const viewed = options.viewed || version;
    return `<main id="main" class="creator-shell">
      <header class="creator-topbar"><a href="?scene=creator-empty" aria-label="返回新创作">${logo()}</a>
        <div class="context-controls">
          <label><small>发布账号</small><select title="笛语服饰品牌官方账号"><option>笛语服饰品牌官方账号</option><option>柯桥门店日常</option></select></label>
          <label><small>平台与形式</small><select><option>小红书 · 图文</option><option>小红书 · 视频</option><option>抖音 · 视频</option></select></label>
        </div>
        ${button("账号画像", { action: "open-account-profile", className: "profile-trigger" })}</header>
      <div class="creator-grid" data-view="${esc(view)}">
        <aside class="history">${button("＋ 新创作", { go: "creator-empty" })}<p class="muted">最近</p>${versionHistory(version, viewed)}</aside>
        ${body}
      </div>
      <nav class="mobile-tabs" aria-label="创作工作面"><button class="${view === "conversation" ? "active" : ""}" data-view="conversation">对话</button><button class="${view === "artifact" ? "active" : ""}" data-view="artifact">成品</button></nav>
    </main>`;
  };

  const messages = (items) => `<section class="messages">${items.map(([who, text]) =>
    `<article class="message ${who}"><p>${esc(text)}</p></article>`).join("")}</section>`;

  const composer = ({ value = "", current = 0, loading = false, error = false }) => {
    const key = current ? `revision-${current}` : "seed";
    const draft = state.drafts[key] ?? value;
    const generateGo = current ? "creator-v2" : "creator-generating";
    const directionCount = Object.keys(state.directions).length;
    return `<div class="composer">
      <textarea data-draft-key="${key}" aria-label="${current ? "修改要求" : "说一句话就可以"}">${esc(draft)}</textarea>
      <div class="composer-tools"><div>
        ${button(directionCount ? `创作方向 · ${directionCount}` : "创作方向（可选）", { action: "open-directions" })}
        ${button(state.series ? `系列 · ${state.series}` : "系列", { action: "open-series" })}
        ${button(state.material ? `素材 · ${state.material}` : "素材", { action: "open-material" })}
      </div><small>输入会保留到完成或你主动清空</small></div>
      <div class="composer-actions"><button class="quiet" data-action="send-chat">发送</button>
      ${button(loading ? "正在整理…" : current ? `修改成 V${current + 1}` : "生成内容", { primary: true, go: generateGo })}</div>
      ${error ? `<div class="status bad">网络中断，原始输入已经保留。</div>` : ""}</div>`;
  };

  const artifact = (version, viewed = version) => `<section class="artifact" data-current-version="${version}" data-viewed-version="${viewed}">
    <header class="artifact-head"><div><p class="eyebrow">${viewed === version ? `当前版 · V${version}` : `历史版 · V${viewed}`}</p>
    <h1>${viewed === 1 ? "忙完一天，别让两只碗替你们吵架" : "今晚，两只碗决定暂时休战"}</h1>
    ${viewed !== version ? `<p class="muted">当前版本仍为 V${version}</p>` : ""}</div>
    <div class="button-row">${button("版本", { action: "open-versions" })}${button("复制", { action: "copy-current" })}${button("导出", { action: "export-current" })}</div></header>
    ${viewed !== version ? `<div class="status warn history-reading">正在回读 V${viewed}　<a href="?scene=creator-current">回到当前 V${version}</a></div>` : ""}
    <div class="artifact-section"><h2>完整发布正文</h2><div class="artifact-copy">${esc(viewed === 1 ? artifactText.v1 : artifactText.v2)}</div></div>
    <div class="artifact-section"><h2>图文组织</h2><p>1. 标题卡　2. 真实片段　3. 观察或演绎　4. 收束与互动</p></div>
    <div class="artifact-section"><h2>制作提示</h2><p>使用文字卡、已有室内环境和一人旁白；不新增演员或道具。</p></div>
    <p class="muted">AI 辅助生成 · 发布前请按平台要求完成标识。</p></section>`;
  const conversationPane = (content, compose) => `<section class="conversation">${content}${compose}</section>`;

  const creatorScenes = {
    "creator-empty": () => creator("conversation", `${conversationPane(`<div class="messages"><div><p class="eyebrow">小红书 · 图文</p><h1>今天想说什么？</h1><p class="muted">一句感悟、一段流水账、一个商品，或者“今天不知道发什么”都可以。</p></div></div>`, composer({}))}<section class="artifact"><div class="card empty-artifact"><h2>成品会出现在这里</h2><p class="muted">生成完成前，不展示尚未核验的草稿。</p></div></section>`),
    "creator-compose": () => creator("conversation", `${conversationPane(messages([["user", "今天店里忙了一天，回家因为洗碗拌了两句，帮我发条小红书。"]]), composer({ value: "今天店里忙了一天，回家因为洗碗拌了两句，帮我发条小红书。" }))}<section class="artifact"><div class="card empty-artifact"><h2>准备生成完整小红书</h2><p>无需再填写观点、受众或结构。</p></div></section>`),
    "creator-generating": () => creator("conversation", `${conversationPane(messages([["user", "今天店里忙了一天，回家因为洗碗拌了两句，帮我发条小红书。"], ["assistant", "正在把这段生活整理成一篇完整内容。"]]), `<div class="card loading-card" role="status"><strong>正在整理成品</strong><p class="muted">完成检查后会一次呈现，不展示未完成草稿。</p>${button("查看完成的 V1", { primary: true, go: "creator-v1" })}</div>`)}<section class="artifact"><div class="card empty-artifact"><h2>内容还在整理</h2></div></section>`),
    "creator-v1": () => creator("artifact", `${conversationPane(messages([["user", "今天店里忙了一天，回家因为洗碗拌了两句，帮我发条小红书。"], ["assistant", "V1 已经整理好，可以直接阅读或继续修改。"]]), composer({ current: 1 }))}${artifact(1)}`, { version: 1, viewed: 1 }),
    "creator-revision": () => creator("conversation", `${conversationPane(messages([["assistant", "V1 已经整理好，可以直接阅读或继续修改。"], ["user", "别讲道理，荒诞一点。"]]), composer({ value: "别讲道理，荒诞一点。", current: 1 }))}${artifact(1)}`, { version: 1, viewed: 1 }),
    "creator-v2": () => creator("artifact", `${conversationPane(messages([["assistant", "已改成 V2，V1 完整保留。"]]), composer({ current: 2 }))}${artifact(2)}`, { version: 2, viewed: 2 }),
    "creator-history-v1": () => creator("artifact", `${conversationPane(messages([["assistant", "正在回读 V1。"]]), composer({ current: 2 }))}${artifact(2, 1)}`, { version: 2, viewed: 1 }),
    "creator-current": () => creator("artifact", `${conversationPane(messages([["assistant", "已回到当前 V2。"]]), composer({ current: 2 }))}${artifact(2)}`, { version: 2, viewed: 2 }),
    "creator-export": () => creator("artifact", `${conversationPane(messages([["assistant", "复制和导出都以当前查看版本为准。"]]), composer({ current: 2 }))}${artifact(2)}`, { version: 2, viewed: 2 }),
    "creator-failure": () => creator("conversation", `${conversationPane(messages([["user", "再改得轻一点，但保留前两段。"]]), composer({ value: "再改得轻一点，但保留前两段。", current: 2, error: true }))}${artifact(2)}`, { version: 2, viewed: 2 }),
  };

  const dm = (body) => `<main id="main"><header class="creator-topbar dm-topbar"><a href="?scene=dm-entry">${logo()}</a><strong>陈列参考</strong><span></span></header><section class="dm-main">${body}</section></main>`;
  const plan = (version = 1, identity = "current", currentVersion = version) => `<div class="card plan-card" data-plan-version="${version}" data-plan-identity="${identity}">
    <div class="page-heading"><div><p class="eyebrow">${identity === "current" ? "当前版" : "历史版"} · V${version}</p><h2>墙面挂杆文字参考方案</h2>
    ${identity === "history" ? `<p class="muted">当前版本仍为 V${currentVersion}</p>` : ""}</div>${button("复制", { action: "copy-current" })}</div>
    <p><strong>库存对账：</strong>共 30 件；建议 18 件上墙，12 件暂不上墙。</p>
    <div class="inventory-list"><div class="inventory-row"><span>左侧挂杆</span><strong>6 件</strong></div><div class="inventory-row"><span>主焦点区</span><strong>${version === 1 ? "6" : "7"} 件</strong></div><div class="inventory-row"><span>右侧挂杆</span><strong>${version === 1 ? "6" : "5"} 件</strong></div><div class="inventory-row"><span>暂不上墙</span><strong>12 件</strong></div></div>
    <p class="muted">这是一份可直接阅读和执行的文字参考方案。</p></div>`;
  const dmScenes = {
    "dm-entry": () => dm(`${pageHead("陈列参考", "用现场条件和商品清单开始")}<div class="card dm-entry-card"><p>当前账号具备陈列参考资格。系统只生成纯文字参考方案。</p>${button("新建参考方案", { primary: true, go: "dm-input" })}</div>`),
    "dm-input": () => dm(`${pageHead("新参考方案", "告诉我这次现场有什么")}<div class="dm-grid"><div class="card form-card"><label>现场条件<textarea>柯桥店墙面挂杆，左中右三段；中间适合主焦点。</textarea></label><label>商品清单<textarea>ZX-C218 8 件；ZX-P211 10 件；ZX-V005 12 件。</textarea></label>${button("生成文字方案", { primary: true, go: "dm-v1" })}</div><div class="card info-card"><h2>本次清单</h2><p>3 个商品 · 共 30 件</p><p class="muted">笛语只整理文字安排，不会自动执行陈列。</p></div></div>`),
    "dm-v1": () => dm(`${pageHead("墙面挂杆参考方案", "已保存 V1")}<div class="dm-grid"><div>${plan(1, "current", 1)}</div><div class="card form-card"><label>只想改哪里<textarea>中间主焦点多放一件，其他总量不变。</textarea></label>${button("修改成 V2", { primary: true, go: "dm-v2" })}</div></div>`),
    "dm-v2": () => dm(`${pageHead("墙面挂杆参考方案", "已保存 V2")}<div class="dm-grid"><div>${plan(2, "current", 2)}</div><div class="card info-card"><h2>历史版本</h2>${button("阅读 V1", { go: "dm-history" })}<p class="muted">V1 和 V2 都保留自己的库存对账。</p></div></div>`),
    "dm-history": () => dm(`${pageHead("墙面挂杆参考方案", "正在回读 V1")}<div class="dm-grid"><div>${plan(1, "history", 2)}</div><div class="card info-card"><p>${status("历史版 · V1", "warn")}</p><p>当前版本仍为 V2。</p>${button("回到当前 V2", { primary: true, go: "dm-v2" })}</div></div>`),
  };

  const scenes = {
    home: () => `<main id="main" class="home"><nav class="quiet-links"><a href="?scene=login-admin">品牌管理</a><a href="?scene=login-user">内容创作</a></nav>
      <section class="home-stage"><div class="home-mark"><img src="../../../../assets/brand/diyu-vi/svg/diyu-symbol.svg" alt=""></div>
      <p class="eyebrow">一句种子，长成品牌自己的表达</p><h1>把今天想说的，变成可以发出的内容。</h1><p>不需要先写选题、结构或完整故事。说一句，笛语来完成。</p>${button("开始创作", { primary: true, go: "login-user" })}</section>
      <div class="motion-actions">${button("跳过动效", { quiet: true, action: "skip-motion" })}${button("重播", { quiet: true, action: "replay-motion" })}</div></main>`,
    "login-user": () => auth({ title: "登录内容创作", intro: "从一句生活种子，直接得到完整成品。" }),
    "login-admin": () => auth({ kind: "admin", title: "登录品牌管理", intro: "把成员、账号和资料放在正确的位置。" }),
    activate: () => auth({ kind: "activate", title: "设置你的密码", intro: "欢迎加入笛语。", action: "完成设置" }),
    "link-expired": () => auth({ kind: "user", title: "这个链接已经失效", intro: "一次性链接只在有效期内使用。", note: "请联系租户管理员重新生成链接。", expired: true }),
    "wrong-entry": () => auth({ kind: "user", title: "这里不是你的工作入口", intro: "当前账号用于内容创作。", note: "请返回内容创作入口继续。", expired: true, recoveryGo: "login-user", recoveryLabel: "返回内容创作登录" }),
    "session-expired": () => auth({ kind: "user", title: "登录已过期", intro: "你的输入仍保留在这台设备上。", note: "重新登录后可以继续刚才的内容。", expired: true }),
    ...adminScenes,
    ...creatorScenes,
    ...dmScenes,
  };

  function directionDrawer(trigger) {
    const dimensions = {
      topic: ["题材", ["婆媳", "门店生活"]],
      telling: ["讲法", ["直接说", "从一个细节开始"]],
      style: ["风格", ["克制", "轻松"]],
      form: ["形式", ["图文", "口播"]],
      series: ["系列", ["独立单篇", "门店日常"]],
      interaction: ["互动", ["留一个问题", "不加互动"]],
    };
    const content = `<div class="direction-grid">${Object.entries(dimensions).map(([id, [label, common]]) => `
      <section class="direction-group" data-direction="${id}">
        <h3>${label}<small data-direction-result>${state.directions[id] ? `已选：${esc(state.directions[id])}` : "可不选"}</small></h3>
        <div class="choice-row">${common.map((value) => `<button type="button" data-action="select-direction" data-dimension="${id}" data-value="${esc(value)}" aria-pressed="${state.directions[id] === value}">${esc(value)}</button>`).join("")}
        <button type="button" data-action="show-direction-more" data-dimension="${id}">更多 / 搜索</button></div>
        <div class="direction-more" data-direction-more="${id}" hidden><label>搜索或自定义<input data-direction-input="${id}" placeholder="可以直接写自然语言"></label>
        <button type="button" data-action="apply-direction-custom" data-dimension="${id}">使用这句话</button></div>
      </section>`).join("")}</div>
      <div class="drawer-actions">${button("清除本次选择", { action: "clear-directions" })}${button("保存本次方向", { primary: true, action: "save-directions" })}</div>`;
    openDrawer({ title: "创作方向（可选）", eyebrow: "不打开也可以生成", content, trigger, wide: true });
  }

  function assistDrawer(kind, trigger) {
    const isSeries = kind === "series";
    const current = isSeries ? state.series : state.material;
    const options = isSeries ? ["门店日常", "女性成长", "本次不使用"] : ["今日门店照片", "ZX-C218 商品文字资料", "本次不使用"];
    const content = `<form class="assist-form"><fieldset><legend>${isSeries ? "选择系列" : "选择本次素材"}</legend>
      ${options.map((value) => `<label><input type="radio" name="assist-choice" value="${esc(value)}" ${current === value || (!current && value === "本次不使用") ? "checked" : ""}> ${esc(value)}</label>`).join("")}
      </fieldset>${button("确认并返回输入", { primary: true, action: isSeries ? "save-series" : "save-material" })}</form>`;
    openDrawer({ title: isSeries ? "系列" : "素材", eyebrow: "只影响这次内容", content, trigger });
  }

  function profileDrawer(trigger) {
    openDrawer({ title: "笛语服饰品牌官方账号", eyebrow: "只读账号画像", content: `${profileContent()}<p class="muted">切换平台不会改变这套画像。</p>`, trigger });
  }

  function versionsDrawer(trigger) {
    const artifactNode = document.querySelector(".artifact[data-current-version]");
    const current = Number(artifactNode?.dataset.currentVersion || 0);
    const viewed = Number(artifactNode?.dataset.viewedVersion || current);
    const rows = current === 1
      ? `<button type="button" class="${viewed === 1 ? "active" : ""}" data-go="creator-v1">当前版 · V1</button>`
      : `<button type="button" class="${viewed === 2 ? "active" : ""}" data-go="creator-current">当前版 · V2</button><button type="button" class="${viewed === 1 ? "active" : ""}" data-go="creator-history-v1">历史版 · V1</button>`;
    openDrawer({ title: "内容版本", eyebrow: `当前版本 V${current}`, content: `<div class="version-list">${rows}</div>`, trigger });
  }

  function platformDrawer(trigger) {
    const content = `<form class="assist-form"><fieldset><legend>选择平台与形式</legend>
      <label><input type="radio" name="platform-target" value="wechat-video" checked> 微信视频号 · 视频</label>
      <label><input type="radio" name="platform-target" value="douyin-video"> 抖音 · 视频</label>
      <label><input type="radio" name="platform-target" value="rednote-image"> 小红书 · 图文</label>
      </fieldset><p class="muted">只增加目标，不复制或切换账号画像。</p>${button("确认添加", { primary: true, action: "confirm-platform" })}</form>`;
    openDrawer({ title: "添加平台", eyebrow: "笛语服饰品牌官方账号", content, trigger });
  }

  function adminMenuDrawer(trigger) {
    const links = adminNav.map(([, label, target]) => `<a href="?scene=${target}">${esc(label)}</a>`).join("");
    openDrawer({ title: "品牌管理菜单", eyebrow: "七个管理栏目", content: `<nav class="drawer-nav" aria-label="移动管理导航">${links}</nav>`, trigger });
  }

  function personalDrawer(trigger) {
    openDrawer({ title: "林予", eyebrow: "品牌管理员", content: `<div class="work-list"><p>当前空间：笛语服饰品牌管理</p><a class="text-link" href="?scene=admin-security">前往账户安全</a></div>`, trigger });
  }

  function updateMemberRole(role) {
    state.memberRole = role;
    const user = role === "user";
    document.querySelector("[data-user-qualification]")?.toggleAttribute("hidden", !user);
    document.querySelector("[data-admin-qualification]")?.toggleAttribute("hidden", user);
    document.querySelectorAll("[data-user-field]").forEach((field) => {
      field.disabled = !user;
      if (!user) field.selectedIndex = -1;
      else if (field.selectedIndex < 0) field.selectedIndex = 0;
    });
  }

  function updateDirectionChoice(dimension, value) {
    state.directions[dimension] = value;
    const group = drawer?.querySelector(`[data-direction="${dimension}"]`);
    group?.querySelectorAll("[data-value]").forEach((item) => item.setAttribute("aria-pressed", String(item.dataset.value === value)));
    const result = group?.querySelector("[data-direction-result]");
    if (result) result.textContent = `已选：${value}`;
  }

  function render() {
    closeDrawer(false);
    app.innerHTML = (scenes[currentScene] || scenes.home)();
    document.title = `${document.querySelector("h1,h2")?.textContent || "笛语"} · 笛语`;
    if (currentScene === "admin-member-qualify") updateMemberRole(state.memberRole);
  }

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-go],[data-action],[data-view]");
    if (!trigger) return;
    if (trigger.dataset.action === "activate-demo") {
      event.preventDefault();
      go("activate");
      return;
    }
    if (trigger.dataset.go) {
      event.preventDefault();
      go(trigger.dataset.go);
      return;
    }
    if (trigger.dataset.view) {
      document.querySelector(".creator-grid")?.setAttribute("data-view", trigger.dataset.view);
      document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item === trigger));
      return;
    }
    const action = trigger.dataset.action;
    if (!supportedActions.has(action)) throw new Error(`未实现的原型动作：${action}`);
    if (action === "close-drawer") closeDrawer();
    else if (action === "open-admin-menu") adminMenuDrawer(trigger);
    else if (action === "open-personal-menu") personalDrawer(trigger);
    else if (action === "open-account-profile") profileDrawer(trigger);
    else if (action === "open-platform-drawer") platformDrawer(trigger);
    else if (action === "open-directions") directionDrawer(trigger);
    else if (action === "open-series") assistDrawer("series", trigger);
    else if (action === "open-material") assistDrawer("material", trigger);
    else if (action === "open-versions") versionsDrawer(trigger);
    else if (action === "save-account") {
      state.accountCreated = true;
      go("admin-account-created");
    } else if (action === "confirm-platform") {
      state.platformAdded = true;
      closeDrawer();
      render();
      toast("微信视频号 · 视频已添加，账号画像保持不变");
    } else if (action === "save-library") {
      state.libraryAdded = true;
      go("admin-library");
    } else if (action === "usage-7" || action === "usage-30") {
      state.usageDays = action === "usage-7" ? 7 : 30;
      render();
    } else if (action === "show-direction-more") {
      const more = drawer?.querySelector(`[data-direction-more="${trigger.dataset.dimension}"]`);
      if (more) {
        more.hidden = false;
        more.querySelector("input")?.focus();
      }
    } else if (action === "select-direction") {
      updateDirectionChoice(trigger.dataset.dimension, trigger.dataset.value);
    } else if (action === "apply-direction-custom") {
      const input = drawer?.querySelector(`[data-direction-input="${trigger.dataset.dimension}"]`);
      if (input?.value.trim()) updateDirectionChoice(trigger.dataset.dimension, input.value.trim());
    } else if (action === "clear-directions") {
      state.directions = {};
      drawer?.querySelectorAll("[aria-pressed]").forEach((item) => item.setAttribute("aria-pressed", "false"));
      drawer?.querySelectorAll("[data-direction-result]").forEach((item) => { item.textContent = "可不选"; });
    } else if (action === "save-directions") {
      closeDrawer();
      document.querySelector('[data-action="open-directions"]')?.replaceChildren(document.createTextNode(Object.keys(state.directions).length ? `创作方向 · ${Object.keys(state.directions).length}` : "创作方向（可选）"));
    } else if (action === "save-series" || action === "save-material") {
      const value = drawer?.querySelector('input[name="assist-choice"]:checked')?.value || "本次不使用";
      const normalized = value === "本次不使用" ? "" : value;
      if (action === "save-series") state.series = normalized;
      else state.material = normalized;
      closeDrawer();
      const selector = action === "save-series" ? '[data-action="open-series"]' : '[data-action="open-material"]';
      const label = action === "save-series" ? "系列" : "素材";
      document.querySelector(selector)?.replaceChildren(document.createTextNode(normalized ? `${label} · ${normalized}` : label));
    } else if (action === "copy-link") {
      window.__UX01_COPIED = demoActivationUrl;
      navigator.clipboard?.writeText(demoActivationUrl).catch(() => {});
      toast("完整演示链接已复制");
    } else if (action === "copy-current") toast("已复制当前查看版本");
    else if (action === "export-current") toast("已导出当前查看版本");
    else if (action === "send-chat") toast("已发送，这次不会创建内容版本。");
    else if (action === "save-profile") toast("账号画像新版本已保存");
    else if (action === "save-password") toast("密码已更新，其他管理会话将退出");
    else if (action === "skip-motion") document.body.classList.add("motion-skipped");
    else if (action === "replay-motion") {
      document.querySelector(".home-mark")?.animate(
        [{ transform: "scale(.72)", opacity: .3 }, { transform: "scale(1)", opacity: 1 }],
        { duration: 7200, easing: "ease-out" },
      );
    }
  });

  document.addEventListener("change", (event) => {
    if (event.target.matches('input[name="member-role"]')) updateMemberRole(event.target.value);
    if (event.target.matches("[data-library-scope]")) {
      const region = document.querySelector("[data-region-choice]");
      if (region) region.hidden = event.target.value !== "region";
    }
  });

  document.addEventListener("input", (event) => {
    if (event.target.matches(".composer textarea")) state.drafts[event.target.dataset.draftKey] = event.target.value;
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && drawer) closeDrawer();
  });

  window.addEventListener("popstate", () => {
    currentScene = new URLSearchParams(location.search).get("scene") || "home";
    render();
  });

  window.UX01_PRODUCT = {
    get scene() { return currentScene; },
    state,
    go,
    supportsAction: (action) => supportedActions.has(action),
    openDrawer: (name) => {
      const trigger = document.querySelector(`[data-action="${name}"]`);
      trigger?.click();
    },
  };

  render();
})();
