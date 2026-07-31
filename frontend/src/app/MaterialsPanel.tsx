import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, FormEvent, JSX } from "react";
import { api, scopedContentPath } from "../services/api";
import type { Target } from "./types";
import "../styles/user-extensions.css";

export type ReferenceMaterial = {
  id: string;
  title: string;
  media_type: string;
  scope: "personal" | "organization";
  created_at: string;
  status: string;
  reference_note?: string;
  product_media?: Array<{
    binding_id: string;
    product_id: string;
    sku: string;
    product_name: string;
    product_version: number;
  }>;
};

async function filePayload(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("无法读取这份素材。"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.readAsDataURL(file);
  });
}

function isReadable(item: ReferenceMaterial): boolean {
  return item.media_type === "text" || Boolean(item.reference_note?.trim());
}

export function MaterialPicker({
  materials,
  selectedIds,
  onSelectedIdsChange,
  onWriteNote
}: {
  materials: ReferenceMaterial[];
  selectedIds: string[];
  onSelectedIdsChange: (value: string[]) => void;
  onWriteNote: (item: ReferenceMaterial) => void;
}): JSX.Element {
  if (materials.length === 0) return <p className="material-picker-empty">本次不参考素材也可以继续创作。</p>;
  return (
    <fieldset className="material-picker">
      <legend>本次参考（可选）</legend>
      <p className="material-picker-help">
        选择两份已关联商品的组织素材时，先选的是主视觉，后选的是辅助视觉。
      </p>
      {materials.map(item => {
        const readable = isReadable(item);
        const checked = selectedIds.includes(item.id);
        const selectedPosition = selectedIds.indexOf(item.id);
        const visualRole =
          checked && (item.product_media ?? []).length > 0
            ? selectedPosition === 0
              ? "主视觉"
              : selectedPosition === 1
                ? "辅助视觉"
                : "普通参考"
            : "";
        return (
          <label key={item.id} className={readable ? "" : "needs-note"}>
            <input
              type="checkbox"
              checked={checked}
              disabled={!readable}
              onChange={event => onSelectedIdsChange(event.target.checked ? [...selectedIds, item.id] : selectedIds.filter(id => id !== item.id))}
            />
            <span>
              <strong>{item.title}</strong>
              <small>
                {item.scope === "personal" ? "我的素材" : "组织素材"}
                {readable ? "" : " · 先补一句说明"}
                {(item.product_media ?? []).map(
                  product =>
                    ` · 已关联 ${product.product_name}（${product.sku}）`
                )}
                {visualRole ? ` · ${visualRole}` : ""}
              </small>
            </span>
            {!readable && item.scope === "personal" && <button type="button" className="text-action" onClick={event => { event.preventDefault(); onWriteNote(item); }}>补说明</button>}
          </label>
        );
      })}
    </fieldset>
  );
}

