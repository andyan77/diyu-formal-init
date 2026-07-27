(() => {
  "use strict";

  const one = (selector, root = document) => root.querySelector(selector);
  const all = (selector, root = document) => [...root.querySelectorAll(selector)];

  const adminPages = [
    ["overview", "概览", "admin-overview.html"],
    ["usage", "团队使用", "team-usage.html"],
    ["members", "成员与权限", "members.html"],
    ["accounts", "发布账号", "publishing-account.html"],
    ["library", "品牌资料库", "brand-library.html"],
    ["readiness", "当前可用与待补", "readiness.html"],
  ];

  const accountSpecs = {
    hq: {
      name: "总部品牌内容运营",
      profile: "从总部岗位表达品牌当前立场",
      targets: {
        douyin: ["video"],
        xiaohongshu: ["graphic", "video"],
        wechat_channels: ["video"],
      },
    },
    store: {
      name: "柯桥门店人物",
      profile: "从门店日常与本人观察出发",
      targets: {
        xiaohongshu: ["graphic", "video"],
        wechat_channels: ["video"],
      },
    },
  };

  const platformLabels = {
    douyin: "抖音",
    xiaohongshu: "小红书",
    wechat_channels: "微信视频号",
  };
  const formatLabels = { video: "视频", graphic: "图文" };

  const mountAdminRail = () => {
    const rail = one("[data-admin-rail]");
    if (!rail) return;
    const current = document.body.dataset.page || "";
    rail.innerHTML = `
      <header>
        <img class="brand-symbol" src="../../../../assets/brand/diyu-vi/svg/diyu-symbol.svg" alt="笛语" />
        <div><strong>品牌管理</strong><span>笛语服饰</span></div>
      </header>
      <nav class="admin-nav" aria-label="品牌管理导航">
        ${adminPages
          .map(
            ([id, label, href]) =>
              `<a href="${href}" class="${current === id ? "active" : ""}" ${
                current === id ? 'aria-current="page"' : ""
              }>${label}</a>`
          )
          .join("")}
      </nav>
      <footer><strong>林岚</strong><span>品牌管理员 · 演示资料</span></footer>
    `;
  };

  const setNotice = (message) => {
    const notice = one("[data-page-notice]");
    if (!notice) return;
    notice.textContent = message;
    notice.hidden = false;
    window.setTimeout(() => {
      notice.hidden = true;
    }, 2600);
  };

  const openDrawer = (id) => {
    const layer = one(`[data-drawer="${id}"]`);
    if (!layer) return;
    layer.hidden = false;
    document.body.classList.add("locked");
    one("button, input, select, textarea", layer)?.focus();
  };

  const closeDrawer = (layer) => {
    layer.hidden = true;
    document.body.classList.remove("locked");
  };

  const initDrawers = () => {
    all("[data-open-drawer]").forEach((trigger) => {
      trigger.addEventListener("click", () => openDrawer(trigger.dataset.openDrawer));
    });
    all("[data-drawer]").forEach((layer) => {
      all("[data-close-drawer]", layer).forEach((trigger) => {
        trigger.addEventListener("click", () => closeDrawer(layer));
      });
      layer.addEventListener("mousedown", (event) => {
        if (event.target === layer) closeDrawer(layer);
      });
      layer.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeDrawer(layer);
      });
    });
    if (new URLSearchParams(window.location.search).get("import") === "open") {
      openDrawer("import");
    }
  };

  const initRange = () => {
    all("[data-range]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        const range = trigger.dataset.range;
        all("[data-range]").forEach((candidate) =>
          candidate.classList.toggle("active", candidate === trigger)
        );
        all("[data-range-value]").forEach((node) => {
          const value = node.dataset[range === "30" ? "value30" : "value7"];
          if (value !== undefined) node.textContent = value;
        });
        all("[data-range-width]").forEach((node) => {
          const width = node.dataset[range === "30" ? "width30" : "width7"];
          if (width) node.style.width = width;
        });
        const label = one("[data-range-label]");
        if (label) label.textContent = range === "30" ? "近30日" : "近7日";
      });
    });
  };

  const initMemberFilters = () => {
    all("[data-member-filter]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        const filter = trigger.dataset.memberFilter;
        all("[data-member-filter]").forEach((candidate) =>
          candidate.classList.toggle("active", candidate === trigger)
        );
        all("[data-member-status]").forEach((row) => {
          row.hidden = filter !== "all" && row.dataset.memberStatus !== filter;
        });
      });
    });
  };

  const initEntryType = () => {
    const choices = all("[data-entry-type]");
    if (!choices.length) return;
    const userBlock = one("[data-entry-user]");
    const adminBlock = one("[data-entry-admin]");
    const sync = () => {
      const isAdmin = one('[data-entry-type][value="tenant-admin"]')?.checked;
      userBlock.hidden = isAdmin;
      adminBlock.hidden = !isAdmin;
      all("input, select", userBlock).forEach((control) => {
        control.disabled = isAdmin;
      });
      document.body.dataset.memberEntryType = isAdmin ? "tenant-admin" : "tenant-user";
    };
    choices.forEach((choice) => choice.addEventListener("change", sync));
    sync();
  };

  const refreshLibraryEmpty = () => {
    const panel = one('[data-tab-panel-group="library"]:not([hidden])');
    const empty = one("[data-scope-empty]");
    if (!panel || !empty) return;
    empty.hidden = all("[data-library-row]", panel).some((row) => !row.hidden);
  };

  const initTabs = () => {
    all("[data-tab-group]").forEach((group) => {
      const name = group.dataset.tabGroup;
      const choose = (value) => {
        all(`[data-tab-group="${name}"] [data-tab]`).forEach((trigger) => {
          const selected = trigger.dataset.tab === value;
          trigger.classList.toggle("active", selected);
          trigger.setAttribute("aria-selected", String(selected));
        });
        all(`[data-tab-panel-group="${name}"]`).forEach((panel) => {
          panel.hidden = panel.dataset.tabPanel !== value;
        });
        refreshLibraryEmpty();
      };
      all("[data-tab]", group).forEach((trigger) => {
        trigger.addEventListener("click", () => choose(trigger.dataset.tab));
      });
    });
  };

  const initLibraryScopes = () => {
    const filters = all("[data-scope-filter]");
    if (!filters.length) return;
    const apply = (scope) => {
      filters.forEach((button) => {
        button.classList.toggle("active", button.dataset.scopeFilter === scope);
      });
      all("[data-library-row]").forEach((row) => {
        row.hidden = scope !== "all" && row.dataset.libraryScope !== scope;
      });
      refreshLibraryEmpty();
    };
    filters.forEach((button) => {
      button.addEventListener("click", () => apply(button.dataset.scopeFilter));
    });
    apply("all");
  };

  const importScopeLabel = (scope, region) => {
    if (scope === "hq") return "总部专用";
    if (scope === "region") return `${region}可用`;
    return "品牌全员";
  };

  const initImportFlow = () => {
    const drawer = one('[data-drawer="import"]');
    if (!drawer) return;
    let step = 1;
    const button = one("[data-import-next]", drawer);
    const back = one("[data-import-back]", drawer);
    const scope = one("[data-scope-select]", drawer);
    const regionField = one("[data-region-field]", drawer);
    const region = one("[data-region-select]", drawer);
    const regionError = one("[data-region-error]", drawer);

    const syncScope = () => {
      const needsRegion = scope.value === "region";
      regionField.hidden = !needsRegion;
      region.disabled = !needsRegion;
      region.required = needsRegion;
      if (!needsRegion) regionError.hidden = true;
    };

    const render = () => {
      all("[data-import-step]", drawer).forEach((panel) => {
        panel.hidden = Number(panel.dataset.importStep) !== step;
      });
      all("[data-step]", drawer).forEach((item) => {
        item.classList.toggle("active", Number(item.dataset.step) <= step);
      });
      back.hidden = step === 1 || step === 4;
      button.textContent =
        step === 1 ? "预览字段" : step === 2 ? "设置可用范围" : step === 3 ? "保存这批资料" : "完成";
    };

    scope.addEventListener("change", syncScope);
    region.addEventListener("change", () => {
      regionError.hidden = Boolean(region.value);
    });
    button.addEventListener("click", () => {
      if (step === 3 && scope.value === "region" && !region.value) {
        regionError.hidden = false;
        region.focus();
        return;
      }
      if (step < 4) {
        if (step === 3) {
          one("[data-import-scope-summary]", drawer).textContent = importScopeLabel(
            scope.value,
            region.value
          );
        }
        step += 1;
        render();
      } else {
        const label = importScopeLabel(scope.value, region.value);
        closeDrawer(drawer);
        setNotice(`2 条商品资料已保存为第 1 版；谁可用：${label}。`);
        step = 1;
        render();
      }
    });
    back.addEventListener("click", () => {
      step = Math.max(1, step - 1);
      render();
    });
    syncScope();
    render();
  };

  const initAdminAccounts = () => {
    const switches = all("[data-admin-account]");
    if (!switches.length) return;
    const show = (account) => {
      switches.forEach((button) => {
        button.classList.toggle("active", button.dataset.adminAccount === account);
      });
      all("[data-account-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.accountPanel !== account;
      });
    };
    switches.forEach((button) => {
      button.addEventListener("click", () => show(button.dataset.adminAccount));
    });
    show("hq");
  };

  const platformName = (value) => platformLabels[value] || "抖音";
  const formatName = (value) => formatLabels[value] || "视频";

  const syncTargetLabels = (account, platform, format) => {
    const spec = accountSpecs[account] || accountSpecs.hq;
    all("[data-identity-label]").forEach((node) => {
      node.textContent = spec.name;
    });
    all("[data-profile-summary]").forEach((node) => {
      node.textContent = spec.profile;
    });
    all("[data-profile-summary-inline]").forEach((node) => {
      node.textContent = spec.profile;
    });
    all("[data-platform-label]").forEach((node) => {
      node.textContent = platformName(platform);
    });
    all("[data-format-label]").forEach((node) => {
      node.textContent = formatName(format);
    });
    all("[data-only-format]").forEach((node) => {
      node.hidden = node.dataset.onlyFormat !== format;
    });
    document.body.dataset.contentTarget = `${account}:${platform}:${format}`;
  };

  let currentCreatorTarget = {
    account: "hq",
    platform: "douyin",
    format: "video",
  };

  const initCreatorTarget = () => {
    const identity = one("[data-identity-select]");
    const platform = one("[data-platform-select]");
    const format = one("[data-format-select]");
    if (!identity || !platform || !format) return;
    const params = new URLSearchParams(window.location.search);

    const fillFormats = (preferred = "") => {
      const formats = accountSpecs[identity.value].targets[platform.value] || ["video"];
      format.innerHTML = formats
        .map((value) => `<option value="${value}">${formatName(value)}</option>`)
        .join("");
      format.value = formats.includes(preferred) ? preferred : formats[0];
    };

    const fillPlatforms = (preferredPlatform = "", preferredFormat = "") => {
      const targets = accountSpecs[identity.value].targets;
      platform.innerHTML = Object.keys(targets)
        .map((value) => `<option value="${value}">${platformName(value)}</option>`)
        .join("");
      platform.value = Object.hasOwn(targets, preferredPlatform)
        ? preferredPlatform
        : Object.keys(targets)[0];
      fillFormats(preferredFormat);
    };

    const sync = () => {
      currentCreatorTarget = {
        account: identity.value,
        platform: platform.value,
        format: format.value,
      };
      syncTargetLabels(identity.value, platform.value, format.value);
    };

    const requestedAccount = Object.hasOwn(accountSpecs, params.get("account"))
      ? params.get("account")
      : "hq";
    identity.value = requestedAccount;
    fillPlatforms(params.get("platform") || "", params.get("format") || "");
    sync();

    identity.addEventListener("change", () => {
      fillPlatforms();
      sync();
    });
    platform.addEventListener("change", () => {
      fillFormats();
      sync();
    });
    format.addEventListener("change", sync);
  };

  const initMobileTabs = () => {
    all("[data-mobile-tab]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        document.body.dataset.mobileView = trigger.dataset.mobileTab;
        all("[data-mobile-tab]").forEach((candidate) =>
          candidate.classList.toggle("active", candidate === trigger)
        );
      });
    });
  };

  const detectExplicitTargetMention = (text) => {
    let platform = "";
    let format = "";
    if (text.includes("小红书")) platform = "xiaohongshu";
    else if (text.includes("视频号")) platform = "wechat_channels";
    else if (text.includes("抖音")) platform = "douyin";
    if (/(图文|多图|图片合集)/.test(text)) format = "graphic";
    else if (/(视频|口播|短片)/.test(text)) format = "video";
    if (format === "graphic" && !platform) platform = "xiaohongshu";
    if (platform && platform !== "xiaohongshu") format = "video";
    return { platform, format };
  };

  const selectedDirections = () => {
    const names = {
      topic: "题材",
      approach: "讲法",
      style: "风格",
      format: "形式",
      continuity: "系列与互动",
    };
    const values = all("[data-axis]").flatMap((axis) => {
      const selected = one("[data-axis-choice].selected", axis);
      const search = one("[data-axis-search]", axis);
      const value = selected?.textContent.trim() || search?.value.trim() || "";
      return value ? [`${names[axis.dataset.axis]}：${value}`] : [];
    });
    const custom = one("[data-axis-custom]")?.value.trim();
    if (custom) values.push(`自定义：${custom}`);
    return values;
  };

  const updateDirectionSummary = () => {
    const values = selectedDirections();
    const summary = one("[data-direction-summary]");
    if (summary) summary.textContent = values.length ? `本次方向：${values.join(" · ")}` : "本次方向：未选择";
  };

  const initDirections = () => {
    const toggle = one("[data-direction-toggle]");
    const panel = one("[data-direction-panel]");
    toggle?.addEventListener("click", () => {
      const open = panel.hidden;
      panel.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
    });
    all("[data-axis]").forEach((axis) => {
      all("[data-axis-choice]", axis).forEach((button) => {
        button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", () => {
          const selecting = !button.classList.contains("selected");
          all("[data-axis-choice]", axis).forEach((candidate) => {
            candidate.classList.remove("selected");
            candidate.setAttribute("aria-pressed", "false");
          });
          if (selecting) {
            button.classList.add("selected");
            button.setAttribute("aria-pressed", "true");
          }
          updateDirectionSummary();
        });
      });
      one("[data-axis-more]", axis)?.addEventListener("click", (event) => {
        const search = one("[data-axis-search]", axis);
        search.hidden = !search.hidden;
        event.currentTarget.setAttribute("aria-expanded", String(!search.hidden));
        if (!search.hidden) search.focus();
      });
      one("[data-axis-search]", axis)?.addEventListener("input", updateDirectionSummary);
    });
    one("[data-axis-custom]")?.addEventListener("input", updateDirectionSummary);
    updateDirectionSummary();
  };

  const creatorDestination = () => {
    const params = new URLSearchParams({
      account: currentCreatorTarget.account,
      platform: currentCreatorTarget.platform,
      format: currentCreatorTarget.format,
    });
    const directions = selectedDirections();
    if (directions.length) params.set("directions", directions.join(" · "));
    return `creator-generating.html?${params.toString()}`;
  };

  const appendMessage = (role, text) => {
    const list = one("[data-message-list]");
    if (!list) return;
    const article = document.createElement("article");
    article.className = `message ${role === "user" ? "user" : "assistant"}`;
    article.dataset.messageRole = role;
    const label = document.createElement("span");
    label.textContent = role === "user" ? "你" : "笛语";
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    article.append(label, paragraph);
    list.append(article);
  };

  const initConversationFlow = () => {
    const submit = one("[data-conversation-submit]");
    const input = one("[data-creator-input]");
    if (!submit || !input) return;
    const conflict = one("[data-target-conflict]");
    const hint = one("[data-flow-hint]");
    let step = 0;
    let ignoreConflictOnce = false;

    const showConflict = (named) => {
      one("[data-conflict-current]", conflict).textContent = `${platformName(
        currentCreatorTarget.platform
      )} · ${formatName(currentCreatorTarget.format)}`;
      one("[data-conflict-named]", conflict).textContent = `${platformName(
        named.platform || currentCreatorTarget.platform
      )}${named.format ? ` · ${formatName(named.format)}` : ""}`;
      conflict.dataset.namedPlatform = named.platform;
      conflict.dataset.namedFormat = named.format;
      const switchButton = one("[data-conflict-switch]", conflict);
      const allowed =
        !named.platform ||
        Object.hasOwn(accountSpecs[currentCreatorTarget.account].targets, named.platform);
      switchButton.disabled = !allowed;
      switchButton.textContent = allowed ? "切换页面选择" : "当前账号没有这个平台";
      conflict.hidden = false;
      conflict.scrollIntoView({ block: "nearest" });
    };

    submit.addEventListener("click", () => {
      const text = input.value.trim();
      if (!text) {
        setNotice("先说一句你现在想到的话。");
        input.focus();
        return;
      }
      const named = detectExplicitTargetMention(text);
      const platformConflict =
        named.platform && named.platform !== currentCreatorTarget.platform;
      const formatConflict = named.format && named.format !== currentCreatorTarget.format;
      if (!ignoreConflictOnce && conflict && (platformConflict || formatConflict)) {
        showConflict(named);
        return;
      }
      ignoreConflictOnce = false;
      conflict.hidden = true;
      one("[data-creator-welcome]")?.remove();
      appendMessage("user", text);

      if (step === 0) {
        appendMessage("assistant", "没关系，可以先说最近发生的一件小事，或者一个一直没想明白的感觉。");
        document.body.dataset.conversationStage = "chat";
        input.value = "最近店里总有人只想自己看看。";
        hint.textContent = "先说观察；不会生成半成品";
        step = 1;
        input.focus();
        return;
      }

      if (step === 1) {
        appendMessage(
          "assistant",
          "这个观察可以做成门店人物内容。你更想讲“沉默也应该被尊重”，还是讨论“店员什么时候适合主动介绍”？"
        );
        document.body.dataset.conversationStage = "clarifying";
        input.value = "讲前一个，别像品牌宣言，要像店员自己的感受。";
        hint.textContent = "只补最有价值的一点";
        step = 2;
        input.focus();
        return;
      }

      appendMessage(
        "assistant",
        `好，我按当前选择的${platformName(currentCreatorTarget.platform)}${formatName(
          currentCreatorTarget.format
        )}整理。`
      );
      document.body.dataset.conversationStage = "generating";
      input.disabled = true;
      submit.disabled = true;
      hint.textContent = "要求已经足够，正在直接整理";
      window.setTimeout(() => {
        window.location.href = creatorDestination();
      }, 650);
    });

    one("[data-conflict-keep]")?.addEventListener("click", () => {
      conflict.hidden = true;
      ignoreConflictOnce = true;
      input.focus();
    });
    one("[data-conflict-switch]")?.addEventListener("click", () => {
      const identity = one("[data-identity-select]");
      const platform = one("[data-platform-select]");
      const format = one("[data-format-select]");
      const nextPlatform = conflict.dataset.namedPlatform;
      const nextFormat = conflict.dataset.namedFormat;
      if (nextPlatform && Object.hasOwn(accountSpecs[identity.value].targets, nextPlatform)) {
        platform.value = nextPlatform;
        platform.dispatchEvent(new Event("change"));
      }
      if (nextFormat && [...format.options].some((option) => option.value === nextFormat)) {
        format.value = nextFormat;
        format.dispatchEvent(new Event("change"));
      }
      conflict.hidden = true;
      input.focus();
    });
  };

  const initRelationshipFlow = () => {
    const submit = one("[data-relationship-submit]");
    const input = one("[data-relationship-input]");
    submit?.addEventListener("click", () => {
      if (!input.value.trim()) {
        setNotice("先补充当前由谁表达，或者想怎样展开。");
        return;
      }
      appendMessage("user", input.value.trim());
      const result = one("[data-relationship-result]");
      result.hidden = false;
      one("[data-message-list]").append(result);
      input.value = "";
      setNotice("人物关系和本次边界仍按原话保留。");
    });
  };

  const initStableActions = () => {
    one("[data-member-create]")?.addEventListener("click", () => {
      const isAdmin = document.body.dataset.memberEntryType === "tenant-admin";
      one("[data-member-success-title]").textContent = isAdmin
        ? "租户管理员体验链接已生成"
        : "租户用户体验链接已生成";
      one("[data-member-success-copy]").textContent = isAdmin
        ? "顾晨将只从品牌管理入口进入，不会获得内容创作或陈列搭配资格。链接在 24 小时内仅能使用一次。"
        : "顾晨将从租户用户入口进入。链接在 24 小时内仅能使用一次；这里不显示链接正文。";
      one("[data-member-form]").hidden = true;
      one("[data-member-form-actions]").hidden = true;
      one("[data-member-success]").hidden = false;
    });

    all("[data-profile-save]").forEach((button) => {
      button.addEventListener("click", () => {
        const account = button.dataset.profileSave;
        const version = one(`[data-profile-version="${account}"]`);
        version.textContent = account === "hq" ? "V3" : "V2";
        closeDrawer(button.closest("[data-drawer]"));
        setNotice("账号画像已保存为新版本；已有内容仍保留原版本。");
      });
    });

    one("[data-material-save]")?.addEventListener("click", (event) => {
      const drawer = event.currentTarget.closest("[data-drawer]");
      const count = all('input[type="checkbox"]:checked', drawer).length;
      one("[data-material-summary]").textContent = count ? `已选择 ${count} 项素材` : "未选择素材";
      closeDrawer(drawer);
      setNotice(count ? `本次将参考 ${count} 项素材。` : "本次不参考素材。");
    });

    one("[data-series-save]")?.addEventListener("click", (event) => {
      const drawer = event.currentTarget.closest("[data-drawer]");
      const selected = one('input[name="series"]:checked', drawer);
      one("[data-series-summary]").textContent = selected?.value || "单篇创作";
      closeDrawer(drawer);
      setNotice(selected?.value === "单篇创作" ? "这次按单篇创作。" : `已加入“${selected?.value}”。`);
    });

    one("[data-recovery-action='continue']")?.addEventListener("click", () => {
      one("[data-failure-input]")?.focus();
      setNotice("原来的交流仍在，可以直接继续补充。");
    });
  };

  const initGenerationSummary = () => {
    const directions = one("[data-directions-used]");
    if (!directions) return;
    const params = new URLSearchParams(window.location.search);
    directions.textContent =
      params.get("directions") || "本次方向：未选择（按自然交流整理）";
  };

  const initGenerationProgress = () => {
    const steps = all("[data-progress-step]");
    if (!steps.length) return;
    const artifact = one("[data-artifact]");
    const composer = one("[data-progress-composer]");
    let timer = 0;
    let index = 0;
    const show = (nextIndex) => {
      index = nextIndex;
      steps.forEach((step, stepIndex) => {
        step.classList.toggle("done", stepIndex < index);
        step.classList.toggle("active", stepIndex === index);
      });
    };
    const complete = () => {
      steps.forEach((step) => {
        step.classList.remove("active");
        step.classList.add("done");
      });
      all("[data-progress-card]").forEach((card) => {
        card.hidden = true;
      });
      artifact.hidden = false;
      composer.hidden = false;
      document.body.dataset.conversationStage = "completed";
      document.body.dataset.mobileView = "artifact";
      all("[data-mobile-tab]").forEach((trigger) =>
        trigger.classList.toggle("active", trigger.dataset.mobileTab === "artifact")
      );
    };
    const tick = () => {
      if (index >= steps.length - 1) {
        complete();
        return;
      }
      show(index + 1);
      timer = window.setTimeout(tick, 720);
    };
    show(0);
    timer = window.setTimeout(tick, 720);
    window.addEventListener("pagehide", () => window.clearTimeout(timer), { once: true });
  };

  const artifactVersions = {
    V1: {
      title: "想自己看一会儿，也可以",
      summary:
        "这篇从门店人物的个人感受出发：有人暂时不想说话时，先给对方一点自己的节奏，不把它写成统一服务承诺。",
      main:
        "我在店里有时会遇到这样的时刻：有人走进来，不急着问，也不急着回应，只想先自己看看。<br><br>以前我会担心，是不是应该马上介绍点什么。后来我更愿意先留一点安静。对方也许只是在看颜色、摸摸衣服，或者还没想好今天需要什么。<br><br>对我来说，沉默不一定是拒绝，也可能是在认真感受。先让这一小段安静成立，再等对方愿意开口。",
    },
    V2: {
      title: "有些沉默，只是想先看一会儿",
      summary:
        "修改后更早落到店员本人的感受，同时保留“尊重沉默”的判断，不扩大为门店统一做法。",
      main:
        "这是我在店里会遇到的一种感受：有人走进来，只想先安静看一会儿。<br><br>我以前总担心是不是该马上介绍。现在我会先停一下，让对方看看颜色、摸摸衣服，也让那一点还没想好的时间自然过去。<br><br>沉默不一定是在拒绝谁。有时，它只是在认真感受。等对方愿意开口，再从那句话开始。",
    },
  };

  const applyArtifactVersion = (version) => {
    const content = artifactVersions[version];
    if (!content) return;
    all("[data-artifact-version]").forEach((node) => {
      node.textContent = version;
    });
    one("[data-artifact-title]").textContent = content.title;
    one("[data-artifact-summary]").textContent = content.summary;
    one("[data-artifact-main]").innerHTML = content.main;
    one("[data-artifact-version-state]").textContent = version === "V1" ? "历史版本" : "当前版本";
  };

  const initVersionActions = () => {
    one("[data-revision-submit]")?.addEventListener("click", () => {
      const input = one("[data-revision-input]");
      if (!input?.value.trim()) {
        setNotice("先说说想保留什么、改变什么。");
        return;
      }
      applyArtifactVersion("V2");
      one("[data-revision-result]").hidden = false;
      one("[data-history-count]").textContent = "历史版本（1）";
      one("[data-history-empty]").hidden = true;
      one("[data-history-versions]").hidden = false;
      setNotice("V2 已生成；V1 仍可在历史版本中打开。");
    });
    all("[data-open-version]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        applyArtifactVersion(trigger.dataset.openVersion);
        closeDrawer(trigger.closest("[data-drawer]"));
        setNotice(`已打开 ${trigger.dataset.openVersion}。`);
      });
    });
  };

  const initArtifactActions = () => {
    const text = () => one("[data-artifact]")?.innerText.trim() || "";
    one("[data-copy-artifact]")?.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(text());
        setNotice("已复制当前版本。");
      } catch (_error) {
        const fallback = document.createElement("textarea");
        fallback.value = text();
        fallback.style.position = "fixed";
        fallback.style.opacity = "0";
        document.body.appendChild(fallback);
        fallback.select();
        const copied = document.execCommand("copy");
        fallback.remove();
        setNotice(copied ? "已复制当前版本。" : "浏览器没有允许复制，请在新窗口中重试。");
      }
    });
    one("[data-export-artifact]")?.addEventListener("click", () => {
      const blob = new Blob([text()], { type: "text/plain;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `笛语内容-${one("[data-artifact-version]")?.textContent || "当前版"}.txt`;
      link.click();
      URL.revokeObjectURL(link.href);
      setNotice("已导出当前版本。");
    });
  };

  const initStaticActions = () => {
    all("[data-action-message]").forEach((trigger) => {
      trigger.addEventListener("click", () => setNotice(trigger.dataset.actionMessage));
    });
  };

  mountAdminRail();
  initDrawers();
  initRange();
  initMemberFilters();
  initEntryType();
  initTabs();
  initLibraryScopes();
  initImportFlow();
  initAdminAccounts();
  initCreatorTarget();
  initMobileTabs();
  initDirections();
  initConversationFlow();
  initRelationshipFlow();
  initStableActions();
  initGenerationSummary();
  initGenerationProgress();
  initVersionActions();
  initArtifactActions();
  initStaticActions();
})();
