(() => {
  "use strict";

  const one = (selector, root = document) => root.querySelector(selector);
  const all = (selector, root = document) => [...root.querySelectorAll(selector)];
  const query = new URLSearchParams(window.location.search);

  const setText = (selector, value, root = document) => {
    const element = one(selector, root);
    if (element) element.textContent = value;
  };

  const replaceQuery = (changes) => {
    const next = new URLSearchParams(window.location.search);
    Object.entries(changes).forEach(([key, value]) => {
      if (value === null || value === undefined || value === "") next.delete(key);
      else next.set(key, value);
    });
    const suffix = next.toString();
    window.history.replaceState({}, "", `${window.location.pathname}${suffix ? `?${suffix}` : ""}`);
  };

  const isReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Public home */

  const introShell = one(".intro-shell");
  if (introShell) {
    const motion = one("[data-intro-motion]");
    const skip = one("[data-intro-skip]");
    let timer = 0;

    const finish = () => {
      window.clearTimeout(timer);
      introShell.classList.add("is-ready");
      introShell.dataset.motionState = "complete";
      one(".public-home__content", introShell)?.removeAttribute("inert");
    };

    if (isReducedMotion) {
      finish();
      introShell.dataset.motionState = "reduced";
    } else {
      introShell.dataset.motionState = "playing";
      timer = window.setTimeout(finish, 7400);
      motion?.addEventListener("click", finish);
      motion?.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          finish();
        }
      });
      skip?.addEventListener("click", (event) => {
        event.stopPropagation();
        finish();
      });
    }
  }

  /* Authentication and human recovery */

  const authForm = one("[data-auth-form]");
  if (authForm) {
    const entry = query.get("entry") || "creator";
    const mode = query.get("mode") || "login";
    const entries = {
      creator: {
        eyebrow: "创作空间",
        title: "登录创作空间",
        subtitle: "继续内容与陈列工作",
        quote: "把今天想说的话，整理成真正属于品牌的表达。",
        target: "creator.html?role=store&task=content&state=empty",
      },
      admin: {
        eyebrow: "品牌管理",
        title: "登录品牌管理",
        subtitle: "管理成员、发布账号和团队资料",
        quote: "让每个账号在清楚的身份和资料边界里工作。",
        target: "tenant-admin.html?view=overview",
      },
      ops: {
        eyebrow: "笛语运维",
        title: "登录笛语运维",
        subtitle: "处理租户状态与需求反馈",
        quote: "把需要处理的事放到眼前，把其他信息留在恰当的位置。",
        target: "ops.html",
      },
    };
    const current = entries[entry] || entries.creator;

    setText("[data-auth-eyebrow]", current.eyebrow);
    setText("[data-auth-title]", mode === "activate" ? "设置登录密码" : current.title);
    setText(
      "[data-auth-subtitle]",
      mode === "activate" ? "完成后会直接进入为你开通的工作空间。" : current.subtitle,
    );
    setText("[data-auth-quote]", current.quote);
    setText("[data-auth-submit]", mode === "activate" ? "完成并进入" : "登录");
    setText("[data-password-label]", mode === "activate" ? "新密码" : "密码");
    setText(
      "[data-auth-help]",
      mode === "activate"
        ? "这个页面只用于本人完成首次设置。"
        : "忘记密码时，请联系为你开通账号的团队成员。",
    );

    const username = one("[data-login-username]");
    const confirm = one("[data-confirm-password]");
    const password = one('input[name="password"]', authForm);
    const confirmInput = one('input[name="password-confirm"]', authForm);
    if (mode === "activate") {
      if (username) username.hidden = true;
      const usernameInput = one('input[name="username"]', authForm);
      if (usernameInput) usernameInput.disabled = true;
      if (confirm) confirm.hidden = false;
      if (password) password.autocomplete = "new-password";
      if (confirmInput) confirmInput.required = true;
    }

    authForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!authForm.reportValidity()) return;
      if (mode === "activate" && password?.value !== confirmInput?.value) {
        confirmInput?.setCustomValidity("两次输入需要一致。");
        confirmInput?.reportValidity();
        return;
      }
      confirmInput?.setCustomValidity("");
      window.location.href = current.target;
    });
  }

  const recoveryPrimary = one("[data-recovery-primary]");
  if (recoveryPrimary) {
    const entry = query.get("entry") || "creator";
    const recovery = {
      creator: ["当前账号没有创作空间的使用资格。", "返回创作空间登录"],
      admin: ["当前账号没有品牌管理资格。", "返回品牌管理登录"],
      ops: ["当前账号没有笛语运维资格。", "返回笛语运维登录"],
    };
    const current = recovery[entry] || recovery.creator;
    setText("[data-recovery-title]", current[0]);
    setText("[data-recovery-primary]", current[1]);
    recoveryPrimary.href = `login.html?entry=${entry}`;
  }

  /* Tenant management */

  const adminView = one("[data-admin-view]");
  if (adminView) {
    const requested = query.get("view") || "overview";
    const knownViews = ["overview", "members", "accounts", "library", "readiness"];
    const view = knownViews.includes(requested) ? requested : "overview";
    const labels = {
      overview: "概览与待处理",
      members: "成员与权限",
      accounts: "发布账号",
      library: "品牌、商品与组织素材",
      readiness: "生产就绪与缺口",
    };
    all("[data-admin-view]").forEach((item) => {
      item.hidden = item.dataset.adminView !== view;
    });
    all("[data-admin-nav]").forEach((item) => {
      item.classList.toggle("is-current", item.dataset.adminNav === view);
      if (item.dataset.adminNav === view) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    setText("[data-admin-location]", labels[view]);

    const nav = one(".management-nav");
    const backdrop = one("[data-admin-backdrop]");
    const drawer = one("[data-admin-drawer]");
    const stopDialog = one("[data-stop-member-dialog]");
    let adminReturnFocus = null;
    const activePrimaryActions = () =>
      all("[data-admin-primary]").filter((item) => !item.closest("[hidden]"));

    const closeAdminOverlays = () => {
      nav?.classList.remove("is-open");
      drawer?.classList.remove("is-open");
      drawer?.setAttribute("aria-hidden", "true");
      backdrop?.classList.remove("is-open");
      document.body.classList.remove("no-scroll");
      all("[data-admin-primary]").forEach((item) => {
        if (item.dataset.overlayHidden === "true") {
          item.hidden = false;
          delete item.dataset.overlayHidden;
        }
      });
      adminReturnFocus?.focus?.();
      adminReturnFocus = null;
    };

    one("[data-management-menu]")?.addEventListener("click", () => {
      adminReturnFocus = one("[data-management-menu]");
      nav?.classList.add("is-open");
      backdrop?.classList.add("is-open");
      document.body.classList.add("no-scroll");
      one("a", nav)?.focus();
    });

    const openAdminDrawer = (kind, trigger) => {
      adminReturnFocus = trigger;
      activePrimaryActions().forEach((item) => {
        item.dataset.overlayHidden = "true";
        item.hidden = true;
      });
      const memberForm = one("[data-member-form]");
      const accountForm = one("[data-account-form]");
      if (memberForm) memberForm.hidden = kind !== "member";
      if (accountForm) accountForm.hidden = kind !== "account";
      setText("[data-drawer-eyebrow]", kind === "member" ? "成员与权限" : "发布账号");
      setText("[data-drawer-title]", kind === "member" ? "添加成员" : "建立发布账号");
      if (drawer) drawer.dataset.returnFocus = trigger ? "true" : "";
      drawer?.classList.add("is-open");
      drawer?.setAttribute("aria-hidden", "false");
      backdrop?.classList.add("is-open");
      document.body.classList.add("no-scroll");
      one("input, select", kind === "member" ? memberForm : accountForm)?.focus();
    };

    all("[data-open-admin-drawer]").forEach((button) => {
      button.addEventListener("click", () => openAdminDrawer(button.dataset.openAdminDrawer, button));
    });
    one("[data-close-admin-drawer]")?.addEventListener("click", closeAdminOverlays);
    backdrop?.addEventListener("click", closeAdminOverlays);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !stopDialog?.open) closeAdminOverlays();
      const activeOverlay = drawer?.classList.contains("is-open")
        ? drawer
        : nav?.classList.contains("is-open")
          ? nav
          : null;
      if (event.key === "Tab" && activeOverlay) {
        const focusable = all(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary',
          activeOverlay,
        ).filter((item) => !item.closest("[hidden]"));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });

    const renderNewMember = (name) => {
      const mount = one("[data-new-member-row]");
      if (!mount) return;
      const row = document.createElement("div");
      row.className = "data-row";
      row.innerHTML =
        "<div><strong></strong><small>门店使用者</small></div><span>柯桥门店</span><div class=\"tag-line\"><span>创作空间</span><span>内容</span><span>陈列</span></div><span class=\"status status--waiting\">待激活</span><button class=\"text-button\" type=\"button\">查看</button>";
      one("strong", row).textContent = name;
      mount.replaceWith(row);
    };

    one("[data-member-form]")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const name = one('input[name="name"]', event.currentTarget)?.value.trim() || "新成员";
      renderNewMember(name);
      closeAdminOverlays();
      const success = one("[data-member-success]");
      if (success) {
        success.hidden = false;
        success.focus?.();
      }
    });

    one("[data-account-form]")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const name =
        one('input[name="account-name"]', event.currentTarget)?.value.trim() || "区域内容观察";
      const mount = one("[data-new-account-row]");
      if (mount) {
        const row = document.createElement("article");
        row.className = "account-record";
        row.innerHTML =
          "<div class=\"account-record__mark\">区</div><div><p class=\"eyebrow\">区域内容运营</p><h2></h2><p>从区域使用场景出发，在品牌边界内组织内容。</p></div><dl><div><dt>负责团队</dt><dd>浙江区域</dd></div><div><dt>使用者</dt><dd>许知夏</dd></div><div><dt>可用任务</dt><dd>内容生产</dd></div></dl><button class=\"text-button\" type=\"button\">查看账号</button>";
        one("h2", row).textContent = name;
        mount.replaceWith(row);
      }
      closeAdminOverlays();
      const success = one("[data-account-success]");
      if (success) success.hidden = false;
    });

    one("[data-activation-link]")?.addEventListener("click", () => {
      const result = one("[data-activation-result]");
      if (result) result.hidden = false;
    });

    one("[data-stop-member]")?.addEventListener("click", (event) => {
      adminReturnFocus = event.currentTarget;
      activePrimaryActions().forEach((item) => {
        item.dataset.overlayHidden = "true";
        item.hidden = true;
      });
      stopDialog?.showModal();
    });
    stopDialog?.addEventListener("close", () => {
      if (stopDialog.returnValue === "confirm") {
        setText("[data-chen-status]", "已停用");
        one("[data-chen-status]")?.classList.remove("status--waiting");
        one("[data-chen-status]")?.classList.add("status--quiet");
        setText("[data-member-access-status]", "已停用，不能进入");
        const result = one("[data-activation-result]");
        if (result) {
          result.textContent = "成员已停用，已有内容和账号关系仍然保留。";
          result.hidden = false;
        }
      }
      all("[data-admin-primary]").forEach((item) => {
        if (item.dataset.overlayHidden === "true") {
          item.hidden = false;
          delete item.dataset.overlayHidden;
        }
      });
      adminReturnFocus?.focus?.();
      adminReturnFocus = null;
    });

    const activateLibraryTab = (tab) => {
      const safeTab = ["brand", "products", "materials"].includes(tab) ? tab : "brand";
      all("[data-library-tab]").forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset.libraryTab === safeTab));
      });
      all("[data-library-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.libraryPanel !== safeTab;
      });
      replaceQuery({ view: "library", tab: safeTab });
    };
    if (view === "library") activateLibraryTab(query.get("tab") || "brand");
    all("[data-library-tab]").forEach((button) => {
      button.addEventListener("click", () => activateLibraryTab(button.dataset.libraryTab));
    });
    one("[data-library-add]")?.addEventListener("click", () => {
      activateLibraryTab("products");
      const waiting = one(".library-panel:not([hidden]) .status--waiting");
      waiting?.scrollIntoView({ block: "center" });
      waiting?.closest(".data-row")?.classList.add("is-attention");
      setText("[data-library-add]", "正在补春季针织");
    });
  }

  /* Unified creator */

  const creatorWork = one("[data-creator-work]");
  if (creatorWork) {
    const role = query.get("role") === "hq" ? "hq" : "store";
    let task = query.get("task") === "display" ? "display" : "content";
    let state = query.get("state") || "empty";
    let currentTarget = query.get("target") || "小红书图文";
    let materialSelected = query.get("material") === "selected";
    const canDisplay = role === "store";
    if (!canDisplay && task === "display") state = "no-capability";

    const identity = {
      hq: {
        account: "总部品牌内容运营",
        expression: "总部品牌表达",
        avatar: "总",
        series: "穿着关系练习",
        count: "第 4 篇",
      },
      store: {
        account: "柯桥门店人物",
        expression: "门店人物表达",
        avatar: "店",
        series: "留一点选择距离",
        count: "第 4 篇",
      },
    }[role];

    const contentVersions = {
      store: {
        v1: {
          summary:
            "从门店人物的位置回应独自浏览的需要，给出一种不急着靠近、也不会让人找不到的相处方式。",
          title: "有时候，合适的招呼是先留一点距离",
          opening:
            "如果有人走进店里，只想先自己看看，我更愿意先把选择的时间还给她。不是装作没看见，而是不急着把一段对话塞过去。",
          closing:
            "我会留在能被看到的位置。想问的时候可以叫我；还没想好，也能继续慢慢看。",
          shot: "手机固定，对着干净的墙；你走进画面，在一侧自然停下。",
          caption: "先留一点选择距离，也许更容易听见自己真正喜欢什么。#门店观察",
        },
        v2: {
          summary:
            "把开头收得更轻，从本人愿意怎样相处说起；受众能带走一种不打扰、也不失联的逛店节奏。",
          title: "想自己看一会儿，也不用急着回应",
          opening:
            "进店后想先自己看看，不需要马上进入一段对话。我会站在能被看见、又不会挡住衣服的位置。",
          closing:
            "想问的时候，一抬头就能找到我；还没想好，也可以继续慢慢看。逛衣服本来就能有一点自己的安静。",
          shot: "手机固定，对着干净的墙和半个挂杆；先留两秒空画面。",
          caption: "想自己看一会儿，也是一种舒服的逛店节奏。#门店日常 #慢慢看",
        },
      },
      hq: {
        v1: {
          summary:
            "从品牌对穿着关系的判断出发，让两件完整商品在同一平面里形成可见主次，而不是靠远近制造差异。",
          title: "两件衣服放在一起，先别急着分主次",
          opening:
            "把亮黄上装和深色外套放在同一平面、同一距离。先看两件完整轮廓，再决定谁居中、谁站在侧边。",
          closing:
            "等权、居中或侧边，是三种不同关系。合照不是颜色排队，主次也不只靠谁站得更近。",
          shot: "手机固定；两件衣服始终在同一平面，以等权并列开始。",
          caption: "同一距离，也能看见三种穿着关系。#穿着关系 #一衣多穿",
        },
        v2: {
          summary:
            "保留你想要的幽默，把吵闹玩梗收窄为一句克制的冷幽默；三张同平面画面让受众直接比较等权、居中与侧边。",
          title: "合照不是颜色排队",
          opening:
            "第一张，两件完整衣服同平面并列，谁也不抢话。第二张，亮黄居中，深色外套成为稳定背景。第三张，亮黄移到侧边，让深色轮廓先被看见。",
          closing:
            "距离没有变，配色关系变了。下一次搭配两件衣服，先试着改变主次，不必先把其中一件藏起来。",
          shot: "手机固定，连续拍三张静态画面；两件完整商品始终同平面、同距离。",
          caption: "合照不是颜色排队。等权、居中、侧边，试试同一组颜色的三种关系。#配色关系",
        },
      },
    };

    const displayVersions = {
      v1: {
        summary:
          "用现有 15 件商品完成两层墙面挂杆：先建立左、中、右关系，再按现场宽度调整数量和间距。",
        title: "先定主焦点，再让两侧有轻重回应",
        left: "米色针织侧挂，灰白下装在下杆回应",
        center: "砖红外套正挂，深蓝下装在下杆承接",
        right: "炭灰与白色上装侧挂，黑色下装收尾",
        spacing: "正挂主焦点两侧各留一手掌以上，侧挂按实际宽度减量。",
        stepOne: "先把砖红外套正挂在中间，确认第一眼焦点。",
        stepTwo: "再挂深蓝下装，让上下杆形成完整主推组。",
      },
      v2: {
        summary:
          "保留中间主焦点，把左侧数量减一、右侧间距拉开；执行人员只需要按新的文字次序调整。",
        title: "中间不动，先让两侧呼吸起来",
        left: "米色针织侧挂减为 3 件，灰白下装在下杆轻声回应",
        center: "砖红外套正挂，深蓝下装在下杆承接，保持主焦点",
        right: "炭灰与白色上装交替侧挂，黑色下装留出拿取距离",
        spacing: "中间正挂保持不动；左侧减一件，右侧每两件之间增加半掌距离。",
        stepOne: "先保留中间砖红外套与深蓝下装，不拆主推组。",
        stepTwo: "左侧取下一件米色针织，再把右侧相近颜色拉开半掌。",
      },
    };

    setText("[data-current-account]", identity.account);
    setText("[data-current-expression]", identity.expression);
    setText("[data-sidebar-account]", identity.account);
    setText("[data-sidebar-avatar]", identity.avatar);
    setText("[data-series-name]", identity.series);
    setText("[data-series-count]", identity.count);
    setText("[data-drawer-profile-title]", identity.expression);
    setText(
      "[data-drawer-profile-copy]",
      role === "hq"
        ? "从品牌当前判断、商品关系和较广受众出发，不代替具体门店叙述经历。"
        : "从门店日常、近场关系和本人观察出发，不代替总部发言。",
    );
    setText("[data-target-label]", task === "display" ? "文字参考方案" : currentTarget);
    document.title = `${identity.account} · 笛语`;

    all("[data-task-link]").forEach((link) => {
      const linkTask = link.dataset.taskLink;
      link.href = `creator.html?role=${role}&task=${linkTask}&state=empty`;
      link.classList.toggle("is-current", linkTask === task);
      if (linkTask === "display" && !canDisplay) link.hidden = true;
    });
    if (!canDisplay) {
      const switcher = one("[data-task-switch]");
      if (switcher) switcher.classList.add("is-single");
    }

    if (query.get("direction") === "open") {
      const direction = one("[data-direction-panel]");
      if (direction) direction.open = true;
    }
    const bodyOptin = one("[data-body-optin]");
    const bodyDirection = one("[data-body-direction]");
    if (bodyOptin && bodyDirection) {
      bodyOptin.checked = query.get("body") === "on";
      bodyDirection.hidden = !bodyOptin.checked;
      bodyOptin.addEventListener("change", () => {
        bodyDirection.hidden = !bodyOptin.checked;
        replaceQuery({ body: bodyOptin.checked ? "on" : null });
      });
    }

    const thread = one("[data-thread]");
    const form = one("[data-creator-form]");
    const recovery = one("[data-conversation-recovery]");
    const input = one("[data-creator-input]");
    const materialState = one("[data-material-state]");
    const directionPanel = one("[data-direction-panel]");
    const materialChoice = one(".material-choice");
    let returnState = "v2";

    const addMessage = (text, self = false) => {
      if (!thread) return;
      const message = document.createElement("div");
      message.className = `message${self ? " message--self" : " message--assistant"}`;
      message.textContent = text;
      thread.append(message);
    };

    const resetThread = () => {
      if (!thread) return;
      thread.replaceChildren();
      addMessage(
        task === "display"
          ? "把现有商品、挂杆和现场限制自然说出来。我会整理成能照着执行的文字方案。"
          : role === "hq"
            ? "先说一个品牌现在真正想讲清楚的判断。写一句就够。"
            : "先说一件今天真正想表达的事。写一句就够，其他部分我来整理。",
      );
    };

    const applyContentVersion = (version) => {
      const data = contentVersions[role][version];
      setText("[data-content-summary]", data.summary);
      setText("[data-content-title]", data.title);
      setText("[data-content-opening]", data.opening);
      setText("[data-content-closing]", data.closing);
      setText("[data-content-shot]", data.shot);
      setText("[data-content-caption]", data.caption);
    };

    const applyDisplayVersion = (version) => {
      const data = displayVersions[version];
      setText("[data-display-summary]", data.summary);
      setText("[data-display-title]", data.title);
      setText('[data-plan-row="left"] span', data.left);
      setText('[data-plan-row="center"] span', data.center);
      setText('[data-plan-row="right"] span', data.right);
      setText("[data-display-spacing]", data.spacing);
      setText('[data-display-step="one"]', data.stepOne);
      setText('[data-display-step="two"]', data.stepTwo);
      const leftCount = one('[data-plan-row="left"] span:nth-child(3)');
      if (leftCount) leftCount.textContent = version === "v2" ? "3 件" : "4 件";
      const rightCount = one('[data-plan-row="right"] span:nth-child(3)');
      if (rightCount) rightCount.textContent = version === "v2" ? "7 件" : "6 件";
    };

    const showArtifact = (name) => {
      all("[data-artifact-state]").forEach((section) => {
        section.hidden = section.dataset.artifactState !== name;
      });
    };

    const switchMobile = (view) => {
      creatorWork.dataset.mobileView = view;
      all("[data-mobile-work]").forEach((button) => {
        button.setAttribute("aria-selected", String(button.dataset.mobileWork === view));
      });
    };

    const render = (nextState, updateUrl = true) => {
      state = nextState;
      if (updateUrl) replaceQuery({ role, task, state });
      resetThread();
      if (form) form.hidden = false;
      if (recovery) recovery.hidden = true;
      if (input) input.value = "";
      all("[data-history-return]").forEach((button) => {
        button.hidden = true;
      });
      setText("[data-artifact-meta]", identity.account);
      setText("[data-conversation-status]", identity.count);
      setText("[data-conversation-eyebrow]", task === "display" ? "陈列搭配" : "接着这个系列");
      setText(
        "[data-conversation-title]",
        task === "display" ? "先把库存和现场说清楚。" : "从一句真实观察开始。",
      );

      if (directionPanel) directionPanel.hidden = task === "display";
      if (materialChoice) materialChoice.hidden = task === "display";
      if (input) {
        input.placeholder =
          task === "display"
            ? "例如：两层挂杆，现有 15 件，上杆想留一个主焦点，右侧拿取空间比较窄……"
            : state === "v1" || state === "v2"
              ? "例如：判断保留，开头再轻一点……"
              : "例如：有人进店后只想自己看看，我想先给她一点空间……";
      }
      setText(
        "[data-composer-help]",
        task === "display"
          ? "商品、数量、挂杆和限制一次说清即可。"
          : state === "v1" || state === "v2"
            ? "直接说想改什么，旧版本会保留。"
            : "自然说出想法即可。",
      );
      setText(
        "[data-creator-submit]",
        state === "v1" || state === "v2" ? "形成新版本" : task === "display" ? "生成参考方案" : "生成成品",
      );

      if (nextState === "empty" || nextState === "no-history") {
        showArtifact("empty");
        setText("[data-version-label]", "等待成品");
        setText(
          "[data-empty-copy]",
          task === "display"
            ? "先在左侧说清现有商品与现场限制；完整文字方案会在这里出现。"
            : "先在左侧说一句真实想法；创作方向和素材都可以不选。",
        );
        const noHistory = nextState === "no-history";
        const history = one("[data-sidebar-history]");
        const empty = one("[data-sidebar-empty]");
        if (history) history.hidden = noHistory;
        if (empty) empty.hidden = !noHistory;
        return;
      }

      const sidebarHistory = one("[data-sidebar-history]");
      const sidebarEmpty = one("[data-sidebar-empty]");
      if (sidebarHistory) sidebarHistory.hidden = false;
      if (sidebarEmpty) sidebarEmpty.hidden = true;

      if (nextState === "loading") {
        showArtifact("loading");
        setText("[data-version-label]", "正在整理");
        if (form) form.hidden = true;
        return;
      }

      if (nextState === "clarify") {
        showArtifact("clarify");
        setText("[data-version-label]", "需要补一句");
        if (form) form.hidden = true;
        return;
      }

      if (nextState === "error") {
        showArtifact("empty");
        setText("[data-version-label]", "这次没有完成");
        if (form) form.hidden = true;
        if (recovery) recovery.hidden = false;
        return;
      }

      if (nextState === "no-capability") {
        showArtifact("no-capability");
        setText("[data-version-label]", "当前账号");
        if (form) form.hidden = true;
        return;
      }

      const historical = nextState === "history";
      const version = historical || nextState === "v1" ? "v1" : "v2";
      returnState = nextState === "v1" ? "v1" : "v2";
      if (task === "content") {
        showArtifact("content");
        applyContentVersion(version);
      } else {
        showArtifact("display");
        applyDisplayVersion(version);
      }

      if (historical) {
        setText("[data-version-label]", "历史版本 · V1");
        if (form) form.hidden = true;
        all("[data-history-return]").forEach((button) => {
          if (!button.closest("[data-artifact-state]")?.hidden) button.hidden = false;
        });
        addMessage("你正在回读修改前的完整版本。");
      } else {
        setText("[data-version-label]", `当前版本 · ${version.toUpperCase()}`);
        addMessage(
          task === "display"
            ? "请用这批商品和两层挂杆，整理一份可以照着做的文字方案。"
            : role === "hq"
              ? "两件衣服放在一起，怎样让人看见真正不同的穿着关系？"
              : "有人进店后只想自己看看，这种沉默也应该被尊重。",
          true,
        );
        addMessage(
          nextState === "v2"
            ? "新版本已经整理好。旧版本仍在历史里，可以随时完整回读。"
            : "第一版已经整理成完整结果。想改哪里，继续像和同事说话一样告诉我。",
        );
      }

      const historyCount = nextState === "v2" || historical ? 1 : 0;
      all("[data-history-summary]").forEach((summary) => {
        summary.textContent = `历史版本（${historyCount}）`;
      });
      all("[data-content-history], [data-display-history]").forEach((block) => {
        block.hidden = historyCount === 0;
      });
      if (window.innerWidth <= 800 && !historical) switchMobile("artifact");
    };

    resetThread();
    if (materialState) {
      materialState.textContent = materialSelected ? "已选择：春季商品静物（2）" : "未选择";
    }

    one("[data-material-toggle]")?.addEventListener("click", () => {
      materialSelected = !materialSelected;
      if (materialState) {
        materialState.textContent = materialSelected ? "已选择：春季商品静物（2）" : "未选择";
      }
      replaceQuery({ material: materialSelected ? "selected" : null });
    });

    form?.addEventListener("submit", (event) => {
      event.preventDefault();
      const value = input?.value.trim() || "";
      if (!value) {
        input?.focus();
        return;
      }
      addMessage(value, true);
      const revision = state === "v1" || state === "v2";
      render("loading");
      window.setTimeout(() => render(revision ? "v2" : "v1"), 620);
    });

    all("[data-clarify-choice]").forEach((button) => {
      button.addEventListener("click", () => {
        addMessage(
          button.dataset.clarifyChoice === "personal"
            ? "只表达我现在的理解，不写成门店已经在做。"
            : "这是门店已经明确提供的做法。",
          true,
        );
        render("loading");
        window.setTimeout(() => render("v1"), 620);
      });
    });

    one("[data-retry]")?.addEventListener("click", () => {
      render("loading");
      window.setTimeout(() => render("v1"), 620);
    });

    all("[data-history-open]").forEach((button) => {
      button.addEventListener("click", () => render("history"));
    });
    all("[data-history-return]").forEach((button) => {
      button.addEventListener("click", () => render(returnState === "v1" ? "v1" : "v2"));
    });

    all("[data-mobile-work]").forEach((button) => {
      button.addEventListener("click", () => switchMobile(button.dataset.mobileWork));
    });

    const actionResult = (button, message) => {
      const artifact = button.closest("[data-artifact-state]");
      const result = one("[data-artifact-action-result]", artifact);
      if (result) {
        result.textContent = message;
        result.hidden = false;
      }
    };
    all("[data-copy]").forEach((button) => {
      button.addEventListener("click", () =>
        actionResult(button, task === "display" ? "当前文字方案已复制。" : "当前完整成品已复制。"),
      );
    });
    all("[data-export]").forEach((button) => {
      button.addEventListener("click", () => actionResult(button, "当前版本的导出文件已经准备好。"));
    });
    one("[data-series-add]")?.addEventListener("click", (event) => {
      setText("[data-series-count]", "第 5 篇");
      actionResult(event.currentTarget, `已加入“${identity.series}”，下一篇会从这里继续。`);
    });

    const sidebar = one("[data-creator-sidebar]");
    const backdrop = one("[data-creator-backdrop]");
    const accountDrawer = one("[data-account-drawer]");
    const targetDrawer = one("[data-target-drawer]");
    const primary = one("[data-creator-submit]");
    let creatorReturnFocus = null;

    const closeCreatorOverlays = () => {
      sidebar?.classList.remove("is-open");
      accountDrawer?.classList.remove("is-open");
      targetDrawer?.classList.remove("is-open");
      accountDrawer?.setAttribute("aria-hidden", "true");
      targetDrawer?.setAttribute("aria-hidden", "true");
      backdrop?.classList.remove("is-open");
      document.body.classList.remove("no-scroll");
      if (primary?.dataset.overlayHidden === "true") {
        primary.hidden = false;
        delete primary.dataset.overlayHidden;
      }
      creatorReturnFocus?.focus?.();
      creatorReturnFocus = null;
    };

    const openCreatorDrawer = (drawer, trigger) => {
      closeCreatorOverlays();
      creatorReturnFocus = trigger;
      if (primary && !primary.hidden) {
        primary.dataset.overlayHidden = "true";
        primary.hidden = true;
      }
      drawer?.classList.add("is-open");
      drawer?.setAttribute("aria-hidden", "false");
      backdrop?.classList.add("is-open");
      document.body.classList.add("no-scroll");
      one("a, button", drawer)?.focus();
    };

    all("[data-account-drawer-open]").forEach((button) => {
      button.addEventListener("click", () => openCreatorDrawer(accountDrawer, button));
    });
    one("[data-target-drawer-open]")?.addEventListener("click", (event) =>
      openCreatorDrawer(targetDrawer, event.currentTarget),
    );
    all("[data-creator-drawer-close]").forEach((button) => {
      button.addEventListener("click", closeCreatorOverlays);
    });
    backdrop?.addEventListener("click", closeCreatorOverlays);
    one("[data-creator-menu]")?.addEventListener("click", () => {
      closeCreatorOverlays();
      creatorReturnFocus = one("[data-creator-menu]");
      sidebar?.classList.add("is-open");
      backdrop?.classList.add("is-open");
      document.body.classList.add("no-scroll");
      one("a", sidebar)?.focus();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeCreatorOverlays();
      const activeOverlay = accountDrawer?.classList.contains("is-open")
        ? accountDrawer
        : targetDrawer?.classList.contains("is-open")
          ? targetDrawer
          : sidebar?.classList.contains("is-open")
            ? sidebar
            : null;
      if (event.key === "Tab" && activeOverlay) {
        const focusable = all(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary',
          activeOverlay,
        ).filter((item) => !item.closest("[hidden]"));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });

    all("[data-target-choice]").forEach((button) => {
      button.addEventListener("click", () => {
        currentTarget = button.dataset.targetChoice || "小红书图文";
        setText("[data-target-label]", currentTarget);
        replaceQuery({ target: currentTarget });
        closeCreatorOverlays();
        one("[data-target-drawer-open]")?.focus();
      });
    });

    one("[data-collab-edit]")?.addEventListener("click", (event) => {
      const collaborationForm = one("[data-collab-form]");
      if (!collaborationForm) return;
      collaborationForm.hidden = false;
      event.currentTarget.hidden = true;
      one("textarea", collaborationForm)?.focus();
    });
    one("[data-collab-form]")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const value = one("textarea", event.currentTarget)?.value.trim();
      if (value) setText("[data-collab-summary]", value);
      event.currentTarget.hidden = true;
      const result = one("[data-collab-result]");
      if (result) result.hidden = false;
      const edit = one("[data-collab-edit]");
      if (edit) {
        edit.textContent = "再次调整";
        edit.hidden = false;
      }
    });

    render(state, false);
  }

  /* Ops */

  const feedbackEditor = one("[data-feedback-editor]");
  if (feedbackEditor) {
    let selectedDemand = one("[data-demand-item].is-active");
    const nextButton = one("[data-ops-next]");
    const success = one("[data-feedback-success]");

    const openDemand = (item) => {
      if (!item) return;
      selectedDemand = item;
      all("[data-demand-item]").forEach((candidate) => {
        candidate.classList.toggle("is-active", candidate === item);
      });
      setText("[data-feedback-title]", item.dataset.demandTitle || "需求反馈");
      feedbackEditor.hidden = false;
      if (success) success.hidden = true;
      if (nextButton) nextButton.hidden = true;
      one("select", feedbackEditor)?.focus();
    };

    nextButton?.addEventListener("click", () => {
      openDemand(all("[data-demand-item]").find((item) => !item.hidden));
    });
    all("[data-demand-item]").forEach((item) => {
      item.addEventListener("click", () => openDemand(item));
    });
    one("[data-feedback-complete]")?.addEventListener("click", () => {
      if (selectedDemand) selectedDemand.hidden = true;
      feedbackEditor.hidden = true;
      if (success) success.hidden = false;
      const remaining = all("[data-demand-item]").filter((item) => !item.hidden);
      setText("[data-open-demand-count]", String(remaining.length));
      setText("[data-ops-title]", remaining.length ? `还有 ${remaining.length} 件事需要处理。` : "今天的待处理已经清空。");
    });
    one("[data-feedback-next]")?.addEventListener("click", () => {
      openDemand(all("[data-demand-item]").find((item) => !item.hidden));
    });

    all("[data-tenant-detail]").forEach((button) => {
      button.addEventListener("click", () => {
        const panel = one("[data-tenant-detail-panel]");
        if (panel) panel.hidden = false;
      });
    });
    one("[data-close-tenant-detail]")?.addEventListener("click", () => {
      const panel = one("[data-tenant-detail-panel]");
      if (panel) panel.hidden = true;
    });
    one("[data-tenant-search]")?.addEventListener("input", (event) => {
      const needle = event.currentTarget.value.trim().toLowerCase();
      all("[data-tenant-row]").forEach((row) => {
        row.hidden = Boolean(needle) && !row.textContent.toLowerCase().includes(needle);
      });
    });
  }
})();
