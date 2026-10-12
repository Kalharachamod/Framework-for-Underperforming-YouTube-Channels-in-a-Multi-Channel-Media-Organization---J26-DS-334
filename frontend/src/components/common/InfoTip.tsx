import { useId, type ReactNode } from "react";

/** Small "i" button that reveals a note on hover or keyboard focus (notes stay available to screen readers). */
export function InfoTip({ children, label = "About this panel" }: { children: ReactNode; label?: string }) {
  const id = useId();
  return (
    <span className="infotip">
      <button type="button" className="infotip__button" aria-label={label} aria-describedby={id}>i</button>
      <span role="tooltip" id={id} className="infotip__bubble">{children}</span>
    </span>
  );
}