export function MaterialsPanel({
  selectedIds = [],
  onSelectedIdsChange = () => undefined,
  publishingIdentityId = "current",
  target = "douyin_video"
}: {
  selectedIds?: string[];
  onSelectedIdsChange?: (value: string[]) => void;
  publishingIdentityId?: string;
  target?: Target;
}): JSX.Element {
  const [materials, setMaterials] = useState<ReferenceMaterial[]>([]);
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [minor, setMinor] = useState(false);
  const [editing, setEditing] = useState<ReferenceMaterial | null>(null);
  const [editingNote, setEditingNote] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = async (): Promise<void> => {
    try {
      setMaterials(
        await api<ReferenceMaterial[]>(
          scopedContentPath("/api/v1/materials", publishingIdentityId, target)
        )
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "暂时无法读取素材。");
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  const upload = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!file || !title.trim() || busy) return;
    setBusy(true);
    setNotice("");
    try {
      await api<ReferenceMaterial>(
        scopedContentPath("/api/v1/materials/personal", publishingIdentityId, target),
        {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          filename: file.name,
          content_type: file.type || "application/octet-stream",
          content_base64: await filePayload(file),
          declares_identifiable_minor: minor,
          reference_note: note.trim()
        })
        }
      );
      setTitle("");
      setNote("");
      setFile(null);
      setMinor(false);
      await reload();
      setNotice("已保存。只有你在本次创作中主动选择时，它才会被参考。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "这份素材没有保存成功。");
    } finally {
      setBusy(false);
    }
  };

  const saveNote = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!editing || editingNote.trim().length < 2 || busy) return;
    setBusy(true);
    try {
      await api<ReferenceMaterial>(
        scopedContentPath(
          `/api/v1/materials/${editing.id}/reference-note`,
          publishingIdentityId,
          target
        ),
        {
          method: "PATCH",
          body: JSON.stringify({ reference_note: editingNote.trim() })
        }
      );
      setEditing(null);
      setEditingNote("");
      await reload();
      setNotice("这句说明已经保存，现在可以把它选进本次参考。 ");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "这句说明没有保存成功。");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (item: ReferenceMaterial): Promise<void> => {
    if (busy || !window.confirm(`移除《${item.title}》？`)) return;
    setBusy(true);
    try {
      await api<{ deleted: boolean }>(
        scopedContentPath(`/api/v1/materials/${item.id}`, publishingIdentityId, target),
        { method: "DELETE" }
      );
      onSelectedIdsChange(selectedIds.filter(id => id !== item.id));
      await reload();
      setNotice("已移除这份素材。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "暂时无法移除这份素材。");
    } finally {
      setBusy(false);
    }
  };

  const personal = useMemo(() => materials.filter(item => item.scope === "personal"), [materials]);
  const organization = useMemo(() => materials.filter(item => item.scope === "organization"), [materials]);
  const chooseFile = (event: ChangeEvent<HTMLInputElement>): void => setFile(event.target.files?.[0] ?? null);

  const materialList = (
    heading: string,
    items: ReferenceMaterial[],
    editable: boolean
  ): JSX.Element => (
    <section className="material-zone">
      <h3>{heading}</h3>
      {items.length === 0 ? <p>还没有素材。</p> : <ul>{items.map(item => (
        <li key={item.id}>
          <div>
            <strong>{item.title}</strong>
            <small>
              {item.media_type === "text"
                ? "文字原件"
                : item.media_type === "image"
                  ? "图片原件"
                  : "视频原件"}
              {isReadable(item) ? " · 已有说明" : " · 还缺说明"}
              {(item.product_media ?? []).map(
                product =>
                  ` · ${product.product_name}（${product.sku}）`
              )}
            </small>
          </div>
          {editable && <span><button type="button" onClick={() => { setEditing(item); setEditingNote(item.reference_note ?? ""); }}>写说明</button><button type="button" onClick={() => void remove(item)}>移除</button></span>}
        </li>
      ))}</ul>}
    </section>
  );

  return (
    <section className="materials-panel" aria-label="素材">
      <header><p className="eyebrow">素材</p><h2>只带上你这次想参考的内容。</h2><p>图片和视频只依照你写下的说明参与文字创作。</p></header>
      {notice && <p className="user-path-notice" role="status">{notice}</p>}
      <div className="material-zones">{materialList("我的素材", personal, true)}{materialList("组织素材", organization, false)}</div>
      {!editing && <form className="material-upload-form" onSubmit={event => void upload(event)}>
        <p className="eyebrow">添加到我的素材</p>
        <label>素材名称<input value={title} onChange={event => setTitle(event.target.value)} maxLength={120} /></label>
        <label>原件<input type="file" accept="text/plain,.txt,.md,.csv,image/*,video/*" onChange={chooseFile} /></label>
        <label>这份原件里有什么值得参考？<textarea value={note} onChange={event => setNote(event.target.value)} maxLength={500} placeholder="图片或视频请先写一句人工说明。" /></label>
        <label className="material-minor"><input type="checkbox" checked={minor} onChange={event => setMinor(event.target.checked)} />我已知其中有可识别的未成年人</label>
        <button className="primary" type="submit" disabled={busy || !title.trim() || !file}>{busy ? "正在保存……" : "保存素材"}</button>
      </form>}
      {editing && <form className="material-note-form" onSubmit={event => void saveNote(event)}><h3>给《{editing.title}》补一句说明</h3><textarea value={editingNote} onChange={event => setEditingNote(event.target.value)} maxLength={500} autoFocus /><div><button className="primary" type="submit" disabled={busy || editingNote.trim().length < 2}>保存说明</button><button type="button" onClick={() => setEditing(null)}>取消</button></div></form>}
      <MaterialPicker materials={materials} selectedIds={selectedIds} onSelectedIdsChange={onSelectedIdsChange} onWriteNote={item => { setEditing(item); setEditingNote(item.reference_note ?? ""); }} />
    </section>
  );
}
