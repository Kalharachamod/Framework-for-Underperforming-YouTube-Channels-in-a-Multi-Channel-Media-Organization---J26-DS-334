import { Link } from "react-router-dom";

/** Start screen: the system logo in the centre and one action, analysing an organization. */
export function WelcomePage() {
  return (
    <main className="welcome" aria-labelledby="welcome-title">
      <div className="welcome__inner">
        <img className="welcome__logo" src="/brand/logo.png" alt="Growth Intelligence logo" width={180} height={180} />
        <span className="welcome__kicker">SLIIT · J26-DS-334</span>
        <h1 id="welcome-title">Growth Intelligence</h1>
        <p>Cross-channel audience bridge analysis for YouTube media organizations.</p>
        <Link to="/analyze" className="welcome__tile" aria-label="Enter Dashboard" title="Enter Dashboard">
          <svg viewBox="0 0 100 100" aria-hidden="true">
            <defs>
              <linearGradient id="wsunset" x1="1" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#ffb347" /><stop offset=".35" stopColor="#ff6a3d" /><stop offset=".65" stopColor="#e8336d" /><stop offset="1" stopColor="#7b2cbf" />
              </linearGradient>
              <mask id="wtile" maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100">
                <rect width="100" height="100" fill="#fff" />
                <path d="M44 40H112M44 40V74M36 90L67 37" fill="none" stroke="#000" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
              </mask>
            </defs>
            <polygon points="16,22 84,22 50,84" fill="url(#wsunset)" stroke="url(#wsunset)" strokeWidth="14" strokeLinejoin="round" mask="url(#wtile)" />
          </svg>
        </Link>
      </div>
    </main>
  );
}
