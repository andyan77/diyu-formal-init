import { useEffect, useState } from "react";
import type { ChangeEvent, FormEvent, JSX } from "react";
import { BrandMark } from "../components/Brand";
import { api } from "../services/api";
import "../styles/user-extensions.css";
import "../styles/tenant-admin.css";
import type { BootstrapContext } from "./types";

type OrganizationMaterial = {
  id: string;
  title: string;
  media_type: string;
  status: "active" | "inactive" | string;
  reference_note: string;
  reference_version: number;
  organization_id: string;
  organization: string;
};

type MaterialVersion = {
  id: string;
  version: number;
  title: string;
  reference_note: string;
  is_current: boolean;
  created_at: string;
};

async function filePayload(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("无法读取这份素材。"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.readAsDataURL(file);
  });
}

export default function OrganizationMaterialsApp({
  context
}: {
  context: BootstrapContext;
}): JSX.Element {
  const [materials, setMaterials] = useState<OrganizationMaterial[]>([]);
  const [versions, setVersions] = useState<MaterialVersion[]>([]);
  const [selected, setSelected] = useState<OrganizationMaterial | null>(null);
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [minor, setMinor] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const reload = async (): Promise<void> => {
    const next = await api<OrganizationMaterial[]>("/api/v1/user/organization-materials");
    setMaterials(next);
    if (selected) {
      setSelected(next.find(item => item.id === selected.id) ?? null);
    }
  };

  useEffect(() => {
    void reload().catch(error => {
      setNotice(error instanceof Error ? error.message : "暂时无法读取组织素材。");
    });
  }, []);

  const chooseFile = (event: ChangeEvent<HTMLInputElement>): void => {
    setFile(event.target.files?.[0] ?? null);
  };

  const upload = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!file || !title.trim() || busy) return;
    setBusy(true);
    setNotice("");
    try {
      await api("/api/v1/user/organization-materials", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          filename: file.name,
          content_type: file.type || "application/octet-stream",
          content_base64: await filePayload(file),
          declares_identifiable_minor: minor,
          reference_note: note.trim()
        })
      });
      setTitle("");
      setNote("");
      setFile(null);
      setMinor(false);
      await reload();
      setNotice("组织素材已保存；只有用户在某次创作中明确选择时才会使用。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "组织素材没有保存成功。");
    } finally {
      setBusy(false);
    }
  };

  const open = async (item: OrganizationMaterial): Promise<void> => {
    setSelected(item);
    setTitle(item.title);
    setNote(item.reference_note);
    try {
      setVersions(
        await api<MaterialVersion[]>(
          `/api/v1/user/organization-materials/${item.id}/versions`
        )
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "暂时无法读取历史版本。");
    }
  };

  const saveVersion = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!selected || !title.trim() || !note.trim() || busy) return;
    setBusy(true);
    try {
      await api(`/api/v1/user/organization-materials/${selected.id}/versions`, {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          reference_note: note.trim(),
          visibility_scope: "organizations",
          organization_ids: [selected.organization_id]
        })
      });
      await reload();
      await open({ ...selected, title: title.trim(), reference_note: note.trim() });
      setNotice("已保存一个新的说明版本，旧版本仍可查看。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "新版本没有保存成功。");
    } finally {
      setBusy(false);
    }
  };

  const setEnabled = async (item: OrganizationMaterial): Promise<void> => {
    setBusy(true);
    try {
      await api(`/api/v1/user/organization-materials/${item.id}/enabled`, {
        method: "PUT",
        body: JSON.stringify({ enabled: item.status !== "active" })
      });
      await reload();
      setNotice(item.status === "active" ? "已停用；新任务不会再看到这份素材。" : "素材已恢复。" );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "素材状态没有更新成功。");
    } finally {
      setBusy(false);
    }
  };

  const identity = context.identity ?? {};
  return (
    <main className="user-home organization-materials-page">
      <header>
        <BrandMark />
        <a className="button quiet" href="/user">返回工作台</a>
      </header>
      <section>
        <p className="eyebrow">{identity.organization ?? "所属团队"}</p>
        <h1>维护组织官方素材</h1>
        <p>这里的原件只属于当前团队；创作用户仍需在每次任务中主动选择。</p>
        {notice && <p className="user-path-notice" role="status">{notice}</p>}
        <form className="material-upload-form" onSubmit={event => void upload(event)}>
          <label>素材名称<input value={selected ? "" : title} disabled={Boolean(selected)} onChange={event => setTitle(event.target.value)} maxLength={120} /></label>
          <label>原件<input type="file" disabled={Boolean(selected)} accept="text/plain,.txt,.md,.csv,image/*,video/*" onChange={chooseFile} /></label>
          <label>人工说明<textarea value={selected ? "" : note} disabled={Boolean(selected)} onChange={event => setNote(event.target.value)} maxLength={500} /></label>
          <label><input type="checkbox" disabled={Boolean(selected)} checked={minor} onChange={event => setMinor(event.target.checked)} />原件中有可识别的未成年人</label>
          <button className="primary" type="submit" disabled={Boolean(selected) || busy || !file || !title.trim()}>保存组织素材</button>
        </form>
        <section className="material-zone" aria-labelledby="organization-material-list">
          <h2 id="organization-material-list">当前团队素材</h2>
          {materials.length === 0 ? <p>还没有组织官方素材。</p> : <ul>{materials.map(item => (
            <li key={item.id}>
              <div><strong>{item.title}</strong><small>{item.organization} · V{item.reference_version} · {item.status === "active" ? "使用中" : "已停用"}</small></div>
              <span><button type="button" onClick={() => void open(item)}>查看与修改</button><button type="button" disabled={busy} onClick={() => void setEnabled(item)}>{item.status === "active" ? "停用" : "恢复"}</button></span>
            </li>
          ))}</ul>}
        </section>
      </section>
      {selected && <section className="tenant-drawer" role="dialog" aria-modal="true" aria-label="素材详情">
        <button type="button" aria-label="关闭" onClick={() => { setSelected(null); setVersions([]); setTitle(""); setNote(""); }}>×</button>
        <form className="tenant-form" onSubmit={event => void saveVersion(event)}>
          <h2>{selected.title}</h2>
          <label>素材名称<input value={title} onChange={event => setTitle(event.target.value)} maxLength={120} /></label>
          <label>人工说明<textarea value={note} onChange={event => setNote(event.target.value)} maxLength={500} /></label>
          <button className="primary" type="submit" disabled={busy || !title.trim() || !note.trim()}>保存新版本</button>
        </form>
        <section><h3>历史版本</h3><ul>{versions.map(version => <li key={version.id}>V{version.version}{version.is_current ? " · 当前" : ""} · {version.title}</li>)}</ul></section>
      </section>}
    </main>
  );
}
