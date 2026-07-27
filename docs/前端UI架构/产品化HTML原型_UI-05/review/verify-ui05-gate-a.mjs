import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const prototypeRoot = resolve(here, "..");
const repoRoot = resolve(prototypeRoot, "../../..");
const resultPath = join(here, "verification.json");
const startedAt = new Date().toISOString();
const checks = [];
const negativeProofs = [];
const layouts = [];
const consoleErrors = [];
const externalRequests = [];
const forbiddenFindings = [];

const record = (id, category, status, evidence) => {
  checks.push({ id, category, status, evidence });
  if (status !== "passed") throw new Error(`${id}: ${evidence}`);
};

const walk = (directory) =>
  readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  });

const prototypeFiles = walk(prototypeRoot)
  .filter((path) => path !== resultPath)
  .sort();
const htmlFiles = prototypeFiles.filter((path) => path.endsWith(".html"));
const productFiles = htmlFiles.filter((path) => path.includes(`${join("product", "")}`));

const sourceDigest = createHash("sha256");
for (const path of prototypeFiles) {
  sourceDigest.update(relative(prototypeRoot, path));
  sourceDigest.update(readFileSync(path));
}

const verifyLocalLinks = () => {
  const broken = [];
  const external = [];
  const attributes = /\b(?:href|src)=["']([^"']+)["']/g;
  for (const path of htmlFiles) {
    const source = readFileSync(path, "utf8");
    for (const match of source.matchAll(attributes)) {
      const value = match[1];
      if (/^(?:https?:)?\/\//i.test(value)) {
        external.push({ page: relative(prototypeRoot, path), value });
        continue;
      }
      const target = value.split(/[?#]/, 1)[0];
      if (!target || target.startsWith("#") || /^(?:data|blob|javascript|about):/i.test(target)) {
        continue;
      }
      if (!existsSync(resolve(dirname(path), target))) {
        broken.push({ page: relative(prototypeRoot, path), value });
      }
    }
  }
  const reviewSource = readFileSync(join(here, "review.js"), "utf8");
  for (const match of reviewSource.matchAll(/["'](\.\.\/product\/[^"']+?\.html(?:\?[^"']*)?)["']/g)) {
    const target = match[1].split(/[?#]/, 1)[0];
    if (!existsSync(resolve(here, target))) broken.push({ page: "review/review.js", value: match[1] });
  }
  record(
    "static.local_links",
    "static",
    broken.length === 0 && external.length === 0 ? "passed" : "failed",
    { html_files: htmlFiles.length, broken, external }
  );
};

const visibleText = (source) =>
  source
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");

const verifyLanguageAndAdminLinks = () => {
  const forbidden = [
    /\bP[1-5]\b/i,
    /\bDM01\b/i,
    /\bRLS\b/i,
    /tenant_id/i,
    /ContentRole/i,
    /carrier_of_account_id/i,
    /服务端可信/,
    /当前正式会话/,
    /候选对象/,
    /内容边界无法在一次单元修复内满足/,
    /事实边界/,
    /单元修复/,
    /适配器/,
    /合同失败/,
    /模型 JSON/i,
    /\bPrompt\b/i,
    /\b422\b/,
  ];
  const closedRelationshipEnums = [
    "闺蜜聊天",
    "婆媳聊天",
    "夫妻聊天",
    "母女聊天",
    "店员顾客聊天",
  ];
  for (const path of productFiles) {
    const text = visibleText(readFileSync(path, "utf8"));
    for (const pattern of forbidden) {
      if (pattern.test(text)) forbiddenFindings.push({ page: basename(path), term: String(pattern) });
    }
    for (const term of closedRelationshipEnums) {
      if (text.includes(term)) forbiddenFindings.push({ page: basename(path), term });
    }
  }

  const adminPages = [
    "admin-overview.html",
    "team-usage.html",
    "members.html",
    "publishing-account.html",
    "brand-library.html",
    "readiness.html",
    "access-admin-creator.html",
  ];
  const adminCreatorLinks = [];
  for (const file of adminPages) {
    const source = readFileSync(join(prototypeRoot, "product", file), "utf8");
    for (const match of source.matchAll(/\bhref=["']([^"']+)["']/g)) {
      if (/creator-|\/content/i.test(match[1])) adminCreatorLinks.push({ file, href: match[1] });
    }
  }
  record(
    "static.product_language",
    "static",
    forbiddenFindings.length === 0 ? "passed" : "failed",
    { forbidden_findings: forbiddenFindings }
  );
  record(
    "static.admin_no_creator_links",
    "static",
    adminCreatorLinks.length === 0 ? "passed" : "failed",
    { links: adminCreatorLinks }
  );

  const librarySource = readFileSync(join(prototypeRoot, "product", "brand-library.html"), "utf8");
  const oldLibraryTerms = ["发布账号与画像", "全品牌", "品牌内容</span>", "演示内容", "总部内容组"];
  const oldMatches = oldLibraryTerms.filter((term) => librarySource.includes(term));
  record(
    "static.library_scope_language",
    "static",
    oldMatches.length === 0 ? "passed" : "failed",
    { old_matches: oldMatches }
  );
};

const assertAdminNoCreator = (links) => {
  if (links.some((link) => /creator-|\/content/i.test(link))) {
    throw new Error("管理员旅程出现了创作链接");
  }
};
const assertOrdinaryChat = (evidence) => {
  if (evidence.artifactPresent || evidence.navigated || evidence.stage !== "chat") {
    throw new Error("普通交流直接进入了成品");
  }
};
const assertFiveAxes = (axes) => {
  for (const axis of ["topic", "approach", "style", "format", "continuity"]) {
    if (!axes.includes(axis)) throw new Error(`缺少 ${axis} 轴`);
  }
};
const assertRelation = (text) => {
  if (!text.includes("婆媳") || !/不(?:要)?把任何一方写成反派/.test(text) || text.includes("闺蜜")) {
    throw new Error("人物关系原话或本次边界没有保留");
  }
};
const assertScopes = (scopes) => {
  for (const scope of ["品牌全员", "总部专用", "指定区域"]) {
    if (!scopes.includes(scope)) throw new Error(`缺少 ${scope} 范围`);
  }
};

const negative = (id, mutation, check) => {
  let caught = false;
  let message = "";
  try {
    check();
  } catch (error) {
    caught = true;
    message = error.message;
  }
  negativeProofs.push({ id, mutation, caught, error_message: message });
  if (!caught) throw new Error(`反向证明未能令 ${id} 失败`);
};

const findChrome = () => {
  const candidates = [
    process.env.UI05_CHROME,
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/home/faye/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome",
    "/home/faye/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome",
  ].filter(Boolean);
  const which = spawnSync("sh", ["-lc", "command -v google-chrome || command -v chromium || true"], {
    encoding: "utf8",
  }).stdout.trim();
  if (which) candidates.unshift(which);
  return candidates.find((path) => existsSync(path) && statSync(path).isFile()) || "";
};

const runBrowserChecks = async () => {
  const chromePath = findChrome();
  if (!chromePath) throw new Error("未找到本机 Chrome；浏览器验证不能降级为通过");
  const wsPath = join(repoRoot, "frontend", "node_modules", "ws", "index.js");
  if (!existsSync(wsPath)) throw new Error("缺少仓库既有 ws 依赖，无法连接本机 Chrome");
  const { default: WebSocket } = await import(pathToFileURL(wsPath).href);
  const profile = mkdtempSync(join(tmpdir(), "ui05-gate-a-"));
  const chrome = spawn(
    chromePath,
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      "--disable-crash-reporter",
      "--disable-background-networking",
      "--disable-component-update",
      "--disable-default-apps",
      "--disable-sync",
      "--metrics-recording-only",
      "--no-first-run",
      "--allow-file-access-from-files",
      "--remote-debugging-port=0",
      `--user-data-dir=${profile}`,
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "pipe"] }
  );

  let socket;
  try {
    const wsUrl = await new Promise((resolvePromise, reject) => {
      let buffered = "";
      const timer = setTimeout(() => reject(new Error("Chrome DevTools 启动超时")), 10000);
      chrome.stderr.on("data", (chunk) => {
        buffered += chunk.toString();
        const match = buffered.match(/DevTools listening on (ws:\/\/[^\s]+)/);
        if (match) {
          clearTimeout(timer);
          resolvePromise(match[1]);
        }
      });
      chrome.once("exit", (code) => reject(new Error(`Chrome 提前退出：${code}`)));
    });
    socket = new WebSocket(wsUrl);
    await new Promise((resolvePromise, reject) => {
      socket.once("open", resolvePromise);
      socket.once("error", reject);
    });

    let sequence = 0;
    const pending = new Map();
    const events = [];
    socket.on("message", (raw) => {
      const message = JSON.parse(raw.toString());
      if (message.id) {
        const waiter = pending.get(message.id);
        if (!waiter) return;
        pending.delete(message.id);
        if (message.error) waiter.reject(new Error(JSON.stringify(message.error)));
        else waiter.resolve(message.result || {});
      } else {
        events.push(message);
      }
    });
    const send = (method, params = {}, sessionId) =>
      new Promise((resolvePromise, reject) => {
        const id = ++sequence;
        pending.set(id, { resolve: resolvePromise, reject });
        socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
      });
    const pause = (ms) => new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
    const evaluate = async (expression, sessionId) => {
      const result = await send(
        "Runtime.evaluate",
        { expression, awaitPromise: true, returnByValue: true },
        sessionId
      );
      if (result.exceptionDetails) {
        const description = result.result?.description || result.exceptionDetails.exception?.description;
        throw new Error(description || result.exceptionDetails.text);
      }
      return result.result.value;
    };
    const { targetId } = await send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
    await send("Page.enable", {}, sessionId);
    await send("Runtime.enable", {}, sessionId);
    await send("Log.enable", {}, sessionId);
    await send("Network.enable", {}, sessionId);

    const navigate = async (relativePath, wait = 160) => {
      const url = `${pathToFileURL(join(prototypeRoot, relativePath.split("?")[0])).href}${
        relativePath.includes("?") ? `?${relativePath.split("?").slice(1).join("?")}` : ""
      }`;
      await send("Page.navigate", { url }, sessionId);
      for (let attempt = 0; attempt < 80; attempt += 1) {
        if ((await evaluate("document.readyState", sessionId)) === "complete") break;
        await pause(40);
      }
      await pause(wait);
    };

    await navigate("review/index.html");
    const reviewEvidence = await evaluate(
      `(() => {
        const homeVisible = !document.querySelector('[data-journey-home]').hidden;
        document.querySelector('[data-journey="admin"]').click();
        const admin = [...document.querySelectorAll('[data-page]')].map((node) => node.textContent.trim());
        const adminFirstSrc = document.querySelector('[data-review-frame]').getAttribute('src');
        document.querySelector('[data-journey="creator"]').click();
        const creator = [...document.querySelectorAll('[data-page]')].map((node) => node.textContent.trim());
        const creatorFirstSrc = document.querySelector('[data-review-frame]').getAttribute('src');
        return { homeVisible, admin, creator, adminFirstSrc, creatorFirstSrc };
      })()`,
      sessionId
    );
    record(
      "browser.journey_separation",
      "browser",
      reviewEvidence.homeVisible &&
        reviewEvidence.admin.length === 7 &&
        reviewEvidence.creator.length === 5 &&
        reviewEvidence.admin.every((name) => !/自然交流|生成过程|婆媳/.test(name)) &&
        reviewEvidence.adminFirstSrc.endsWith("admin-overview.html") &&
        reviewEvidence.creatorFirstSrc.includes("creator-empty.html")
        ? "passed"
        : "failed",
      reviewEvidence
    );

    await navigate("product/members.html");
    const entryEvidence = await evaluate(
      `(() => {
        document.querySelector('[data-open-drawer="add-member"]').click();
        const admin = document.querySelector('[data-entry-type][value="tenant-admin"]');
        const user = document.querySelector('[data-entry-type][value="tenant-user"]');
        admin.click();
        const adminState = {
          mutuallyExclusive: admin.checked && !user.checked,
          userHidden: document.querySelector('[data-entry-user]').hidden,
          userDisabled: [...document.querySelectorAll('[data-entry-user] input')].every((node) => node.disabled),
          adminVisible: !document.querySelector('[data-entry-admin]').hidden
        };
        user.click();
        const userState = {
          mutuallyExclusive: user.checked && !admin.checked,
          userVisible: !document.querySelector('[data-entry-user]').hidden,
          userEnabled: [...document.querySelectorAll('[data-entry-user] input')].every((node) => !node.disabled),
          adminHidden: document.querySelector('[data-entry-admin]').hidden
        };
        return { adminState, userState };
      })()`,
      sessionId
    );
    record(
      "browser.entry_type_exclusive",
      "browser",
      Object.values(entryEvidence.adminState).every(Boolean) &&
        Object.values(entryEvidence.userState).every(Boolean)
        ? "passed"
        : "failed",
      entryEvidence
    );

    await navigate("product/creator-empty.html?account=hq&platform=douyin&format=video");
    const accountEvidence = await evaluate(
      `(() => {
        const identity = document.querySelector('[data-identity-select]');
        const platform = document.querySelector('[data-platform-select]');
        const format = document.querySelector('[data-format-select]');
        const countTargets = () => {
          let total = 0;
          for (const option of [...platform.options]) {
            platform.value = option.value;
            platform.dispatchEvent(new Event('change'));
            total += format.options.length;
          }
          return total;
        };
        const hq = {
          name: identity.options[identity.selectedIndex].textContent,
          platforms: [...platform.options].map((option) => option.textContent),
          targets: countTargets(),
          profile: document.querySelector('[data-profile-summary]').textContent
        };
        identity.value = 'store';
        identity.dispatchEvent(new Event('change'));
        const store = {
          name: identity.options[identity.selectedIndex].textContent,
          platforms: [...platform.options].map((option) => option.textContent),
          targets: countTargets(),
          profile: document.querySelector('[data-profile-summary]').textContent
        };
        return { hq, store, path: location.pathname };
      })()`,
      sessionId
    );
    record(
      "browser.identities_and_targets",
      "browser",
      accountEvidence.hq.name.includes("总部") &&
        accountEvidence.hq.platforms.length === 3 &&
        accountEvidence.hq.targets === 4 &&
        accountEvidence.store.name.includes("柯桥") &&
        accountEvidence.store.platforms.length === 2 &&
        accountEvidence.store.profile.includes("门店")
        ? "passed"
        : "failed",
      accountEvidence
    );

    await navigate(
      "product/creator-empty.html?account=store&platform=xiaohongshu&format=graphic"
    );
    const ordinaryChat = await evaluate(
      `(() => {
        const before = location.href;
        document.querySelector('[data-conversation-submit]').click();
        return {
          stage: document.body.dataset.conversationStage,
          navigated: location.href !== before,
          artifactPresent: !!document.querySelector('[data-artifact]'),
          text: document.querySelector('[data-message-list]').textContent
        };
      })()`,
      sessionId
    );
    assertOrdinaryChat(ordinaryChat);
    record("browser.ordinary_chat", "browser", "passed", ordinaryChat);

    const clarification = await evaluate(
      `(() => {
        document.querySelector('[data-conversation-submit]').click();
        const text = document.querySelector('[data-message-list]').textContent;
        return {
          stage: document.body.dataset.conversationStage,
          firstRoundPreserved: text.includes('最近店里总有人只想自己看看。'),
          oneQuestion: (text.match(/沉默也应该被尊重/g) || []).length === 1,
          noVersion: !/V1|版本/.test(text)
        };
      })()`,
      sessionId
    );
    record(
      "browser.clarification_before_generation",
      "browser",
      clarification.stage === "clarifying" &&
        clarification.firstRoundPreserved &&
        clarification.oneQuestion &&
        clarification.noVersion
        ? "passed"
        : "failed",
      clarification
    );

    const axesEvidence = await evaluate(
      `(() => {
        document.querySelector('[data-direction-toggle]').click();
        const axes = [...document.querySelectorAll('[data-axis]')];
        axes.forEach((axis) => axis.querySelector('[data-axis-choice]').click());
        const custom = document.querySelector('[data-axis-custom]');
        if (!custom) {
          return {
            axes: axes.map((axis) => axis.dataset.axis),
            counts: axes.map((axis) => axis.querySelectorAll('[data-axis-choice]').length),
            hasMore: axes.every((axis) => axis.querySelector('[data-axis-more]')),
            summary: document.querySelector('[data-direction-summary]')?.textContent || '',
            customMissing: true
          };
        }
        custom.value = '保留店员自己的停顿';
        custom.dispatchEvent(new Event('input'));
        return {
          axes: axes.map((axis) => axis.dataset.axis),
          counts: axes.map((axis) => axis.querySelectorAll('[data-axis-choice]').length),
          hasMore: axes.every((axis) => axis.querySelector('[data-axis-more]')),
          summary: document.querySelector('[data-direction-summary]').textContent,
          customMissing: false
        };
      })()`,
      sessionId
    );
    assertFiveAxes(axesEvidence.axes);
    record(
      "browser.five_axes",
      "browser",
      axesEvidence.counts.every((count) => count >= 2 && count <= 4) &&
        axesEvidence.hasMore &&
        !axesEvidence.customMissing &&
        axesEvidence.summary.includes("讲法") &&
        axesEvidence.summary.includes("保留店员自己的停顿")
        ? "passed"
        : "failed",
      axesEvidence
    );

    await evaluate(`document.querySelector('[data-conversation-submit]').click()`, sessionId);
    for (let attempt = 0; attempt < 60; attempt += 1) {
      if ((await evaluate("location.pathname", sessionId)).endsWith("creator-generating.html")) break;
      await pause(50);
    }
    await pause(200);
    const preGeneration = await evaluate(
      `(() => {
        const text = document.querySelector('[data-generation-summary]').textContent;
        return {
          stage: document.body.dataset.conversationStage,
          account: document.querySelector('[data-identity-select]').value,
          platform: document.querySelector('[data-platform-select]').value,
          format: document.querySelector('[data-format-select]').value,
          frozen: document.querySelector('[data-identity-select]').disabled &&
            document.querySelector('[data-platform-select]').disabled &&
            document.querySelector('[data-format-select]').disabled,
          text
        };
      })()`,
      sessionId
    );
    record(
      "browser.complete_requirement_starts_generation",
      "browser",
      preGeneration.stage === "generating" &&
        preGeneration.account === "store" &&
        preGeneration.platform === "xiaohongshu" &&
        preGeneration.format === "graphic" &&
        preGeneration.frozen &&
        preGeneration.text.includes("店员自己的感受") &&
        preGeneration.text.includes("保留店员自己的停顿")
        ? "passed"
        : "failed",
      preGeneration
    );
    await pause(3800);
    const completed = await evaluate(
      `(() => {
        const artifact = document.querySelector('[data-artifact]');
        const v1Text = artifact.textContent;
        document.querySelector('[data-revision-submit]').click();
        const v2 = {
          version: document.querySelector('[data-artifact-version]').textContent,
          title: document.querySelector('[data-artifact-title]').textContent,
          main: document.querySelector('[data-artifact-main]').textContent
        };
        document.querySelector('[data-open-drawer="history"]').click();
        document.querySelector('[data-open-version="V1"]').click();
        return {
          stage: document.body.dataset.conversationStage,
          artifactVisible: !artifact.hidden,
          v1HasStoreFeeling: v1Text.includes('我在店里'),
          v2,
          backToV1: document.querySelector('[data-artifact-version]').textContent === 'V1',
          v1Restored: document.querySelector('[data-artifact-title]').textContent === '想自己看一会儿，也可以'
        };
      })()`,
      sessionId
    );
    record(
      "browser.v1_v2_history",
      "browser",
      completed.stage === "completed" &&
        completed.artifactVisible &&
        completed.v1HasStoreFeeling &&
        completed.v2.version === "V2" &&
        completed.v2.title !== "想自己看一会儿，也可以" &&
        completed.backToV1 &&
        completed.v1Restored
        ? "passed"
        : "failed",
      completed
    );

    await navigate(
      "product/creator-generating.html?account=store&platform=xiaohongshu&format=graphic"
    );
    const optionalDirectionEvidence = await evaluate(
      `(() => ({
        text: document.querySelector('[data-directions-used]').textContent.trim(),
        inventedSelection: /题材：|讲法：|风格：|形式：|系列与互动：/.test(
          document.querySelector('[data-directions-used]').textContent
        )
      }))()`,
      sessionId
    );
    record(
      "browser.optional_directions_stay_unselected",
      "browser",
      optionalDirectionEvidence.text === "本次方向：未选择（按自然交流整理）" &&
        !optionalDirectionEvidence.inventedSelection
        ? "passed"
        : "failed",
      optionalDirectionEvidence
    );

    await navigate(
      "product/creator-relationship.html?account=store&platform=xiaohongshu&format=graphic"
    );
    const relationEvidence = await evaluate(
      `(() => {
        const text = document.body.innerText;
        return {
          text,
          original: document.querySelector('[data-original-relation]').textContent,
          noClosedReplacement: !text.includes('闺蜜') && !text.includes('没有婆媳这个选项')
        };
      })()`,
      sessionId
    );
    assertRelation(relationEvidence.text);
    record(
      "browser.relationship_verbatim",
      "browser",
      relationEvidence.noClosedReplacement &&
        relationEvidence.original.includes("婆媳") &&
        relationEvidence.original.includes("不要把任何一方写成反派")
        ? "passed"
        : "failed",
      { original: relationEvidence.original, noClosedReplacement: relationEvidence.noClosedReplacement }
    );

    await navigate(
      "product/creator-failure.html?account=store&platform=xiaohongshu&format=graphic"
    );
    const failureEvidence = await evaluate(
      `(() => {
        const text = document.body.innerText;
        return {
          stage: document.body.dataset.conversationStage,
          message: document.querySelector('[data-generation-failure]').textContent,
          originalInput: document.querySelector('[data-failure-input]').value,
          artifactPresent: !!document.querySelector('[data-artifact]'),
          fakeVersion: /\\bV1\\b/.test(text),
          actions: [...document.querySelectorAll('[data-recovery-action]')].map((node) => node.textContent.trim())
        };
      })()`,
      sessionId
    );
    record(
      "browser.failure_recovery",
      "browser",
      failureEvidence.stage === "failed" &&
        failureEvidence.message.includes("这次还没能整理成一份可靠的成品") &&
        failureEvidence.originalInput.includes("沉默也应该被尊重") &&
        !failureEvidence.artifactPresent &&
        !failureEvidence.fakeVersion &&
        failureEvidence.actions.join("|") === "继续补充|再试一次"
        ? "passed"
        : "failed",
      failureEvidence
    );

    await navigate("product/brand-library.html");
    const scopeEvidence = await evaluate(
      `(() => {
        const filters = [...document.querySelectorAll('[data-scope-filter]')].map((node) => node.textContent.trim());
        const rows = [...document.querySelectorAll('[data-library-row]')].map((node) => ({
          scope: node.dataset.libraryScope,
          text: node.textContent
        }));
        document.querySelector('[data-open-drawer="import"]').click();
        document.querySelector('[data-import-next]').click();
        document.querySelector('[data-import-next]').click();
        const scope = document.querySelector('[data-scope-select]');
        scope.value = 'region';
        scope.dispatchEvent(new Event('change'));
        const regionFieldVisible = !document.querySelector('[data-region-field]').hidden;
        document.querySelector('[data-import-next]').click();
        const blockedWithoutRegion =
          !document.querySelector('[data-region-error]').hidden &&
          !document.querySelector('[data-import-step="3"]').hidden;
        const region = document.querySelector('[data-region-select]');
        region.value = '浙江区域';
        region.dispatchEvent(new Event('change'));
        document.querySelector('[data-import-next]').click();
        return {
          filters,
          rows,
          regionFieldVisible,
          blockedWithoutRegion,
          finalScope: document.querySelector('[data-import-scope-summary]').textContent,
          noAccountCategory: !document.body.innerText.includes('发布账号与画像')
        };
      })()`,
      sessionId
    );
    assertScopes(scopeEvidence.filters);
    record(
      "browser.library_scopes",
      "browser",
      scopeEvidence.regionFieldVisible &&
        scopeEvidence.blockedWithoutRegion &&
        scopeEvidence.finalScope === "浙江区域可用" &&
        scopeEvidence.noAccountCategory &&
        scopeEvidence.rows.some((row) => row.text.includes("总部专用")) &&
        scopeEvidence.rows.some((row) => row.text.includes("其他区域不可用"))
        ? "passed"
        : "failed",
      scopeEvidence
    );

    const pagePaths = [
      "product/admin-overview.html",
      "product/team-usage.html",
      "product/members.html",
      "product/publishing-account.html",
      "product/brand-library.html",
      "product/readiness.html",
      "product/access-admin-creator.html",
      "product/creator-empty.html?account=store&platform=xiaohongshu&format=graphic",
      "product/creator-relationship.html?account=store&platform=xiaohongshu&format=graphic",
      "product/creator-generating.html?account=store&platform=xiaohongshu&format=graphic",
      "product/creator-failure.html?account=store&platform=xiaohongshu&format=graphic",
      "product/access-user-admin.html",
    ];
    const viewports = [
      { name: "desktop", width: 1440, height: 900, mobile: false },
      { name: "mobile", width: 390, height: 844, mobile: true },
    ];
    for (const viewport of viewports) {
      await send(
        "Emulation.setDeviceMetricsOverride",
        {
          width: viewport.width,
          height: viewport.height,
          deviceScaleFactor: 1,
          mobile: viewport.mobile,
        },
        sessionId
      );
      for (const page of pagePaths) {
        const eventStart = events.length;
        await navigate(page, page.includes("creator-generating") ? 3800 : 120);
        const metric = await evaluate(
          `(() => {
            const visible = (node) => {
              const style = getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return style.display !== 'none' && style.visibility !== 'hidden' &&
                rect.width > 0 && rect.height > 0;
            };
            const controls = [...document.querySelectorAll('button,a,input,select,textarea')]
              .filter(visible)
              .map((node) => {
                const target = node.matches('input[type="checkbox"],input[type="radio"]')
                  ? node.closest('label') || node
                  : node;
                const rect = target.getBoundingClientRect();
                return {
                  label: (node.getAttribute('aria-label') || node.textContent || node.value || node.tagName)
                    .trim().slice(0, 60),
                  width: Math.round(rect.width),
                  height: Math.round(rect.height)
                };
              });
            return {
              innerWidth,
              scrollWidth: document.documentElement.scrollWidth,
              overflow: document.documentElement.scrollWidth > innerWidth + 1,
              undersized: controls.filter((item) => item.width < 44 || item.height < 44)
            };
          })()`,
          sessionId
        );
        layouts.push({ page, viewport: viewport.name, ...metric });
        for (const event of events.slice(eventStart)) {
          if (
            event.method === "Runtime.exceptionThrown" ||
            (event.method === "Log.entryAdded" && event.params.entry.level === "error") ||
            (event.method === "Runtime.consoleAPICalled" && event.params.type === "error")
          ) {
            consoleErrors.push({ page, viewport: viewport.name, method: event.method });
          }
          if (event.method === "Network.requestWillBeSent") {
            const url = event.params.request.url;
            if (!/^(?:file|data|blob|about|devtools):/.test(url)) {
              externalRequests.push({ page, viewport: viewport.name, url });
            }
          }
        }
      }
    }
    const layoutFailures = layouts.filter((item) => item.overflow || item.undersized.length);
    record(
      "browser.viewport_quality",
      "browser",
      layoutFailures.length === 0 &&
        consoleErrors.length === 0 &&
        externalRequests.length === 0
        ? "passed"
        : "failed",
      {
        combinations: layouts.length,
        layout_failures: layoutFailures,
        console_errors: consoleErrors,
        external_requests: externalRequests,
      }
    );

    const adminLinks = [];
    for (const file of [
      "admin-overview.html",
      "team-usage.html",
      "members.html",
      "publishing-account.html",
      "brand-library.html",
      "readiness.html",
      "access-admin-creator.html",
    ]) {
      const source = readFileSync(join(prototypeRoot, "product", file), "utf8");
      adminLinks.push(...[...source.matchAll(/\bhref=["']([^"']+)["']/g)].map((match) => match[1]));
    }
    assertAdminNoCreator(adminLinks);
    negative("negative.admin_creator_link", "向管理员链接注入 creator-empty.html", () =>
      assertAdminNoCreator([...adminLinks, "creator-empty.html"])
    );
    negative("negative.ordinary_chat_direct_artifact", "把普通交流证据改为已出现成品", () =>
      assertOrdinaryChat({ ...ordinaryChat, artifactPresent: true, navigated: true })
    );
    negative("negative.missing_approach_axis", "从五轴证据删除讲法轴", () =>
      assertFiveAxes(axesEvidence.axes.filter((axis) => axis !== "approach"))
    );
    negative("negative.relation_replaced", "把婆媳原词替换为闺蜜", () =>
      assertRelation(relationEvidence.text.replaceAll("婆媳", "闺蜜"))
    );
    negative("negative.missing_hq_scope", "从范围证据删除总部专用", () =>
      assertScopes(scopeEvidence.filters.filter((scope) => scope !== "总部专用"))
    );
    record(
      "negative.proofs",
      "negative",
      negativeProofs.every((proof) => proof.caught) ? "passed" : "failed",
      negativeProofs
    );

    await send("Browser.close");
    socket.close();
    return { chromePath };
  } finally {
    if (socket?.readyState === 1) socket.close();
    if (chrome.exitCode === null) {
      chrome.kill("SIGTERM");
      await Promise.race([
        new Promise((resolvePromise) => chrome.once("exit", resolvePromise)),
        new Promise((resolvePromise) => setTimeout(resolvePromise, 1000)),
      ]);
    }
    rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 50 });
  }
};

