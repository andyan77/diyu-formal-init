(() => {
  "use strict";
  const { esc, logo, button, status, shell, adminNav } = window.UX;
  const query = new URLSearchParams(location.search);
  const scene = query.get("scene") || "home";
  const app = document.querySelector("#app");

  const auth = ({ kind = "user", title, intro, action = "登录", note = "", expired = false }) => `
    <main id="main" class="auth">
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
          ${expired ? `<div class="button-row">${button("返回登录", { primary: true, go: kind === "admin" ? "login-admin" : "login-user" })}</div>` : `
          <form>
            ${kind === "activate" ? "" : `<label>用户名<input autocomplete="username" value="${kind === "admin" ? "brand-admin" : "zhou-ning"}"></label>`}
            <label>${kind === "activate" ? "设置密码" : "密码"}<input type="password" value="long-password-demo" autocomplete="${kind === "activate" ? "new-password" : "current-password"}"></label>
            ${kind === "activate" ? `<label>再次输入<input type="password" value="long-password-demo" autocomplete="new-password"></label>` : ""}
            ${button(action, { primary: true, go: kind === "admin" ? "admin-overview" : kind === "activate" ? "creator-empty" : "creator-empty" })}
          </form>`}
        </div>
      </section>
    </main>`;

  const pageHead = (eyebrow, title, action = "") => `
    <header class="page-heading"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1></div>${action}</header>`;
  const metric = (label, value, note) => `<div class="metric card"><small>${label}</small><strong>${value}</strong><small>${note}</small></div>`;
  const admin = (active, title, body) => shell({
    role: "admin", nav: adminNav, active, title, meta: "笛语服饰", body: `<main id="main" class="page">${body}</main>`
  });

  const memberTable = () => `<div class="table-card card">
    <div class="table-row"><strong>周宁</strong><span>内容创作</span><span>品牌官方账号</span>${status("可使用","good")}</div>
    <div class="table-row"><strong>苏予</strong><span>陈列参考</span><span>柯桥门店</span>${status("可使用","good")}</div>
    <div class="table-row"><strong>林予</strong><span>品牌管理</span><span>不进入创作端</span>${status("可使用","good")}</div>
  </div>`;

  const adminScenes = {
    "admin-overview": () => admin("overview", "概览", `
      ${pageHead("品牌管理","今天需要处理什么")}
      <div class="metric-grid">${metric("已启用成员","7","比上周 +1")}${metric("近 7 日使用","5 人","有真实操作")}${metric("待补资料","2 项","影响商品内容")}${metric("账号变化","1 项","新增小红书图文")}</div>
      <section class="work-list"><h2>当前待办</h2>
        <article class="work-item card"><div><h3>补充 ZX-C218 的公开商品事实</h3><p class="muted">缺少面料与适用范围，暂不支持对应商品表达。</p></div>${button("去补资料",{primary:true,go:"admin-library"})}</article>
        <article class="work-item card"><div><h3>把新成员加入发布账号</h3><p class="muted">周宁已有内容资格，还没有可操作的发布账号。</p></div>${button("查看成员",{go:"admin-members"})}</article>
      </section>`),
    "admin-members": () => admin("members","成员与资格",`${pageHead("成员与资格","谁可以进入哪里",button("添加成员",{primary:true,go:"admin-member-create"}))}${memberTable()}`),
    "admin-member-create": () => admin("members","成员与资格",`${pageHead("添加成员","先建立登录身份")}
      <div class="drawer-layer"><aside class="drawer"><header><div><p class="eyebrow">第 1 步</p><h2>成员基本信息</h2></div>${button("关闭",{go:"admin-members"})}</header>
      <form><label>姓名或工作名<input value="门店内容小周"></label><label>登录用户名<input value="store-zhou"></label>
      <label>所属团队<select><option>浙江区域门店</option></select></label>${button("继续分配资格",{primary:true,go:"admin-member-qualify"})}</form></aside></div>`),
    "admin-member-qualify": () => admin("members","成员与资格",`${pageHead("添加成员","分配入口与工作资格")}
      <div class="drawer-layer"><aside class="drawer"><header><div><p class="eyebrow">第 2 步</p><h2>这个成员要做什么</h2></div>${button("关闭",{go:"admin-members"})}</header>
      <form><div class="option-grid"><div class="option"><strong>租户用户</strong><p class="muted">进入内容创作或陈列参考</p></div><div class="option"><strong>租户管理员</strong><p class="muted">只进入品牌管理</p></div></div>
      <label>工作资格<select><option>内容创作</option><option>陈列参考</option></select></label>
      <label>可操作的发布账号<select><option>笛语服饰品牌官方账号</option></select></label>
      ${button("创建并生成激活链接",{primary:true,go:"admin-activation"})}</form></aside></div>`),
    "admin-activation": () => admin("members","成员与资格",`${pageHead("成员已创建","把链接安全交给本人")}
      <div class="card" style="padding:28px;max-width:760px"><div class="flow"><div class="done">身份已建立</div><div class="done">资格已分配</div><div class="active">等待本人设置密码</div><div>首次登录</div></div>
      <div class="link-box"><strong>一次性激活链接</strong><a href="https://diyuai.cc/activate/ux01-example-token">https://diyuai.cc/activate/ux01-example-token</a><small>使用一次后失效。请通过受保护的渠道交付。</small></div>
      <div class="button-row" style="margin-top:18px">${button("复制完整链接",{primary:true,action:"copy-link"})}${button("返回成员列表",{go:"admin-members"})}</div></div>`),
    "admin-account": () => admin("accounts","发布账号",`${pageHead("发布账号","一套表达身份，可以去多个平台",button("创建发布账号",{primary:true,go:"admin-profile"}))}
      <article class="card" style="padding:24px"><div class="page-heading"><div><h2>笛语服饰品牌官方账号</h2><p class="muted">机构账号 · 总部品牌内容组</p></div>${button("查看五段画像",{go:"admin-profile"})}</div>
      <div class="button-row">${status("小红书图文","good")}${status("小红书视频","good")}${status("抖音视频","good")}${button("管理平台",{go:"admin-platforms"})}</div></article>`),
    "admin-platforms": () => admin("accounts","发布账号",`${pageHead("笛语服饰品牌官方账号","选择这个账号可以去哪里")}
      <div class="card" style="padding:24px"><div class="table-row"><strong>小红书</strong><span>图文</span><span>周宁</span>${status("已启用","good")}</div>
      <div class="table-row"><strong>小红书</strong><span>视频</span><span>周宁</span>${status("已启用","good")}</div>
      <div class="table-row"><strong>抖音</strong><span>视频</span><span>宋言</span>${status("已启用","good")}</div></div>
      <div class="button-row" style="margin-top:18px">${button("添加平台",{primary:true,action:"toast-add-platform"})}${button("返回账号",{go:"admin-account"})}</div>`),
    "admin-profile": () => admin("accounts","账号画像",`${pageHead("笛语服饰品牌官方账号","五段画像")}
      <div class="card" style="padding:26px"><div class="work-list">
      <div><small>身份位置</small><p>品牌日常表达的组织者，不代替门店或顾客讲经历。</p></div>
      <div><small>可以代表什么</small><p>已确认的品牌选择、商品事实与当篇观察。</p></div>
      <div><small>与受众的关系</small><p>平等、克制，像熟悉服装的人认真分享。</p></div>
      <div><small>长期内容领地</small><p>穿搭选择、门店观察、女性日常与品牌判断。</p></div>
      <div><small>默认制作条件</small><p>一人、一部手机、普通室内和已有商品素材。</p></div></div>
      <div class="button-row" style="margin-top:18px">${button("保存新版本",{primary:true,action:"toast-profile"})}${button("返回账号",{go:"admin-account"})}</div></div>`),
    "admin-library": () => admin("library","品牌资料库",`${pageHead("品牌资料库","资料来自哪里，谁可以使用",button("新增资料",{primary:true,action:"toast-library"}))}
      <div class="button-row" style="margin-bottom:18px">${status("品牌全员","good")}${status("总部专用")}${status("指定区域")}</div>
      <div class="table-card card"><div class="table-row"><strong>品牌表达基线</strong><span>品牌全员</span><span>总部品牌部 · V3</span>${status("当前","good")}</div>
      <div class="table-row"><strong>ZX-C218 商品事实</strong><span>总部专用</span><span>商品部 · V2</span>${status("当前","good")}</div>
      <div class="table-row"><strong>浙江门店拍摄条件</strong><span>指定区域</span><span>浙江区域 · V1</span>${status("当前","good")}</div></div>`),
    "admin-usage": () => admin("usage","团队使用",`${pageHead("团队使用","最近谁在使用，做了什么")}
      <div class="button-row" style="margin-bottom:18px">${button("近 7 日",{primary:true})}${button("近 30 日",{action:"toast-30"})}</div>
      <div class="metric-grid">${metric("活跃成员","5","7 名已启用")}${metric("内容尝试","18","成功 14")}${metric("陈列尝试","3","成功 3")}${metric("已记录用量","28,640","仅为系统记录")}</div>
      <div class="table-card card"><div class="table-row"><strong>周宁</strong><span>11 次内容</span><span>小红书图文</span>${status("今天使用","good")}</div><div class="table-row"><strong>苏予</strong><span>3 次陈列</span><span>柯桥门店</span>${status("3 天前")}</div></div>`),
    "admin-readiness": () => admin("readiness","能力诊断",`${pageHead("能力诊断","缺什么，会影响哪项工作")}
      <div class="work-list">
      <article class="work-item card"><div>${status("待补","warn")}<h3>商品内容</h3><p>依据：ZX-C218 已有名称和品类。缺少：公开面料与适用范围。影响：不能写商品硬事实。</p></div>${button("去补商品资料",{primary:true,go:"admin-library"})}</article>
      <article class="work-item card"><div>${status("可用","good")}<h3>非商品内容</h3><p>依据：品牌表达基线 V3、账号画像 V2。当前可直接创作。</p></div></article>
      <article class="work-item card"><div>${status("有条件","warn")}<h3>陈列参考</h3><p>依据：柯桥店挂杆结构已记录。缺少本次库存时，需要先补一份商品清单。</p></div></article>
      </div>`),
    "admin-security": () => admin("security","账户安全",`${pageHead("账户安全","保护你的管理入口")}
      <div class="card" style="padding:26px;max-width:660px"><h2>修改密码</h2><p class="muted">更新后，其他浏览器中的管理会话会退出。</p>
      <label>当前密码<input type="password" value="current-password"></label><label>新密码<input type="password" value="new-password-long"></label>
      <div class="button-row" style="margin-top:16px">${button("更新密码",{primary:true,action:"toast-password"})}</div></div>`)
  };

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

发布配文｜本段为情景演绎。碗没有立场，人可以先休息。`
  };
  const creator = (view, body, options = {}) => `
    <main id="main" class="creator-shell">
      <header class="creator-topbar"><a href="?scene=creator-empty">${logo()}</a>
        <div class="context-controls"><select aria-label="发布账号"><option>笛语服饰品牌官方账号</option><option>柯桥门店日常</option></select>
        <select aria-label="平台与形式"><option>小红书 · 图文</option><option>小红书 · 视频</option><option>抖音 · 视频</option></select></div>
        <button class="quiet">账号画像</button></header>
      <div class="creator-grid" data-view="${view}">
        <aside class="history"><button data-go="creator-empty">＋ 新创作</button><p class="muted">最近</p><button class="${options.version === 2 ? "active" : ""}">今晚，两只碗决定暂时休战<small> V2</small></button><button>门店里最安静的十分钟<small> V1</small></button></aside>
        ${body}
      </div>
      <nav class="mobile-tabs"><button class="${view === "conversation" ? "active" : ""}" data-view="conversation">对话</button><button class="${view === "artifact" ? "active" : ""}" data-view="artifact">成品</button></nav>
    </main>`;
  const messages = (items) => `<section class="messages">${items.map(([who,text])=>`<article class="message ${who}"><p>${esc(text)}</p></article>`).join("")}</section>`;
  const composer = ({ value = "", current = 0, loading = false, error = false }) => `<div class="composer">
    <textarea aria-label="${current ? "修改要求" : "说一句话就可以"}">${esc(value)}</textarea>
    <div class="composer-tools"><div>${button("创作方向（可选）",{action:"toggle-direction"})}${button("系列")}${button("素材")}</div><small>输入会保留到完成或你主动清空</small></div>
    <div class="composer-actions"><button class="quiet" data-action="send-chat">发送</button>${button(loading ? "正在整理…" : current ? `修改成 V${current+1}` : "生成内容",{primary:true,go:current?"creator-v2":"creator-generating"})}</div>
    ${error?`<div class="status bad">网络中断，原始输入已经保留。</div>`:""}</div>`;
  const artifact = (version, viewed = version) => `<section class="artifact">
    <header class="artifact-head"><div><p class="eyebrow">${viewed === version ? `当前版 · V${version}` : `历史版 · V${viewed}`}</p><h1>${viewed === 1 ? "忙完一天，别让两只碗替你们吵架" : "今晚，两只碗决定暂时休战"}</h1></div>
    <div class="button-row">${button("复制",{action:"toast-copy"})}${button("导出",{action:"toast-export"})}</div></header>
    ${viewed !== version?`<div class="status warn" style="margin-top:18px">正在回读 V${viewed}　<a href="?scene=creator-current">回到当前 V${version}</a></div>`:""}
    <div class="artifact-section"><h2>完整发布正文</h2><div class="artifact-copy">${esc(viewed===1?artifactText.v1:artifactText.v2)}</div></div>
    <div class="artifact-section"><h2>图文组织</h2><p>1. 标题卡　2. 真实片段　3. 观察或演绎　4. 收束与互动</p></div>
    <div class="artifact-section"><h2>制作提示</h2><p>使用文字卡、已有室内环境和一人旁白；不新增演员或道具。</p></div>
    <p class="muted">AI 辅助生成 · 发布前请按平台要求完成标识。</p></section>`;
  const conversationPane = (content, compose) => `<section class="conversation">${content}${compose}</section>`;
  const creatorScenes = {
    "creator-empty": () => creator("conversation",`${conversationPane(`<div class="messages"><div><p class="eyebrow">小红书 · 图文</p><h1>今天想说什么？</h1><p class="muted">一句感悟、一段流水账、一个商品，或者“今天不知道发什么”都可以。</p></div></div>`,composer({}))}<section class="artifact"><div class="card" style="padding:28px"><h2>成品会出现在这里</h2><p class="muted">生成完成前，不展示尚未核验的草稿。</p></div></section>`),
    "creator-compose": () => creator("conversation",`${conversationPane(messages([["user","今天店里忙了一天，回家因为洗碗拌了两句，帮我发条小红书。"]]),composer({value:"今天店里忙了一天，回家因为洗碗拌了两句，帮我发条小红书。"}))}<section class="artifact"><div class="card" style="padding:28px"><h2>准备生成完整小红书</h2><p>无需再填写观点、受众或结构。</p></div></section>`),
    "creator-generating": () => creator("conversation",`${conversationPane(messages([["user","今天店里忙了一天，回家因为洗碗拌了两句，帮我发条小红书。"],["assistant","正在把这段生活整理成一篇完整内容。"]]),`<div class="card" role="status" style="padding:18px"><strong>正在整理成品</strong><p class="muted">完成检查后会一次呈现，不展示未完成草稿。</p></div>`)}<section class="artifact"><div class="card" style="padding:28px"><h2>内容还在整理</h2></div></section>`),
    "creator-v1": () => creator("artifact",`${conversationPane(messages([["user","今天店里忙了一天，回家因为洗碗拌了两句，帮我发条小红书。"],["assistant","V1 已经整理好，可以直接阅读或继续修改。"]]),composer({current:1}))}${artifact(1)}`,{version:1}),
    "creator-revision": () => creator("conversation",`${conversationPane(messages([["assistant","V1 已经整理好，可以直接阅读或继续修改。"],["user","别讲道理，荒诞一点。"]]),composer({value:"别讲道理，荒诞一点。",current:1}))}${artifact(1)}`,{version:1}),
    "creator-v2": () => creator("artifact",`${conversationPane(messages([["assistant","已改成 V2，V1 完整保留。"]]),composer({current:2}))}${artifact(2)}`,{version:2}),
    "creator-history-v1": () => creator("artifact",`${conversationPane(messages([["assistant","正在回读 V1。"]]),composer({current:2}))}${artifact(2,1)}`,{version:2}),
    "creator-current": () => creator("artifact",`${conversationPane(messages([["assistant","已回到当前 V2。"]]),composer({current:2}))}${artifact(2)}`,{version:2}),
    "creator-export": () => creator("artifact",`${conversationPane(messages([["assistant","复制和导出都以当前查看版本为准。"]]),composer({current:2}))}${artifact(2)}`,{version:2}),
    "creator-failure": () => creator("conversation",`${conversationPane(messages([["user","再改得轻一点，但保留前两段。"]]),composer({value:"再改得轻一点，但保留前两段。",current:2,error:true}))}${artifact(2)}`,{version:2})
  };

  const dm = (body) => `<main id="main"><header class="creator-topbar"><a href="?scene=dm-entry">${logo()}</a><strong>陈列参考</strong><span></span></header><section class="dm-main">${body}</section></main>`;
  const plan = (version=1) => `<div class="card" style="padding:24px"><div class="page-heading"><div><p class="eyebrow">当前版 · V${version}</p><h2>墙面挂杆文字参考方案</h2></div>${button("复制",{action:"toast-copy"})}</div>
    <p><strong>库存对账：</strong>共 30 件；建议 18 件上墙，12 件暂不上墙。</p>
    <div class="inventory-list"><div class="inventory-row"><span>左侧挂杆</span><strong>6 件</strong></div><div class="inventory-row"><span>主焦点区</span><strong>${version===1?"6":"7"} 件</strong></div><div class="inventory-row"><span>右侧挂杆</span><strong>${version===1?"6":"5"} 件</strong></div><div class="inventory-row"><span>暂不上墙</span><strong>12 件</strong></div></div>
    <p class="muted">这是一份可直接阅读和执行的文字参考方案。</p></div>`;
  const dmScenes = {
    "dm-entry":()=>dm(`${pageHead("陈列参考","用现场条件和商品清单开始")}<div class="card" style="padding:26px"><p>当前账号具备陈列参考资格。系统只生成纯文字参考方案。</p>${button("新建参考方案",{primary:true,go:"dm-input"})}</div>`),
    "dm-input":()=>dm(`${pageHead("新参考方案","告诉我这次现场有什么")}<div class="dm-grid"><div class="card" style="padding:22px"><label>现场条件<textarea>柯桥店墙面挂杆，左中右三段；中间适合主焦点。</textarea></label><label>商品清单<textarea>ZX-C218 8 件；ZX-P211 10 件；ZX-V005 12 件。</textarea></label>${button("生成文字方案",{primary:true,go:"dm-v1"})}</div><div class="card" style="padding:24px"><h2>本次清单</h2><p>3 个商品 · 共 30 件</p><p class="muted">笛语只整理文字安排，不会自动执行陈列。</p></div></div>`),
    "dm-v1":()=>dm(`${pageHead("墙面挂杆参考方案","已保存 V1")}<div class="dm-grid"><div>${plan(1)}</div><div class="card" style="padding:22px"><label>只想改哪里<textarea>中间主焦点多放一件，其他总量不变。</textarea></label>${button("修改成 V2",{primary:true,go:"dm-v2"})}</div></div>`),
    "dm-v2":()=>dm(`${pageHead("墙面挂杆参考方案","已保存 V2")}<div class="dm-grid"><div>${plan(2)}</div><div class="card" style="padding:22px"><h2>历史版本</h2><button data-go="dm-history">阅读 V1</button><p class="muted">V1 和 V2 都保留自己的库存对账。</p></div></div>`),
    "dm-history":()=>dm(`${pageHead("墙面挂杆参考方案","正在回读 V1")}<div class="dm-grid"><div>${plan(1)}</div><div class="card" style="padding:22px"><p>${status("历史版","warn")}</p><p>当前版本是 V2。</p>${button("回到当前 V2",{primary:true,go:"dm-v2"})}</div></div>`)
  };

  const scenes = {
    home: () => `<main id="main" class="home"><nav class="quiet-links"><a href="?scene=login-admin">品牌管理</a><a href="?scene=login-user">内容创作</a></nav>
      <section class="home-stage"><div class="home-mark"><img src="../../../../assets/brand/diyu-vi/svg/diyu-symbol.svg" alt=""></div>
      <p class="eyebrow">一句种子，长成品牌自己的表达</p><h1>把今天想说的，变成可以发出的内容。</h1><p>不需要先写选题、结构或完整故事。说一句，笛语来完成。</p>${button("开始创作",{primary:true,go:"login-user"})}</section>
      <div class="motion-actions">${button("跳过动效",{quiet:true,action:"skip-motion"})}${button("重播",{quiet:true,action:"replay-motion"})}</div></main>`,
    "login-user":()=>auth({title:"登录内容创作",intro:"从一句生活种子，直接得到完整成品。"}),
    "login-admin":()=>auth({kind:"admin",title:"登录品牌管理",intro:"把成员、账号和资料放在正确的位置。"}),
    activate:()=>auth({kind:"activate",title:"设置你的密码",intro:"欢迎加入笛语。",action:"完成设置"}),
    "link-expired":()=>auth({kind:"user",title:"这个链接已经失效",intro:"一次性链接只在有效期内使用。",note:"请联系租户管理员重新生成链接。",expired:true}),
    "wrong-entry":()=>auth({kind:"admin",title:"这里不是你的工作入口",intro:"当前账号用于内容创作。",note:"请返回内容创作入口继续。",expired:true}),
    "session-expired":()=>auth({kind:"user",title:"登录已过期",intro:"你的输入仍保留在这台设备上。",note:"重新登录后可以继续刚才的内容。",expired:true}),
    ...adminScenes, ...creatorScenes, ...dmScenes
  };

  const render = () => {
    app.innerHTML = (scenes[scene] || scenes.home)();
    document.title = `${document.querySelector("h1,h2")?.textContent || "笛语"} · 笛语`;
  };
  render();

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-go],[data-action],[data-view]");
    if (!trigger) return;
    if (trigger.dataset.go) {
      location.href = `?scene=${encodeURIComponent(trigger.dataset.go)}`;
      return;
    }
    if (trigger.dataset.view) {
      document.querySelector(".creator-grid")?.setAttribute("data-view", trigger.dataset.view);
      document.querySelectorAll("[data-view]").forEach(item => item.classList.toggle("active", item === trigger));
      return;
    }
    const action = trigger.dataset.action || "";
    if (action === "toggle-direction") {
      const box = document.createElement("div");
      box.className = "card";
      box.style.cssText = "padding:14px;margin-top:10px";
      box.innerHTML = "<strong>创作方向（可选）</strong><p class='muted'>题材 · 讲法 · 风格 · 形式 · 系列 · 互动。全部可以不选。</p>";
      trigger.closest(".composer")?.append(box);
      trigger.disabled = true;
      return;
    }
    if (action === "skip-motion") document.body.classList.add("motion-skipped");
    if (action === "replay-motion") {
      const mark = document.querySelector(".home-mark");
      mark?.animate([{transform:"scale(.72)",opacity:.3},{transform:"scale(1)",opacity:1}],{duration:7200,easing:"ease-out"});
    }
    if (action === "send-chat") {
      const toast = document.createElement("div"); toast.className = "toast"; toast.textContent = "已发送，这次不会创建内容版本。"; document.body.append(toast); setTimeout(()=>toast.remove(),1800); return;
    }
    if (action.startsWith("toast") || action === "copy-link") {
      const toast = document.createElement("div"); toast.className = "toast";
      toast.textContent = action === "copy-link" ? "完整链接已复制" : action === "toast-copy" ? "已复制当前查看版本" : action === "toast-export" ? "已导出当前查看版本" : "已保存";
      document.body.append(toast); setTimeout(()=>toast.remove(),1800);
    }
  });
})();
