import { useEffect, useState } from "react";
import type { FormEvent, JSX } from "react";
import { BrandMark } from "../components/Brand";
import { api } from "../services/api";
import "../styles/user-extensions.css";
import type { BootstrapContext } from "./types";

type DisplayVersion = {
  kind: "display";
  task_id: string;
  version_id: string;
  version: number;
  body: string;
  created_at?: string;
};

type DisplayQuestion = {
  kind: "question" | "handoff";
  message: string;
};

type RecentDisplay = {
  task_id: string;
  version_id: string;
  version: number;
  title: string;
  updated_at: string;
};

type AvailableProduct = {
  sku: string;
  display_name: string;
  display_family: "upper" | "lower" | "";
  product_version_id: string;
};

function isVersion(value: DisplayVersion | DisplayQuestion): value is DisplayVersion {
  return "task_id" in value;
}

function PlanText({ body }: { body: string }): JSX.Element {
  return (
    <article className="display-plan-text">
      {body
        .split("\n")
        .filter(Boolean)
        .map((line, index) =>
          line.endsWith("：") ? (
            <h3 key={`${line}-${index}`}>{line.slice(0, -1)}</h3>
          ) : (
            <p key={`${line.slice(0, 18)}-${index}`}>{line}</p>
          )
        )}
    </article>
  );
}

