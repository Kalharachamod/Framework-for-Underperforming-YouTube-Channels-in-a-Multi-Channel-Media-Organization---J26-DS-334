import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
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
  const { pathname } = useLocation();
  const currentPath = pathname.replace(/\/+$/, "") || "/";
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
          <Link to="/" className="sidebar__brand" aria-label="Growth Intelligence, overview">
            <span className="sidebar__mark"><img src="/brand/logo-mark.png" alt="Growth Intelligence" width={30} height={30} /></span>
            <span className="sidebar__word"><strong>Growth Intelligence</strong><span>Audience intelligence research</span></span>
          </Link>
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
                    <Link to={item.to} className={`nav__link${currentPath === item.to ? " active" : ""}`} aria-current={currentPath === item.to ? "page" : undefined} onClick={() => setOpen(false)}>
                      {item.icon && <Icon name={item.icon} />}
                      <span>{item.label}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <p className="sidebar__foot"><span>SLIIT · J26-DS-334</span><span className="mono">v0.1.0</span></p>
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
