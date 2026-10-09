import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";

export interface NavItem {
  to: string;
  label: string;
}

/** Page shell: skip link, collapsible sidebar navigation (mobile), header slot and main content. */
export function AppShell({ nav, header, children }: { nav: NavItem[]; header?: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className={`sidebar${open ? " sidebar--open" : ""}`}>
        <div className="sidebar__top">
          <div className="brand">
            <span className="brand__name">Growth Intelligence</span>
            <span className="brand__sub">Audience Bridge Scoring</span>
          </div>
          <button
            type="button"
            className="button nav-toggle"
            aria-expanded={open}
            aria-controls="primary-nav"
            onClick={() => setOpen((o) => !o)}
          >
            Menu
          </button>
        </div>
        <nav id="primary-nav" aria-label="Primary">
          <ul className="nav">
            {nav.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.to === "/"} className="nav__link" onClick={() => setOpen(false)}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <div className="content">
        {header && <div className="topbar">{header}</div>}
        <main id="main" className="main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
