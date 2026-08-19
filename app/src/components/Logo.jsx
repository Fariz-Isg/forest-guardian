import './Logo.css';

// Core brand asset — reproduced exactly from the approved animated logo
// (forest_guardian_logo_animated_righteous.html). Shapes, colors, and
// proportions must not be altered, redrawn, or simplified.
export default function Logo({ size = 220 }) {
  return (
    <div className="fg-logo" style={{ width: size }}>
      <svg viewBox="0 0 680 320" xmlns="http://www.w3.org/2000/svg" role="img">
        <title>Forest Guardian</title>
        <desc>
          A warm circular emblem gently breathing, with a flickering flame and leaf, rising
          ember particles, twinkling sparkles, a satellite orbiting with a trailing path, a
          radar-like detection pulse from the flame, and the name set in Righteous below.
        </desc>
        <circle className="star s1" cx="255" cy="60" r="2.5" fill="#e8622c" />
        <circle className="star s2" cx="430" cy="50" r="2" fill="#a8481f" />
        <circle className="star s3" cx="245" cy="165" r="2" fill="#e8622c" />
        <circle className="star s4" cx="440" cy="170" r="2.5" fill="#a8481f" />
        <g className="badgegroup">
          <circle className="pingring" cx="340" cy="145" r="8" fill="none" stroke="#e8622c" strokeWidth="2" />
          <circle className="pingring pingring2" cx="340" cy="145" r="8" fill="none" stroke="#e8622c" strokeWidth="2" />
          <circle cx="340" cy="110" r="75" fill="#ffedd2" />
          <circle className="trailring" cx="340" cy="110" r="95" fill="none" stroke="#a8481f" strokeWidth="1.5" strokeDasharray="10 590" opacity="0.6" />
          <circle cx="340" cy="110" r="95" fill="none" stroke="#e8622c" strokeWidth="0.5" opacity="0.2" />
          <circle className="ember e1" cx="332" cy="130" r="2" fill="#f0a34a" />
          <circle className="ember e2" cx="345" cy="120" r="1.6" fill="#e8622c" />
          <circle className="ember e3" cx="338" cy="135" r="1.8" fill="#f0a34a" />
          <path className="flame" d="M340 62c-6 17-27 29-27 53 0 17 12 31 29 31s29-14 29-31c0-11-6-19-11-26 1 8-4 15-10 15-8 0-11-6-10-15-6 7-12 13-12 21 0 6 5 11 11 11" fill="#e8622c" />
          <path d="M308 134c8-25 33-38 47-59-3 21 5 34 5 49 0 18-15 33-34 33-12 0-20-8-18-23z" fill="#a8481f" />
          <g className="orbitgroup"><circle cx="435" cy="110" r="6" fill="#a8481f" /></g>
        </g>
        <text x="340" y="242" textAnchor="middle" style={{ fontFamily: "'Righteous'", fontSize: 26, fill: '#e8622c' }}>Forest Guardian</text>
        <text x="340" y="266" textAnchor="middle" style={{ fontSize: 12, fill: 'var(--warm-gray)', fontFamily: 'var(--font-sans)' }}>satellite fire risk prediction</text>
      </svg>
    </div>
  );
}
