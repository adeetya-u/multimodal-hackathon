import { Link, useLocation } from "react-router-dom";
import { ScalpelLogo } from "./ScalpelLogo";

const TABS = [
  { to: "/prep", label: "Prep" },
  { to: "/or", label: "OR" },
  { to: "/summary", label: "Summary" },
] as const;

export function DevNav() {
  const { pathname } = useLocation();

  return (
    <nav className="apple-nav" aria-label="Main">
      <div className="apple-nav-inner">
        <Link to="/prep" className="apple-nav-brand" aria-label="Scalpel home">
          <ScalpelLogo size="sm" showWordmark />
        </Link>
        <div className="apple-segmented" role="tablist">
          {TABS.map(({ to, label }) => (
            <Link
              key={to}
              to={to}
              role="tab"
              aria-selected={pathname === to}
              className={pathname === to ? "apple-segment active" : "apple-segment"}
            >
              {label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
