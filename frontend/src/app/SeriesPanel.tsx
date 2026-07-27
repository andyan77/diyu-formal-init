import { useEffect, useState } from "react";
import type { FormEvent, JSX } from "react";
import { api } from "../services/api";
import "../styles/user-extensions.css";
import type { Target } from "./types";

export type SeriesItem = {
  task_id: string;
  position: number;
  title: string;
};

export type ContentSeries = {
  id: string;
  title: string;
  premise: string;
  revision: number;
  items: SeriesItem[];
};

export type SeriesSelection = {
  seriesId: string;
  position?: number;
};

export function SeriesPanel({
  selected,
  onSelect,
  onContinue,
  onOpenTask,
  target
}: {
  selected: SeriesSelection | null;
  onSelect: (value: SeriesSelection | null) => void;
  onContinue: (value: SeriesSelection) => void;
  onOpenTask?: (taskId: string) => void;
  target: Target;
}): JSX.Element {
  const [series, setSeries] = useState<ContentSeries[]>([]);
  const [title, setTitle] = useState("");
  const [premise, setPremise] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = async (): Promise<void> => {
    try {
      setSeries(
        await api<ContentSeries[]>(
          `/api/v1/content/series?target=${encodeURIComponent(target)}`
        )
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "暂时无法读取连续系列。");
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  const create = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!title.trim() || busy) return;
    setBusy(true);
    setNotice("");
    try {
      const value = await api<ContentSeries>(
        `/api/v1/content/series?target=${encodeURIComponent(target)}`,
        {
        method: "POST",
        body: JSON.stringify({ title: title.trim(), premise: premise.trim() })
        }
      );
      setTitle("");
      setPremise("");
      onSelect({ seriesId: value.id });
      await reload();
      setNotice(`已建立《${value.title}》，下一篇可以从这里开始。`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "没有建立成功。");
    } finally {
      setBusy(false);
    }
  };

  const move = async (item: ContentSeries, from: number, to: number): Promise<void> => {
    const next = [...item.items];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setBusy(true);
    setNotice("");
    try {
      await api<ContentSeries>(
        `/api/v1/content/series/${item.id}/items?target=${encodeURIComponent(target)}`,
        {
          method: "PUT",
          body: JSON.stringify({ task_ids: next.map(entry => entry.task_id) })
        }
      );
      await reload();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "这次调整没有保存。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="series-panel" aria-label="连续系列">
      <header>
        <p className="eyebrow">连续系列</p>
        <h2>让下一篇接住前一篇。</h2>
        <p>选择后才会把这个系列的必要前情带进新内容；阅读、复制和导出不会改变系列。</p>
      </header>
      {notice && <p className="user-path-notice" role="status">{notice}</p>}
      <form className="series-create-form" onSubmit={event => void create(event)}>
        <label htmlFor="series-title">新系列名称</label>
        <input id="series-title" value={title} onChange={event => setTitle(event.target.value)} maxLength={100} placeholder="例如：门店里的安静时刻" />
        <label htmlFor="series-premise">想持续谈什么？（可选）</label>
        <textarea id="series-premise" value={premise} onChange={event => setPremise(event.target.value)} maxLength={500} placeholder="用一句话写下这组内容想继续的判断。" />
        <button className="primary" type="submit" disabled={!title.trim() || busy}>{busy ? "正在建立……" : "建立系列"}</button>
      </form>
      <div className="series-list">
        {series.length === 0 && <p className="series-empty">还没有系列。新建后，可以直接从第一篇开始。</p>}
        {series.map(item => {
          const isSelected = selected?.seriesId === item.id;
          return (
            <article key={item.id} className={isSelected ? "series-entry selected" : "series-entry"}>
              <div className="series-entry-heading">
                <div>
                  <p className="eyebrow">{item.items.length} 篇 · 编排 V{item.revision}</p>
                  <h3>{item.title}</h3>
                  {item.premise && <p>{item.premise}</p>}
                </div>
                <button type="button" className="text-action" onClick={() => onSelect(isSelected ? null : { seriesId: item.id })}>
                  {isSelected ? "本次不承接" : "用于这次创作"}
                </button>
              </div>
              <div className="series-actions">
                <button type="button" onClick={() => onContinue({ seriesId: item.id })}>接着做下一篇</button>
                <label>
                  放到第几篇
                  <input
                    type="number"
                    min={1}
                    max={999}
                    value={isSelected && selected?.position ? selected.position : ""}
                    onChange={event => {
                      const position = event.target.value ? Number(event.target.value) : undefined;
                      onSelect({ seriesId: item.id, position });
                    }}
                  />
                </label>
              </div>
              {item.items.length > 0 && (
                <ol>
                  {item.items.map((entry, index) => (
                    <li key={entry.task_id}>
                      <button
                        className="series-item-open"
                        type="button"
                        onClick={() => onOpenTask?.(entry.task_id)}
                      >
                        第 {entry.position} 篇 · {entry.title}
                      </button>
                      <span>
                        <button type="button" disabled={busy || index === 0} onClick={() => void move(item, index, index - 1)}>上移</button>
                        <button type="button" disabled={busy || index === item.items.length - 1} onClick={() => void move(item, index, index + 1)}>下移</button>
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
