export interface TabItem<T extends string> {
  id: T;
  label: string;
}

export function Tabs<T extends string>({
  activeTab,
  ariaLabel,
  onChange,
  tabs,
}: {
  activeTab: T;
  ariaLabel: string;
  onChange: (tab: T) => void;
  tabs: readonly TabItem<T>[];
}) {
  return (
    <div aria-label={ariaLabel} className="tab-bar" role="tablist">
      {tabs.map((tab) => (
        <button
          aria-selected={activeTab === tab.id}
          className="tab-button"
          key={tab.id}
          role="tab"
          type="button"
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
