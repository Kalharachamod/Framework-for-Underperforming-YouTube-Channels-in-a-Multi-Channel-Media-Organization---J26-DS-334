import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Icon } from "../common/Icon";

export interface NavItem {
  to: string;
  label: string;
  group?: string;
  icon?: string;
}

/** Page shell: skip link, sidebar (brand, grouped navigation with icons, optional extra section such as
 * tracked channels; mobile: menu button), top bar slot and the main content. */
export function AppShell({ nav, header, sidebarExtra, children }: {
  nav: NavItem[];
  header?: ReactNode;
  sidebarExtra?: ReactNode;
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
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className={`sidebar${open ? " sidebar--open" : ""}`}>
        <div className="sidebar__top">
          <div className="brand">
            <span className="brand__mark" aria-hidden="true"><Icon name="play" size={18} /></span>
            <span className="brand__text">
              <span className="brand__name">Growth Intelligence</span>
              <span className="brand__sub">Audience Intelligence</span>
            </span>
          </div>
          <button
            type="button"
            className="button nav-toggle"
            aria-expanded={open}
            aria-controls="primary-nav"
            onClick={() => setOpen((o) => !o)}
          >
            <Icon name="overview" size={16} /> {open ? "Close" : "Menu"}
          </button>
        </div>
        <nav id="primary-nav" aria-label="Primary">
          {groups.map((g) => (
            <div className="nav__group" key={g || "main"}>
              {g && <p className="nav__heading">{g}</p>}
              <ul className="nav">
                {nav
                  .filter((item) => (item.group ?? "") === g)
                  .map((item) => (
                    <li key={item.to}>
                      <NavLink to={item.to} end={item.to === "/"} className="nav__link" onClick={() => setOpen(false)}>
                        {item.icon && <Icon name={item.icon} />}
                        <span>{item.label}</span>
                      </NavLink>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
          {sidebarExtra}
        </nav>
        <p className="sidebar__foot">Read-only research view</p>
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
