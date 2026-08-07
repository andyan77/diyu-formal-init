import { useEffect, useRef, useState } from "react";
import type {
  FormEvent,
  JSX,
  KeyboardEvent as ReactKeyboardEvent
} from "react";

import { api } from "../../services/api";
import type {
  AccountExpression,
  AccountExpressionProfileFields,
  BootstrapContext,
  CreationPreference,
  PublishingIdentity
} from "../../app/types";
import type { AdvisorScopeTransaction } from "./useAdvisorScope";

/**
 * The account drawer: who this account is, and the two settings its owner may
 * change from inside the workspace.
 *
 * Lifted out of CreatorApp unchanged in EXE-01R. It is self-contained — its
 * only reach into the workspace is the two callbacks — and moving it keeps the
 * file it came from from growing while that file gains scope guards.
 */

export function editableAccountProfile(
  value:
    | AccountExpression["current"]
    | AccountExpression["draft"]
    | null
    | undefined
): AccountExpressionProfileFields | null {
  return value
    ? {
        identity_position: value.identity_position,
        authority_boundary: value.authority_boundary,
        audience_relationship: value.audience_relationship,
        content_territories: value.content_territories,
        default_production_conditions: value.default_production_conditions
      }
    : null;
}

export function AccountDrawer({
  context,
  publishingIdentity,
  preferencePath,
  preference,
  profile,
  profilePath,
  onClose,
  onPreference,
  onProfile,
  begin
}: {
  context: BootstrapContext;
  publishingIdentity: PublishingIdentity;
  preferencePath: string;
  preference: CreationPreference | null;
  profile: AccountExpression | null;
  profilePath: string;
  onClose: () => void;
  onPreference: (value: CreationPreference) => void;
  onProfile: (value: AccountExpression) => void;
  /** Both saves here write the parent's state, so both need a scope guard. */
  begin: () => AdvisorScopeTransaction;
}): JSX.Element {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileDraft, setProfileDraft] =
    useState<AccountExpressionProfileFields | null>(
      editableAccountProfile(profile?.current ?? profile?.draft)
    );
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);
  useEffect(() => {
    setProfileDraft(
      editableAccountProfile(profile?.current ?? profile?.draft)
    );
    setEditingProfile(false);
  }, [profile]);

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLElement>): void => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      panelRef.current?.querySelectorAll<HTMLElement>(
        "a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)"
      ) ?? []
    );
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const toggleBodyDirections = async (): Promise<void> => {
    if (!preference || saving) return;
    const txn = begin();
    setSaving(true);
    setError("");
    try {
      const next = await api<CreationPreference>(preferencePath, {
        method: "PUT",
        signal: txn.signal,
        body: JSON.stringify({
          enabled: preference.enabled,
          direction_defaults: preference.direction_defaults,
          clear_direction_defaults: false,
          collaboration_note: preference.collaboration_note,
          body_related_opt_in: !preference.body_related_opt_in
        })
      });
      if (!txn.live()) return;
      onPreference(next);
    } catch (reason) {
      if (!txn.live()) return;
      setError(reason instanceof Error ? reason.message : "没有保存成功。");
    } finally {
      if (txn.live()) setSaving(false);
    }
  };
  const saveProfile = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!profile?.can_maintain || !profileDraft || saving) return;
    const txn = begin();
    setSaving(true);
    setError("");
    try {
      const saved = await api<NonNullable<AccountExpression["current"]>>(
        profilePath,
        {
        method: "POST",
        signal: txn.signal,
        body: JSON.stringify(profileDraft)
        }
      );
      if (!txn.live()) return;
      onProfile({ ...profile, current: saved, draft: null });
      setEditingProfile(false);
    } catch (reason) {
      if (!txn.live()) return;
      setError(
        reason instanceof Error
          ? reason.message
          : "账号画像没有保存成功。"
      );
    } finally {
      if (txn.live()) setSaving(false);
    }
  };
  const identity = context.identity ?? {};
  return (
    <div className="drawer-layer" role="presentation" onMouseDown={onClose}>
      <aside
        ref={panelRef}
        className="account-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-drawer-title"
        onMouseDown={event => event.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <header>
          <div>
            <p className="eyebrow">当前发布身份</p>
            <h2 id="account-drawer-title">{publishingIdentity.name}</h2>
          </div>
          <button
            ref={closeRef}
            className="icon-button"
            type="button"
            aria-label="关闭"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <dl className="identity-details">
          <div>
            <dt>表达身份</dt>
            <dd>{publishingIdentity.content_role || identity.content_role || "—"}</dd>
          </div>
          <div>
            <dt>负责团队</dt>
            <dd>{publishingIdentity.control_organization ?? "—"}</dd>
          </div>
          <div>
            <dt>账号画像</dt>
            <dd>
              {publishingIdentity.profile_version
                ? `V${publishingIdentity.profile_version}`
                : "尚未确认"}
            </dd>
          </div>
        </dl>
        <p className="profile-one-line">{publishingIdentity.profile_summary}</p>
        {profile?.current && !editingProfile && (
          <section className="profile-summary">
            <h3>账号定位 · V{profile.current.version}</h3>
            <p>{profile.current.identity_position}</p>
            <p>{profile.current.authority_boundary}</p>
            <p>{profile.current.audience_relationship}</p>
            <p>{profile.current.content_territories}</p>
            <p>{profile.current.default_production_conditions}</p>
            {profile.can_maintain && (
              <button
                type="button"
                className="text-action"
                onClick={() => setEditingProfile(true)}
              >
                维护账号画像
              </button>
            )}
          </section>
        )}
        {profile?.can_maintain && editingProfile && profileDraft && (
          <form className="account-profile-editor" onSubmit={event => void saveProfile(event)}>
            <h3>
              基于当前 V{profile.current?.version ?? 0} 保存新版本
            </h3>
            {(
              [
                ["identity_position", "表达身份"],
                ["authority_boundary", "权威边界"],
                ["audience_relationship", "受众关系"],
                ["content_territories", "内容领地"],
                ["default_production_conditions", "长期制作条件"]
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <textarea
                  required
                  value={profileDraft[key]}
                  onChange={event =>
                    setProfileDraft(value =>
                      value
                        ? { ...value, [key]: event.target.value }
                        : value
                    )
                  }
                />
              </label>
            ))}
            <div className="drawer-actions">
              <button
                type="button"
                onClick={() => {
                  setProfileDraft(
                    editableAccountProfile(
                      profile.current ?? profile.draft
                    )
                  );
                  setEditingProfile(false);
                  setError("");
                }}
              >
                取消
              </button>
              <button className="primary" type="submit" disabled={saving}>
                {saving
                  ? "正在保存……"
                  : `保存为 V${(profile.current?.version ?? 0) + 1}`}
              </button>
            </div>
          </form>
        )}
        {profile && !profile.can_maintain && (
          <p className="profile-read-only">
            你可以查看完整账号画像；维护资格由账号负责团队单独分配。
          </p>
        )}
        {error && <p className="inline-error">{error}</p>}
        {preference && (
          <section className="personal-controls">
            <h3>我的创作偏好</h3>
            <label className="switch-line">
              <span>
                主动显示体型相关方向
                <small>只有你打开后才出现，系统不会自行推断。</small>
              </span>
              <input
                type="checkbox"
                checked={preference.body_related_opt_in}
                disabled={saving}
                onChange={() => void toggleBodyDirections()}
              />
            </label>
          </section>
        )}
      </aside>
    </div>
  );
}
