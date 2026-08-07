import type { JSX } from "react";
import type { FormalCapabilityMatrix, UsageGuideTruth } from "../app/types";

const dataLabels = {
  satisfied: "资料满足",
  partial: "部分资料",
  missing: "资料缺失",
  not_required: "无需资料"
} as const;

const permissionLabels = {
  granted: "本人获权",
  not_granted: "本人未获权",
  not_applicable: "当前不适用"
} as const;

const countLabels: Record<string, string> = {
  source_documents: "来源文档总数",
  authorized_source_documents: "品牌已授权来源文档",
  template_documents: "仅补录模板文档",
  source_segments: "不可变来源 segments",
  publication_version: "当前正式发布投影版本",
  publication_items: "当前正式发布投影条目",
  publication_source_bound_items: "来源绑定可消费条目",
  publication_brand_facts: "已发布品牌事实",
  publication_expression_constraints: "已发布表达边界",
  publication_creative_methods: "已发布创作方法",
  formal_users: "正式用户",
  content_users: "正式内容用户",
  logical_accounts: "逻辑发布账号",
  platform_targets: "平台与形式目标",
  profile_accounts: "已确认五段画像账号",
  active_products: "正式 active 商品",
  allowed_product_fact_fields: "可进入 ProductFact 的字段证据",
  organization_media: "正式组织官方素材",
  product_media_products: "具备媒体绑定的商品",
  confirmed_stores: "正式门店档案",
  formal_inventory_snapshots: "正式库存快照"
};

