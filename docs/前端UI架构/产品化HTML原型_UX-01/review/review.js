(() => {
  "use strict";
  const p = (label, scene, purpose, truth = "UX-02 目标") => ({ label, scene, purpose, truth });
  const journeys = {
    public: { label: "公共与认证", pages: [
      p("首页","home","访客理解产品并进入内容创作","当前能力 + 目标收敛"),
      p("租户用户登录","login-user","内容创作者进入自己的工作台","当前能力"),
      p("租户管理员登录","login-admin","管理员进入独立品牌管理空间","当前能力"),
      p("设置密码","activate","新成员通过一次性链接设置密码","当前能力"),
      p("链接失效","link-expired","链接过期后自然返回正确入口","当前能力 + 语言优化"),
      p("错入口","wrong-entry","错误角色不越权，并获得正确恢复动作","当前能力"),
      p("会话过期","session-expired","重新登录且不丢掉本机未提交输入","输入保护待 UX-02")
    ]},
    admin: { label: "租户管理员", pages: [
      p("概览","admin-overview","只看真实待办和近期变化","目标信息架构"),
      p("成员列表","admin-members","查看成员、入口和工作资格","当前能力"),
      p("创建身份","admin-member-create","建立一个自然人登录身份","当前能力 + 目标分步"),
      p("分配资格","admin-member-qualify","选择互斥入口、工作资格和发布账号","当前能力 + 目标分步"),
      p("完整激活链接","admin-activation","交付可点击、可复制的完整 HTTPS 链接","当前有缺陷，UX-02 阻断项"),
      p("发布账号","admin-account","理解逻辑账号与平台载体","当前能力"),
      p("多个平台","admin-platforms","同一账号拥有多个合法目标","当前能力"),
      p("五段画像","admin-profile","维护账号的一套表达身份","当前能力"),
      p("三级品牌资料","admin-library","管理品牌全员、总部、指定区域资料","当前能力"),
      p("团队使用","admin-usage","查看真实 7/30 日使用信息","当前能力"),
      p("能力诊断","admin-readiness","知道依据、缺口、影响和补充入口","当前能力")
    ]},
    creator: { label: "租户用户创作", pages: [
      p("空工作台","creator-empty","选择账号/平台后，一句话即可开始","目标信息架构"),
      p("低种子输入","creator-compose","不填写观点、受众和结构","目标双动作"),
      p("诚实生成状态","creator-generating","不伪造百分比，不暴露未核验草稿","当前能力"),
      p("完整 V1","creator-v1","一次呈现标题、正文、组织、制作和配文","当前能力 + 目标布局"),
      p("自然修改","creator-revision","用一句自然话提出修改","当前能力"),
      p("完整 V2","creator-v2","产生实质变化并保留 V1","当前能力"),
      p("回读 V1","creator-history-v1","历史版与当前版清楚区分","当前能力"),
      p("返回当前版","creator-current","从历史版回到 V2","当前能力"),
      p("复制与导出","creator-export","始终使用当前查看版本","当前能力"),
      p("失败恢复","creator-failure","网络失败时保留输入和原成品","部分能力，UX-02 统一")
    ]},
    dm01: { label: "DM01 纯文字参考", pages: [
      p("资格入口","dm-entry","只有获准用户看到陈列参考","当前能力"),
      p("现场与清单","dm-input","输入现场条件和商品数量","当前能力"),
      p("纯文字 V1","dm-v1","形成可读参考方案，不暗示绘图","当前能力"),
      p("局部 V2","dm-v2","只修改指定位置并保持总量","当前能力"),
      p("回读 V1","dm-history","历史方案和库存对账可读","当前能力")
    ]}
  };
  const one = (selector) => document.querySelector(selector);
  const all = (selector) => [...document.querySelectorAll(selector)];
  let journey = ""; let pages = []; let current = 0;
  const show = (index) => {
    if (!pages.length) return;
    current = Math.max(0, Math.min(index, pages.length - 1));
    const page = pages[current];
    one("[data-review-frame]").src = `../product/index.html?scene=${page.scene}`;
    one("[data-review-title]").textContent = page.label;
    one("[data-review-purpose]").textContent = `${page.purpose} · ${page.truth}`;
    one("[data-review-position]").textContent = `${journeys[journey].label} · ${current + 1} / ${pages.length}`;
    one("[data-open-raw]").href = `../product/index.html?scene=${page.scene}`;
    all("[data-page]").forEach((button) => button.classList.toggle("active", Number(button.dataset.page) === current));
    one("[data-prev]").disabled = current === 0;
    one("[data-next]").disabled = current === pages.length - 1;
  };
  const choose = (name) => {
    journey = name; pages = journeys[name].pages; current = 0;
    one("[data-page-list]").innerHTML = pages.map((page,index)=>`<button type="button" data-page="${index}"><span>${index+1}. ${page.label}</span><small>${page.truth}</small></button>`).join("");
    one("[data-journey-home]").hidden = true; one("[data-review-canvas]").hidden = false;
    one("[data-prev]").hidden = false; one("[data-next]").hidden = false; one("[data-open-raw]").hidden = false;
    all("[data-journey]").forEach((button)=>button.classList.toggle("active",button.dataset.journey===name));
    show(0);
  };
  all("[data-journey]").forEach((button)=>button.addEventListener("click",()=>choose(button.dataset.journey)));
  one("[data-page-list]").addEventListener("click",(event)=>{const target=event.target.closest("[data-page]");if(target)show(Number(target.dataset.page));});
  one("[data-prev]").addEventListener("click",()=>show(current-1)); one("[data-next]").addEventListener("click",()=>show(current+1));
  one("[data-home]").addEventListener("click",()=>location.reload());
  one("[data-desktop]").addEventListener("click",()=>{one("[data-review-canvas]").classList.remove("mobile");all("[data-viewport]").forEach(b=>b.classList.toggle("active",b.dataset.viewport==="desktop"));});
  one("[data-mobile]").addEventListener("click",()=>{one("[data-review-canvas]").classList.add("mobile");all("[data-viewport]").forEach(b=>b.classList.toggle("active",b.dataset.viewport==="mobile"));});
  document.addEventListener("keydown",(event)=>{if(!journey)return;if(event.altKey&&event.key==="ArrowRight")show(current+1);if(event.altKey&&event.key==="ArrowLeft")show(current-1);});
  window.UX01_REVIEW = { journeys, choose, show };
})();
