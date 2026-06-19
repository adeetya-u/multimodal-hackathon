import type { ReactNode } from "react";

interface Props {
  title: string;
  large?: boolean;
  actions?: ReactNode;
}

/** iOS-style page header — brand lives in DevNav; this is the large title row only. */
export function AppChrome({ title, large = false, actions }: Props) {
  return (
    <header className={`app-chrome ${large ? "app-chrome-large" : ""}`}>
      <div className="app-chrome-bar">
        <h1 className="app-chrome-title">{title}</h1>
        {actions ? <div className="app-chrome-actions">{actions}</div> : null}
      </div>
    </header>
  );
}