export function CapabilityMatrixView({
  matrix
}: {
  matrix: FormalCapabilityMatrix;
}): JSX.Element {
  return (
    <section className="capability-matrix" aria-labelledby="capability-matrix-title">
      <header>
        <div>
          <p className="eyebrow">58 项正式支持面</p>
          <h3 id="capability-matrix-title">四列真值矩阵</h3>
        </div>
        <p>
          软件实现 {matrix.summary.implemented} 项 · 资料满足或无需资料 {matrix.summary.data_satisfied} 项 ·
          当前身份获权 {matrix.summary.permission_granted} 项 · 同一候选正式实测 {matrix.summary.formally_tested} 项
        </p>
      </header>
      <div className="capability-table-wrap" tabIndex={0} aria-label="正式能力真值表，可横向滚动">
        <table>
          <thead>
            <tr>
              <th scope="col">能力</th>
              <th scope="col">软件是否实现</th>
              <th scope="col">当前资料是否满足</th>
              <th scope="col">当前用户是否获权</th>
              <th scope="col">正式生产是否实测</th>
              <th scope="col">补充入口</th>
            </tr>
          </thead>
          <tbody>
            {matrix.items.map(item => (
              <tr key={item.id}>
                <th scope="row">
                  <span>{item.id}</span>
                  {item.title}
                  <small>{item.role} · {item.route}</small>
                </th>
                <td>{item.software_implemented ? "已实现" : "未实现"}</td>
                <td>{dataLabels[item.data_state]}</td>
                <td>{permissionLabels[item.permission_state]}</td>
                <td>{item.formally_tested ? "已实测" : "尚未实测"}</td>
                <td><a href={item.supplement_href}>去补充</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <footer>
        <span>运行 SHA：{matrix.runtime_sha}</span>
        <span>Schema：{matrix.schema_revision}</span>
        <span>生成时间：{matrix.generated_at}</span>
      </footer>
    </section>
  );
}

export function UsageGuideView({ guide }: { guide: UsageGuideTruth }): JSX.Element {
  const gaps = guide.data_missing.filter(item => item.missing);
  return (
    <section className="usage-guide" aria-labelledby="usage-guide-title">
      <header>
        <p className="eyebrow">笛语服饰使用说明</p>
        <h3 id="usage-guide-title">身份、工作步骤与当前资料真值</h3>
      </header>
      <div className="usage-guide-grid">
        <section>
          <h4>三种身份</h4>
          <ul>{guide.identity_model.map(item => <li key={item}>{item}</li>)}</ul>
          <p className="relationship-line">{guide.relationship}</p>
        </section>
        <section>
          <h4>发送与生成内容</h4>
          <p>{guide.send_vs_generate.send}</p>
          <p>{guide.send_vs_generate.generate}</p>
        </section>
        <section>
          <h4>管理员从零建立成员</h4>
          <ol>{guide.administrator_steps.map(item => <li key={item}>{item}</li>)}</ol>
          <ul>{guide.named_member_examples.map(item => <li key={item}>{item}</li>)}</ul>
        </section>
        <section>
          <h4>一次性陈述与可复用事实</h4>
          <ul>{guide.truth_boundaries.map(item => <li key={item}>{item}</li>)}</ul>
        </section>
      </div>
      <section>
        <h4>当前品牌资料怎样进入创作</h4>
        <p>{guide.brand_context_summary.message}</p>
      </section>
      <section>
        <h4>当前数据库实测数量</h4>
        <dl className="guide-counts">
          {Object.entries(guide.current_counts).map(([key, value]) => (
            <div key={key}><dt>{countLabels[key] ?? key}</dt><dd>{value}</dd></div>
          ))}
        </dl>
      </section>
      <section>
        <h4>P2：按 SKU 查看当前商品事实边界</h4>
        <p>这里只展示可进入 ProductFact 的已确认字段；候选分析文字和未达可信等级的内容不会作为事实展示或发送给 Writer。</p>
        <div className="product-fact-readiness">
          {guide.product_fact_readiness.map(product => (
            <details key={product.sku}>
              <summary>{product.sku} · {product.display_name}</summary>
              <p>{product.can_do}</p>
              <dl>
                {product.current_facts.length === 0 ? (
                  <div><dt>当前可用事实</dt><dd>无</dd></div>
                ) : product.current_facts.map(fact => (
                  <div key={fact.field}><dt>{fact.field}</dt><dd>{fact.value}</dd></div>
                ))}
              </dl>
              <p><strong>尚缺字段：</strong>{product.missing_fields.join("、") || "无"}</p>
              <p><strong>不能承诺：</strong>{product.cannot_promise}</p>
            </details>
          ))}
        </div>
      </section>
      <section>
        <h4>当前资料缺口</h4>
        {gaps.length === 0 ? <p>当前未发现 P4、P5 或 DM01 资料缺口。</p> : (
          <ul className="guide-gaps">
            {gaps.map(item => (
              <li key={item.id}>
                <strong>{item.id}</strong>
                <span>{item.message}</span>
                <a href={item.supplement_href}>去补充</a>
              </li>
            ))}
          </ul>
        )}
      </section>
      <details>
        <summary>状态页的 unknown / degraded / unavailable</summary>
        <dl className="guide-errors">
          {guide.service_status_meanings.map(item => (
            <div key={item.state}><dt>{item.state}</dt><dd>{item.meaning}</dd></div>
          ))}
        </dl>
      </details>
      <details>
        <summary>常见错误及处理</summary>
        <dl className="guide-errors">
          {guide.common_errors.map(item => (
            <div key={item.code}><dt>{item.code}</dt><dd>{item.meaning}</dd></div>
          ))}
        </dl>
      </details>
    </section>
  );
}

/**
 * Both panels together, as one lazily-loadable unit.
 *
 * `/user` opens this only when the disclosure is expanded, so the technical
 * diagnostic surface stays out of that route's first load.
 */
export default function CapabilityGuide({
  guide,
  matrix
}: {
  guide: UsageGuideTruth;
  matrix: FormalCapabilityMatrix;
}): JSX.Element {
  return (
    <>
      <UsageGuideView guide={guide} />
      <CapabilityMatrixView matrix={matrix} />
    </>
  );
}
