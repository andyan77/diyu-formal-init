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

  const initTabs = () => {
    all("[data-tab-group]").forEach((group) => {
      const name = group.dataset.tabGroup;
      const choose = (value) => {
        all(`[data-tab-group="${name}"] [data-tab]`).forEach((trigger) => {
          trigger.classList.toggle("active", trigger.dataset.tab === value);
          trigger.setAttribute("aria-selected", String(trigger.dataset.tab === value));
        });
        all(`[data-tab-panel-group="${name}"]`).forEach((panel) => {
          panel.hidden = panel.dataset.tabPanel !== value;
        });
      };
      all("[data-tab]", group).forEach((trigger) => {
        trigger.addEventListener("click", () => choose(trigger.dataset.tab));
      });
    });
  };

  const initImportFlow = () => {
    const drawer = one('[data-drawer="import"]');
    if (!drawer) return;
    let step = 1;
    const button = one("[data-import-next]", drawer);
    const back = one("[data-import-back]", drawer);
    const render = () => {
      all("[data-import-step]", drawer).forEach((panel) => {
        panel.hidden = Number(panel.dataset.importStep) !== step;
      });
      all("[data-step]", drawer).forEach((item) => {
        item.classList.toggle("active", Number(item.dataset.step) <= step);
      });
      back.hidden = step === 1 || step === 4;
      button.textContent =
        step === 1 ? "预览字段" : step === 2 ? "补充资料范围" : step === 3 ? "保存这批资料" : "完成";
    };
    button.addEventListener("click", () => {
      if (step < 4) {
        step += 1;
        render();
      } else {
        closeDrawer(drawer);
        setNotice("2 条商品资料已保存为第 1 版；留空字段保持待补。");
        step = 1;
        render();
      }
    });
    back.addEventListener("click", () => {
      step = Math.max(1, step - 1);
      render();
    });
    render();
  };

  const platformName = (value) =>
    ({ douyin: "抖音", xiaohongshu: "小红书", wechat_channels: "微信视频号" })[value] ||
    "抖音";

  const formatName = (value) => (value === "graphic" ? "图文" : "视频");

  const syncTargetLabels = (platform, format) => {
    all("[data-platform-label]").forEach((node) => {
      node.textContent = platformName(platform);
    });
    all("[data-format-label]").forEach((node) => {
      node.textContent = formatName(format);
    });
    all("[data-only-format]").forEach((node) => {
      node.hidden = node.dataset.onlyFormat !== format;
    });
  };

  const syncPlatformControls = () => {
    const platform = one("[data-platform-select]");
    const format = one("[data-format-select]");
    if (!platform || !format) return;
    const selectedPlatform = platform.value;
    const graphic = one('option[value="graphic"]', format);
    if (graphic) graphic.disabled = selectedPlatform !== "xiaohongshu";
    if (selectedPlatform !== "xiaohongshu") format.value = "video";
    syncTargetLabels(selectedPlatform, format.value);
  };

  const detectNamedTarget = (text) => {
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

  const creatorDestination = () => {
    const platform = one("[data-platform-select]")?.value || "douyin";
    const format = one("[data-format-select]")?.value || "video";
    return `creator-generating.html?platform=${encodeURIComponent(platform)}&format=${encodeURIComponent(
      format
    )}`;
  };

  const initCreatorControls = () => {
    const platform = one("[data-platform-select]");
    const format = one("[data-format-select]");
    const params = new URLSearchParams(window.location.search);
    all("[data-mobile-tab]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        document.body.dataset.mobileView = trigger.dataset.mobileTab;
        all("[data-mobile-tab]").forEach((candidate) =>
          candidate.classList.toggle("active", candidate === trigger)
        );
      });
    });
    if (!platform || !format) {
      syncTargetLabels(params.get("platform") || "douyin", params.get("format") || "video");
      return;
    }
    if (params.get("platform")) platform.value = params.get("platform");
    if (params.get("format")) format.value = params.get("format");
    platform.addEventListener("change", syncPlatformControls);
    format.addEventListener("change", syncPlatformControls);
    syncPlatformControls();

    const directionToggle = one("[data-direction-toggle]");
    const directionPanel = one("[data-direction-panel]");
    directionToggle?.addEventListener("click", () => {
      const open = directionPanel.hidden;
      directionPanel.hidden = !open;
      directionToggle.setAttribute("aria-expanded", String(open));
    });

    const submit = one("[data-create-submit]");
    const input = one("[data-creator-input]");
    const conflict = one("[data-target-conflict]");
    submit?.addEventListener("click", () => {
      const named = detectNamedTarget(input?.value || "");
      const platformConflict = named.platform && named.platform !== platform.value;
      const formatConflict = named.format && named.format !== format.value;
      if ((platformConflict || formatConflict) && conflict) {
        one("[data-conflict-current]", conflict).textContent = `${platformName(platform.value)} · ${
          formatName(format.value)
        }`;
        one("[data-conflict-named]", conflict).textContent = `${platformName(
          named.platform || platform.value
        )}${named.format ? ` · ${formatName(named.format)}` : ""}`;
        conflict.dataset.namedPlatform = named.platform;
        conflict.dataset.namedFormat = named.format;
        conflict.hidden = false;
        conflict.scrollIntoView({ block: "nearest" });
        return;
      }
      window.location.href = creatorDestination();
    });
    one("[data-conflict-keep]")?.addEventListener("click", () => {
      conflict.hidden = true;
      window.location.href = creatorDestination();
    });
    one("[data-conflict-switch]")?.addEventListener("click", () => {
      const nextPlatform = conflict.dataset.namedPlatform;
      const nextFormat = conflict.dataset.namedFormat;
      if (nextPlatform) platform.value = nextPlatform;
      syncPlatformControls();
      if (nextFormat && (nextFormat === "video" || platform.value === "xiaohongshu")) {
        format.value = nextFormat;
      }
      syncPlatformControls();
      conflict.hidden = true;
    });

  };

  const initChoiceChips = () => {
    all(".direction-group").forEach((group) => {
      all("button", group).forEach((trigger) => {
        trigger.setAttribute("aria-pressed", String(trigger.classList.contains("selected")));
        trigger.addEventListener("click", () => {
          const selected = !trigger.classList.contains("selected");
          all("button", group).forEach((candidate) => {
            candidate.classList.remove("selected");
            candidate.setAttribute("aria-pressed", "false");
          });
          if (selected) {
            trigger.classList.add("selected");
            trigger.setAttribute("aria-pressed", "true");
          }
        });
      });
    });
  };

  const initStablePrototypeActions = () => {
    one("[data-member-create]")?.addEventListener("click", () => {
      one("[data-member-form]").hidden = true;
      one("[data-member-form-actions]").hidden = true;
      one("[data-member-success]").hidden = false;
    });
    one("[data-profile-save]")?.addEventListener("click", (event) => {
      const drawer = event.currentTarget.closest("[data-drawer]");
      all("[data-profile-version]").forEach((node) => {
        node.textContent = "V3";
      });
      if (drawer) closeDrawer(drawer);
      setNotice("账号画像已保存为 V3；已有内容仍保留原版本。");
    });
    one("[data-material-save]")?.addEventListener("click", (event) => {
      const drawer = event.currentTarget.closest("[data-drawer]");
      const count = all('input[type="checkbox"]:checked', drawer).length;
      const summary = one("[data-material-summary]");
      if (summary) summary.textContent = count ? `已选择 ${count} 项素材` : "未选择素材";
      if (drawer) closeDrawer(drawer);
      setNotice(count ? `本次将参考 ${count} 项素材。` : "本次不参考素材。");
    });
    one("[data-series-save]")?.addEventListener("click", (event) => {
      const drawer = event.currentTarget.closest("[data-drawer]");
      const selected = one('input[name="series"]:checked', drawer);
      const summary = one("[data-series-summary]");
      if (summary) summary.textContent = selected?.value || "单篇创作";
      if (drawer) closeDrawer(drawer);
      setNotice(selected?.value === "单篇创作" ? "这次按单篇创作。" : `已加入“${selected?.value}”。`);
    });
    one("[data-revision-submit]")?.addEventListener("click", () => {
      const input = one("[data-revision-input]");
      if (!input?.value.trim()) {
        setNotice("先说说想保留什么、改变什么。");
        return;
      }
      all("[data-artifact-version]").forEach((node) => {
        node.textContent = "V2";
      });
      const title = one("[data-artifact-title]");
      if (title) title.textContent = "想安静看一会儿，也可以";
      const result = one("[data-revision-result]");
      if (result) result.hidden = false;
      const history = one("[data-history-count]");
      if (history) history.textContent = "历史版本（1）";
      const historyEmpty = one("[data-history-empty]");
      if (historyEmpty) historyEmpty.hidden = true;
      const versionRows = one("[data-history-versions]");
      if (versionRows) versionRows.hidden = false;
      const versionState = one("[data-artifact-version-state]");
      if (versionState) versionState.textContent = "当前版本";
      setNotice("V2 已生成；V1 仍可在历史版本中打开。");
    });
    all("[data-open-version]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        const version = trigger.dataset.openVersion;
        all("[data-artifact-version]").forEach((node) => {
          node.textContent = version;
        });
        const versionState = one("[data-artifact-version-state]");
        if (versionState) versionState.textContent = version === "V1" ? "历史版本" : "当前版本";
        const title = one("[data-artifact-title]");
        if (title) {
          title.textContent = version === "V1" ? "想自己看一会儿，也可以" : "想安静看一会儿，也可以";
        }
        const drawer = trigger.closest("[data-drawer]");
        if (drawer) closeDrawer(drawer);
        setNotice(`已打开 ${version}。`);
      });
    });
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
      timer = window.setTimeout(tick, 850);
    };
    show(0);
    timer = window.setTimeout(tick, 850);
    window.addEventListener("pagehide", () => window.clearTimeout(timer), { once: true });
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
      link.download = "笛语内容-V1.txt";
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
  initTabs();
  initImportFlow();
  initCreatorControls();
  initChoiceChips();
  initStablePrototypeActions();
  initGenerationProgress();
  initArtifactActions();
  initStaticActions();
})();