export default function DisplayApp({
  context
}: {
  context: BootstrapContext;
}): JSX.Element {
  const [inventory, setInventory] = useState("");
  const [feedback, setFeedback] = useState("");
  const [current, setCurrent] = useState<DisplayVersion | null>(null);
  const [viewed, setViewed] = useState<DisplayVersion | null>(null);
  const [versions, setVersions] = useState<DisplayVersion[]>([]);
  const [recent, setRecent] = useState<RecentDisplay[]>([]);
  const [products, setProducts] = useState<AvailableProduct[]>([]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [mobileView, setMobileView] = useState<"conversation" | "plan">("conversation");

  const loadRecent = async (): Promise<void> => {
    try {
      const value = await api<RecentDisplay[]>("/api/v1/display/tasks");
      setRecent(value);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "暂时无法读取历史方案。");
    }
  };

  const loadVersions = async (artifact: DisplayVersion): Promise<void> => {
    const value = await api<DisplayVersion[]>(`/api/v1/display/tasks/${artifact.task_id}/versions`);
    setVersions(value);
  };

  useEffect(() => {
    void loadRecent();
    void api<AvailableProduct[]>("/api/v1/display/products")
      .then(setProducts)
      .catch(error =>
        setNotice(error instanceof Error ? error.message : "暂时无法读取本店商品。")
      );
  }, []);

  const addProduct = (product: AvailableProduct): void => {
    const line = `${product.sku} 1 件`;
    setInventory(value => value.trim() ? `${value.replace(/[。.]?$/, "")}、${line}。` : `本次可用：${line}。`);
  };

  const accept = async (value: DisplayVersion | DisplayQuestion): Promise<void> => {
    if (!isVersion(value)) {
      setNotice(value.message);
      return;
    }
    setCurrent(value);
    setViewed(value);
    await loadVersions(value);
    await loadRecent();
    setMobileView("plan");
  };

  const create = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!inventory.trim() || busy) return;
    setBusy(true);
    setNotice("");
    try {
      await accept(
        await api<DisplayVersion | DisplayQuestion>("/api/v1/display", {
          method: "POST",
          body: JSON.stringify({ inventory_text: inventory.trim() })
        })
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "这次方案没有生成，输入仍保留。");
    } finally {
      setBusy(false);
    }
  };

  const revise = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!current || !feedback.trim() || busy) return;
    setBusy(true);
    setNotice("");
    try {
      const value = await api<DisplayVersion | DisplayQuestion>(
        `/api/v1/display-tasks/${current.task_id}/revisions`,
        { method: "POST", body: JSON.stringify({ feedback: feedback.trim() }) }
      );
      await accept(value);
      if (isVersion(value)) setFeedback("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "这次修改没有生成，原方案仍保留。");
    } finally {
      setBusy(false);
    }
  };

  const openRecent = async (item: RecentDisplay): Promise<void> => {
    setBusy(true);
    setNotice("");
    try {
      const value = await api<DisplayVersion>(
        `/api/v1/display-tasks/${item.task_id}/versions/${item.version}`
      );
      setCurrent(value);
      setViewed(value);
      await loadVersions(value);
      setMobileView("plan");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "无法打开这份方案。");
    } finally {
      setBusy(false);
    }
  };

  const copy = async (): Promise<void> => {
    if (!viewed) return;
    try {
      await navigator.clipboard.writeText(viewed.body);
      setNotice(`已复制 V${viewed.version}。`);
    } catch {
      setNotice("没有复制成功，请允许浏览器访问剪贴板后再试。");
    }
  };

  const historical = versions.filter(item => item.version_id !== current?.version_id);
  const identity = context.identity ?? {};
  return (
    <div className="display-shell">
      <header className="display-topbar">
        <a href="/user" aria-label="返回工作首页">
          <BrandMark compact />
        </a>
        <span>
          <strong>{identity.account ?? "当前门店账号"}</strong>
          <small>{identity.content_role ?? "陈列搭配"}</small>
        </span>
        <form method="post" action="/tenant-admin/logout?next=user">
          <button className="quiet" type="submit">退出</button>
        </form>
      </header>
      <div className="display-app">
      <aside className="display-history" aria-label="陈列方案历史">
        <button
          className="new-display"
          type="button"
          onClick={() => {
            setCurrent(null);
            setViewed(null);
            setVersions([]);
            setFeedback("");
            setMobileView("conversation");
          }}
        >
          ＋ 新方案
        </button>
        <p>最近方案</p>
        <nav>
          {recent.length === 0 ? <span>还没有方案</span> : recent.map(item => (
            <button
              key={item.version_id}
              type="button"
              className={current?.task_id === item.task_id ? "active" : ""}
              onClick={() => void openRecent(item)}
            >
              <strong>{item.title}</strong>
              <small>V{item.version}</small>
            </button>
          ))}
        </nav>
      </aside>

      <main className={`display-conversation ${mobileView === "plan" ? "mobile-hidden" : ""}`}>
        <header className="display-heading">
          <p className="eyebrow">陈列搭配</p>
          <h1>说清这组墙现在有什么。</h1>
          <p>按商品编号和数量写下来，就能得到一份可执行的文字参考方案。</p>
        </header>
        {notice && <p className="user-path-notice" role="status">{notice}</p>}
        {!current ? (
          <form className="display-composer" onSubmit={event => void create(event)}>
            <fieldset className="display-product-picker">
              <legend>本店当前可用商品</legend>
              {products.length === 0 ? (
                <p>还没有可用于本店的正式商品，请联系品牌管理员补充。</p>
              ) : (
                products.map(product => (
                  <button
                    key={product.product_version_id}
                    type="button"
                    className="text-action"
                    onClick={() => addProduct(product)}
                  >
                    添加 {product.display_name}（{product.sku}）
                  </button>
                ))
              )}
            </fieldset>
            <label htmlFor="display-inventory">本次库存</label>
            <textarea
              id="display-inventory"
              value={inventory}
              onChange={event => setInventory(event.target.value)}
              placeholder="例如：今天这组墙可用：商品编号 3 件、商品编号 2 件。"
              maxLength={2000}
            />
            <button className="primary" type="submit" disabled={!inventory.trim() || busy}>
              {busy ? "正在整理方案……" : "生成参考方案"}
            </button>
          </form>
        ) : (
          <div className="display-followup">
            <p>当前方案在右侧。想改局部位置时，直接说明哪件商品、哪一侧和哪根挂杆受影响。</p>
            <button className="text-action" type="button" onClick={() => setMobileView("plan")}>
              阅读当前方案
            </button>
          </div>
        )}
      </main>

      <aside className={`display-artifact ${mobileView === "conversation" ? "mobile-hidden" : ""}`} aria-label="文字参考方案">
        {!viewed ? (
          <div className="display-empty"><h2>方案会出现在这里</h2><p>生成后可以完整阅读、复制，或用自然语言只改受影响的位置。</p></div>
        ) : (
          <>
            <header className="display-artifact-heading">
              <div>
                <p className="eyebrow">{viewed.version_id === current?.version_id ? "当前版本" : "历史版本"} · V{viewed.version}</p>
                <h2>墙面挂杆参考方案</h2>
              </div>
              <button type="button" onClick={() => void copy()}>复制</button>
            </header>
            {viewed.version_id !== current?.version_id && current && (
              <p className="history-reading">正在阅读 V{viewed.version}；<button type="button" onClick={() => setViewed(current)}>回到当前版</button></p>
            )}
            <PlanText body={viewed.body} />
            {historical.length > 0 && (
              <details className="display-version-history">
                <summary>历史版本（{historical.length}）</summary>
                {historical.map(item => <button key={item.version_id} type="button" onClick={() => setViewed(item)}>阅读 V{item.version}</button>)}
              </details>
            )}
            <form className="display-revision" onSubmit={event => void revise(event)}>
              <label htmlFor="display-feedback">这次只想改什么？</label>
              <textarea
                id="display-feedback"
                value={feedback}
                onChange={event => setFeedback(event.target.value)}
                placeholder="例如：中间上杆的某件商品少一件，其余保持不动。"
                maxLength={2000}
              />
              <button className="primary" type="submit" disabled={!feedback.trim() || busy || viewed.version_id !== current?.version_id}>
                {busy ? "正在更新……" : `生成 V${(current?.version ?? 0) + 1}`}
              </button>
            </form>
          </>
        )}
      </aside>

      <nav className="display-mobile-tabs" aria-label="工作面切换">
        <button type="button" className={mobileView === "conversation" ? "active" : ""} onClick={() => setMobileView("conversation")}>对话</button>
        <button type="button" className={mobileView === "plan" ? "active" : ""} onClick={() => setMobileView("plan")}>方案</button>
      </nav>
      </div>
    </div>
  );
}
