const COLORS = {
  VERIFIED_SIGNAL: "#1c7a45",
  MODERATE_RISK: "#a56b12",
  HIGH_NOISE: "#b4332a",
};

export default function TrustGauge({ score = 0, band = "HIGH_NOISE" }) {
  const radius = 78;
  const circumference = 2 * Math.PI * radius;
  const safe = Math.max(0, Math.min(100, Number(score) || 0));
  const offset = circumference - (safe / 100) * circumference;
  const color = COLORS[band] || COLORS.HIGH_NOISE;

  return (
    <div className="relative h-48 w-48 shrink-0" role="img" aria-label={`Trust signal ${safe} percent`}>
      <svg viewBox="0 0 200 200" className="h-full w-full">
        <circle cx="100" cy="100" r={radius} fill="none" stroke="#e6dccb" strokeWidth="14" />
        <circle
          cx="100"
          cy="100"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 100 100)"
          className="transition-[stroke-dashoffset] duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display text-5xl leading-none text-ink">{safe}</span>
        <span className="mt-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-ink/55">out of 100</span>
      </div>
    </div>
  );
}
