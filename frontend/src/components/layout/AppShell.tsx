import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Icon } from "../common/Icon";

export interface NavItem {
  to: string;
  label: string;
  group?: string;
  icon?: string;
}

/** Page shell: skip link, left sidebar (logo, grouped navigation with icons, footer; a drawer behind the
 * menu button on small screens), a slim top bar slot (selectors, search, status) and the main content. */
export function AppShell({ nav, header, children }: {
  nav: NavItem[];
  header?: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const groups = [...new Set(nav.map((n) => n.group ?? ""))];
  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className={`sidebar${open ? " sidebar--open" : ""}`}>
        <div className="sidebar__top">
          <NavLink to="/" className="sidebar__brand" aria-label="Growth Intelligence, overview">
            <span className="sidebar__mark"><img src="/brand/logo-mark.png" alt="Growth Intelligence" width={56} height={56} /></span>
          </NavLink>
          <button type="button" className="button nav-toggle" aria-expanded={open} aria-controls="primary-nav" onClick={() => setOpen((o) => !o)}>
            <Icon name="overview" size={16} /> {open ? "Close" : "Menu"}
          </button>
        </div>
        <nav id="primary-nav" aria-label="Primary">
          {groups.map((g) => (
            <div className="nav__group" key={g || "main"}>
              {g && <p className="nav__heading">{g}</p>}
              <ul className="nav">
                {nav.filter((item) => (item.group ?? "") === g).map((item) => (
                  <li key={item.to}>
                    <NavLink to={item.to} end={item.to === "/dashboard"} className="nav__link" onClick={() => setOpen(false)}>
                      {item.icon && <Icon name={item.icon} />}
                      <span>{item.label}</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
      {open && <button type="button" className="backdrop" aria-label="Close menu" onClick={() => setOpen(false)} />}
      <div className="content">
        {header && <div className="topbar">{header}</div>}
        <main id="main" className="main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