let status = "passed";
let failure = "";
let browser = {};
try {
  verifyLocalLinks();
  verifyLanguageAndAdminLinks();
  const syntaxFiles = [
    join(prototypeRoot, "shared", "product.js"),
    join(here, "review.js"),
    fileURLToPath(import.meta.url),
  ];
  const syntax = syntaxFiles.map((path) => ({
    file: relative(repoRoot, path),
    status: spawnSync(process.execPath, ["--check", path]).status,
  }));
  record(
    "static.javascript_syntax",
    "static",
    syntax.every((item) => item.status === 0) ? "passed" : "failed",
    syntax
  );
  browser = await runBrowserChecks();
} catch (error) {
  status = "failed";
  failure = error.stack || error.message;
}

const output = {
  schema_version: "ui05-gate-a-verification-v1",
  verified_at_utc: startedAt,
  git_base_sha:
    spawnSync("git", ["rev-parse", "HEAD"], { cwd: repoRoot, encoding: "utf8" }).stdout.trim(),
  prototype_source_sha256: sourceDigest.digest("hex"),
  verifier_sha256: createHash("sha256")
    .update(readFileSync(fileURLToPath(import.meta.url)))
    .digest("hex"),
  environment: {
    node: process.version,
    browser: browser.chromePath || "",
    mode: "local-file-headless-chrome",
    viewports: ["1440x900", "390x844"],
  },
  summary: {
    status,
    total: checks.length,
    passed: checks.filter((check) => check.status === "passed").length,
    failed: checks.filter((check) => check.status !== "passed").length + (failure ? 1 : 0),
  },
  checks,
  negative_proofs: negativeProofs,
  layout: layouts,
  console_errors: consoleErrors,
  external_requests: externalRequests,
  forbidden_terms: forbiddenFindings,
  asset_activation_delta: 0,
  failure,
};
writeFileSync(resultPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
console.log(
  JSON.stringify(
    {
      status: output.summary.status,
      checks: output.summary,
      negative_proofs: negativeProofs.length,
      layout_combinations: layouts.length,
      result: relative(repoRoot, resultPath),
    },
    null,
    2
  )
);
if (status !== "passed") process.exitCode = 1;
