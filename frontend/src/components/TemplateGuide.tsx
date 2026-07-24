const templateVariables = [
  ["{number}", "番号/作品编号"],
  ["{xchina_id}", "XChina ID"],
  ["{title}", "作品标题"],
  ["{original_title}", "原始标题"],
  ["{studio}", "制作商"],
  ["{series}", "系列"],
  ["{year}", "年份"],
  ["{release_date}", "发布日期"],
  ["{actors}", "演员列表"],
  ["{first_actor}", "第一位演员"],
  ["{source_filename}", "源文件名"],
] as const;

export function TemplateGuide() {
  return (
    <aside className="template-guide" aria-label="命名模板填写说明">
      <div className="template-guide-copy">
        <span className="badge">填写说明</span>
        <strong>文件夹模板一行一级目录；文件名模板只写最终文件名。</strong>
        <p>
          想生成多级目录时，不要在单行里写 <code>/</code>，而是把每一级目录拆成多行。
          非法字符会自动清洗，预览后再执行整理。
        </p>
      </div>

      <div className="template-example-grid">
        <div className="template-example-card">
          <span>推荐媒体库格式</span>
          <code>{"{studio}\n{xchina_id} - {title}"}</code>
          <small>文件夹：制作商 / 编号 - 标题</small>
        </div>
        <div className="template-example-card">
          <span>最终文件名</span>
          <code>{"{xchina_id} - {title}"}</code>
          <small>生成：XC-001 - Sample Title.mkv</small>
        </div>
      </div>

      <details className="template-variable-details">
        <summary>查看可用变量</summary>
        <div className="template-variable-list">
          {templateVariables.map(([variable, description]) => (
            <span className="template-variable-chip" key={variable}>
              <code>{variable}</code>
              <small>{description}</small>
            </span>
          ))}
        </div>
      </details>
    </aside>
  );
}
