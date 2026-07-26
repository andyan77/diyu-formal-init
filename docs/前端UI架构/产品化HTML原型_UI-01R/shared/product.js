(() => {
  "use strict";

  const one = (selector, root = document) => root.querySelector(selector);
  const all = (selector, root = document) => [...root.querySelectorAll(selector)];
  let toastTimer = 0;

  function showToast(message) {
    const toast = one("[data-toast]");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2100);
  }

  function finishHomeMotion() {
    const motion = one("[data-home-motion]");
    if (!motion) return;
    motion.classList.add("is-complete");
    window.clearTimeout(Number(motion.dataset.timer || 0));
  }

  const homeMotion = one("[data-home-motion]");
  if (homeMotion) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      finishHomeMotion();
    } else {
      const timer = window.setTimeout(finishHomeMotion, 7200);
      homeMotion.dataset.timer = String(timer);
      homeMotion.addEventListener("click", finishHomeMotion);
      one("[data-home-skip]")?.addEventListener("click", finishHomeMotion);
    }
  }

  const authForm = one("[data-auth-form]");
  if (authForm) {
    const query = new URLSearchParams(window.location.search);
    const role = query.get("role") || "user";
    const mode = query.get("mode") || "login";
    const labels = {
      user: ["登录笛语", "继续内容与陈列工作", "content-workspace.html?view=home"],
      brand: ["品牌管理登录", "管理品牌、账号与内容演示", "brand-overview.html"],
      ops: ["笛语运维登录", "查看租户运行与需求反馈", "ops-home.html"],
    };
    const current = labels[role] || labels.user;
    one("[data-auth-title]")?.replaceChildren(document.createTextNode(mode === "activate" ? "设置登录密码" : current[0]));
    one("[data-auth-subtitle]")?.replaceChildren(document.createTextNode(mode === "activate" ? "设置完成后，将直接进入对应工作空间。" : current[1]));
    one("[data-auth-submit]")?.replaceChildren(document.createTextNode(mode === "activate" ? "完成并进入" : "登录"));
    one("[data-password-label]")?.replaceChildren(document.createTextNode(mode === "activate" ? "新密码" : "密码"));
    all("[data-login-fields]").forEach((field) => {
      field.hidden = mode === "activate" && field.dataset.loginFields === "username";
    });
    one("[data-confirm-field]")?.toggleAttribute("hidden", mode !== "activate");
    authForm.addEventListener("submit", (event) => {
      event.preventDefault();
      window.location.href = current[2];
    });
  }

  const hubView = one("[data-hub-view]");
  const workbenchView = one("[data-workbench-view]");
  const pageQuery = new URLSearchParams(window.location.search);
  if (hubView && workbenchView) {
    const view = pageQuery.get("view") || "home";
    hubView.hidden = view !== "home";
    workbenchView.hidden = view === "home";
  }

  all("[data-mobile-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const workbench = one("[data-workbench]");
      if (!workbench) return;
      workbench.dataset.mobileView = button.dataset.mobileTab || "conversation";
      all("[data-mobile-tab]").forEach((item) => {
        item.setAttribute("aria-selected", String(item === button));
      });
    });
  });

  const revisionForm = one("[data-revision-form]");
  if (revisionForm) {
    if (pageQuery.get("mode") === "create") {
      revisionForm.dataset.contentMode = "create";
      one("[data-workbench-title]")?.replaceChildren(document.createTextNode("开始下一篇"));
      one("[data-workbench-subtitle]")?.replaceChildren(document.createTextNode("自然输入 · 创作方向都可不选"));
      const thread = one("[data-thread]");
      if (thread) {
        const prompt = document.createElement("div");
        prompt.className = "message";
        prompt.textContent = "先说一个今天真正想表达的观察。写一句就够，其他部分我来整理。";
        thread.replaceChildren(prompt);
      }
      const textarea = one("textarea", revisionForm);
      if (textarea) textarea.placeholder = "例如：有人进店后只想自己看看，我想先给她一点空间……";
      one("[data-composer-help]")?.replaceChildren(document.createTextNode("先写一句真实想法，创作方向可以不选。"));
      one("[data-content-submit]")?.replaceChildren(document.createTextNode("生成成品"));
      const empty = one("[data-artifact-empty]");
      const content = one("[data-artifact-content]");
      if (empty) empty.hidden = false;
      if (content) content.hidden = true;
      one("[data-current-version]")?.replaceChildren(document.createTextNode("还没有成品"));
    }

    revisionForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const value = one("textarea", revisionForm)?.value.trim();
      const version = one("[data-current-version]");
      const count = one("[data-history-count]");
      const history = one("[data-history-list]");
      if (!value) {
        showToast("说一句想改的地方就可以。");
        return;
      }

      if (revisionForm.dataset.contentMode === "create") {
        const thread = one("[data-thread]");
        if (thread) {
          const userMessage = document.createElement("div");
          userMessage.className = "message message--self";
          userMessage.textContent = value;
          const response = document.createElement("div");
          response.className = "message";
          response.dataset.revisionNote = "";
          response.textContent = "已经整理成一份完整成品。想改哪里，继续像和同事说话一样告诉我。";
          thread.append(userMessage, response);
        }
        const empty = one("[data-artifact-empty]");
        const content = one("[data-artifact-content]");
        if (empty) empty.hidden = true;
        if (content) content.hidden = false;
        if (version) version.textContent = "当前版本 · V1";
        const historyBlock = one("[data-history]");
        if (historyBlock) historyBlock.hidden = true;
        if (history) history.replaceChildren();
        if (count) count.textContent = "历史版本（0）";
        revisionForm.dataset.contentMode = "revision";
        one("[data-content-submit]")?.replaceChildren(document.createTextNode("继续修改"));
        one("[data-composer-help]")?.replaceChildren(document.createTextNode("直接说想改什么，不必重新填写。"));
        const textarea = one("textarea", revisionForm);
        if (textarea) {
          textarea.value = "";
          textarea.placeholder = "例如：判断保留，开头再轻一点……";
        }
        showToast("第一版成品已经放在右侧。");
        if (window.innerWidth < 901) one('[data-mobile-tab="artifact"]')?.click();
        return;
      }

      const currentVersion = Number(version?.textContent.match(/V(\d+)/)?.[1] || 2);
      const nextVersion = currentVersion + 1;
      if (version) version.textContent = `当前版本 · V${nextVersion}`;
      if (count) count.textContent = `历史版本（${currentVersion}）`;
      const historyBlock = one("[data-history]");
      if (historyBlock) historyBlock.hidden = false;
      history?.insertAdjacentHTML(
        "afterbegin",
        `<div class="history-row"><span>V${currentVersion} · 修改前版本</span><button class="button button--quiet" type="button">查看</button></div>`,
      );
      one("[data-revision-note]")?.replaceChildren(document.createTextNode(`已按你的意思调整：${value}`));
      one("[data-artifact-title]")?.replaceChildren(document.createTextNode("想自己看一会儿，也不用急着回应"));
      one("[data-artifact-summary]")?.replaceChildren(
        document.createTextNode("这版把开头收得更轻：先承认独自浏览的需要，再从门店人物的位置给出一种不打扰、也不失联的相处方式。"),
      );
      one('[data-artifact-body="opening"]')?.replaceChildren(
        document.createTextNode("进店后想先自己看看，不需要马上进入一段对话。我会站在能被看见、又不会挡住衣服的位置。"),
      );
      one('[data-artifact-body="closing"]')?.replaceChildren(
        document.createTextNode("想问的时候，一抬头就能找到我；还没想好，也可以继续慢慢看。逛衣服本来就能有一点自己的安静。"),
      );
      one("[data-artifact-shot]")?.replaceChildren(
        document.createTextNode("手机固定，对着干净的墙和半个挂杆；先留两秒空画面。"),
      );
      one("[data-artifact-caption]")?.replaceChildren(
        document.createTextNode("想自己看一会儿，也是一种舒服的逛店节奏。#门店日常 #慢慢看"),
      );
      one("textarea", revisionForm).value = "";
      showToast("新版本已经放在右侧，旧版本仍可查看。");
      if (window.innerWidth < 901) one('[data-mobile-tab="artifact"]')?.click();
    });
  }

  all("[data-copy]").forEach((button) => {
    button.addEventListener("click", () => showToast("已复制当前成品。"));
  });

  all("[data-export]").forEach((button) => {
    button.addEventListener("click", () => showToast("已准备当前版本的导出文件。"));
  });

  const displayInput = one("[data-display-input-view]");
  const displayPlan = one("[data-display-plan-view]");
  if (displayInput && displayPlan && pageQuery.get("view") === "input") {
    displayInput.hidden = false;
    displayPlan.hidden = true;
    one("[data-display-version]")?.replaceChildren(document.createTextNode("新建方案"));
  }

  one("[data-display-input-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    if (displayInput) displayInput.hidden = true;
    if (displayPlan) displayPlan.hidden = false;
    one("[data-display-version]")?.replaceChildren(document.createTextNode("当前方案 · V1"));
    showToast("参考方案已按这次输入整理完成。");
  });

  all("[data-display-adjust]").forEach((button) => {
    button.addEventListener("click", () => {
      const mode = button.dataset.displayAdjust;
      const garments = all(".garment");
      garments.forEach((item) => item.classList.remove("is-muted", "is-focus", "is-spaced"));
      if (mode === "focus") {
        garments.forEach((item, index) => item.classList.toggle("is-muted", index > 1));
        garments[0]?.classList.add("is-focus");
      }
      if (mode === "breathe") {
        garments.forEach((item) => item.classList.add("is-spaced"));
      }
      if (mode === "swap") {
        const upper = one("[data-upper-group]");
        const lower = one("[data-lower-group]");
        const swapFirstTwo = (group) => {
          const first = group?.children[0];
          const second = group?.children[1];
          if (first && second) group.insertBefore(second, first);
        };
        swapFirstTwo(upper);
        swapFirstTwo(lower);
        const primary = one('[data-plan-step="primary"]');
        const secondary = one('[data-plan-step="secondary"]');
        const neutralFirst = upper?.children[0]?.getAttribute("title") === "米色针织";
        if (primary) {
          primary.innerHTML = neutralFirst
            ? "<strong>先挂米色针织和灰白下装</strong><br />先用轻一些的关系打开整面墙。"
            : "<strong>先挂砖红外套和深蓝下装</strong><br />它们组成第一眼能读懂的主推组。";
        }
        if (secondary) {
          secondary.innerHTML = neutralFirst
            ? "<strong>再用砖红外套和深蓝下装落重点</strong><br />上下层的深浅关系随后进入视线。"
            : "<strong>用米色与灰白回应</strong><br />上下层形成轻重变化，不挤在一起。";
        }
      }
      one("[data-display-version]")?.replaceChildren(document.createTextNode("当前方案 · V2"));
      one("[data-display-note]")?.replaceChildren(
        document.createTextNode(
          mode === "focus"
            ? "焦点组已前移，其余单品降低存在感。"
            : mode === "breathe"
              ? "画面已拉开相近颜色的距离，拿取关系更清楚。"
              : "两层的第一组关系已经交换，右侧执行顺序也同步改变。",
        ),
      );
      showToast("局部调整已呈现在方案图里。");
    });
  });

  function closeDrawer() {
    one("[data-drawer]")?.classList.remove("is-open");
    one("[data-drawer-backdrop]")?.classList.remove("is-open");
    document.body.classList.remove("no-scroll");
  }

  all("[data-open-drawer]").forEach((button) => {
    button.addEventListener("click", () => {
      one("[data-drawer]")?.classList.add("is-open");
      one("[data-drawer-backdrop]")?.classList.add("is-open");
      document.body.classList.add("no-scroll");
    });
  });

  all("[data-close-drawer], [data-drawer-backdrop]").forEach((button) => {
    button.addEventListener("click", closeDrawer);
  });

  one("[data-brand-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    closeDrawer();
    one("[data-brand-gap]")?.replaceChildren(document.createTextNode("商品资料已补充，品牌现在可以直接开始创作。"));
    showToast("商品资料已加入品牌空间。");
  });

  let activeFeedback = null;
  const feedbackEditor = one("[data-feedback-editor]");
  const openFeedback = (item) => {
    if (!item || !feedbackEditor) return;
    all("[data-feedback-item]").forEach((candidate) => candidate.classList.remove("is-active"));
    item.classList.add("is-active");
    activeFeedback = item;
    feedbackEditor.hidden = false;
    const title = one("strong", item)?.textContent || "需求反馈";
    one("[data-feedback-editor-title]")?.replaceChildren(document.createTextNode(title));
    one("[data-ops-title]")?.replaceChildren(document.createTextNode("正在处理一条需求。"));
    const trigger = one("[data-open-feedback]");
    if (trigger) trigger.hidden = true;
    feedbackEditor.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  one("[data-open-feedback]")?.addEventListener("click", () => {
    openFeedback(all("[data-feedback-item]").find((item) => !item.hidden));
  });

  all("[data-feedback-action]").forEach((button) => {
    button.addEventListener("click", () => openFeedback(button.closest("[data-feedback-item]")));
  });

  one("[data-feedback-complete]")?.addEventListener("click", () => {
    if (!activeFeedback || !feedbackEditor) return;
    activeFeedback.hidden = true;
    activeFeedback.classList.remove("is-active");
    activeFeedback = null;
    feedbackEditor.hidden = true;
    const remaining = all("[data-feedback-item]").filter((item) => !item.hidden);
    one("[data-feedback-count]")?.replaceChildren(document.createTextNode(String(remaining.length)));
    one("[data-ops-title]")?.replaceChildren(
      document.createTextNode(remaining.length ? `已回复 1 条，还有 ${remaining.length} 条待处理。` : "今天的需求已经处理完。"),
    );
    const nextTitle = one("strong", remaining[0])?.textContent;
    one("[data-ops-priority-title]")?.replaceChildren(
      document.createTextNode(nextTitle ? `下一条：“${nextTitle}”` : "需求反馈已经清空"),
    );
    one("[data-ops-priority-copy]")?.replaceChildren(
      document.createTextNode(nextTitle ? "打开后完成分类，并给提交者一段可直接理解的回复。" : "服务保持正常，暂时没有新的需求需要处理。"),
    );
    const trigger = one("[data-open-feedback]");
    if (trigger) trigger.hidden = remaining.length === 0;
    showToast("分类和回复都已完成，待处理数量已更新。");
  });

  all("[data-open-dialog]").forEach((button) => {
    button.addEventListener("click", () => one(`#${button.dataset.openDialog}`)?.showModal());
  });

  all("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog")?.close());
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawer();
  });
})();
