import { useEffect, useState } from "react";
import { api } from "../api";

/**
 * Public pages and a plain comment reader.
 *
 * Links open Instagram, Facebook, or TikTok for someone with a browser.
 * The reader below, and the SMS COMMENTS command, walk the same saved
 * reviews one at a time. Neither path classifies the text or moves the score.
 */
const PAGES = [
  ["instagram", "Instagram", "Photo and comment threads on the shop's profile."],
  ["facebook", "Facebook", "Page posts and the comments under them."],
  ["tiktok", "TikTok", "Short videos and the reviews left on them."],
];

export default function SocialPanel({ vendor }) {
  const profiles = vendor.profiles || {};
  const available = PAGES.filter(([key]) => profiles[key]);

  return (
    <div>
      <CommentReader vendorId={vendor.id} />
      <p className="mt-6 text-sm leading-relaxed text-ink/75">
        Someone with a smartphone can also open the shop's own page. VeriDuka only links out. It does not sign in,
        and it does not copy those comments into the score.
      </p>
      {available.length === 0 ? (
        <p className="mt-4 text-sm text-ink/60">No public page is on file for this shop yet.</p>
      ) : (
        <ul className="mt-4 grid gap-3 sm:grid-cols-3">
          {available.map(([key, label, detail]) => (
            <li key={key} className="rounded-2xl border border-line bg-paper px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink/45">{label}</p>
              <p className="mt-2 font-medium text-ink">@{profiles[key].handle}</p>
              <p className="mt-1 text-sm leading-relaxed text-ink/65">{detail}</p>
              <a
                href={profiles[key].url}
                target="_blank"
                rel="noreferrer"
                className="mt-3 inline-block text-sm font-semibold text-signal"
              >
                Open {label}
              </a>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-4 text-sm text-ink/60">
        Saw a scam or a delivery that never came? Use Add a report. That is the path that can move the score.
      </p>
    </div>
  );
}

function CommentReader({ vendorId }) {
  const [lines, setLines] = useState([]);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setIndex(0);
    api
      .reading(vendorId)
      .then((data) => {
        if (!cancelled) {
          setLines(data.lines || []);
          setError("");
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [vendorId]);

  const total = lines.length;
  const line = total ? lines[Math.min(index, total - 1)] : "";

  return (
    <div className="rounded-2xl border border-line bg-paper px-4 py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink/45">Read the reviews</p>
      <p className="mt-2 text-sm leading-relaxed text-ink/70">
        No smartphone? Text COMMENTS and the paybill, then NEXT. This page does the same thing. The words are shown as saved. They are not scored again here.
      </p>
      {error && <p className="mt-3 text-sm text-noise">{error}</p>}
      {!error && total === 0 && <p className="mt-3 text-sm text-ink/60">No reviews on file yet.</p>}
      {total > 0 && (
        <>
          <p className="mt-3 text-sm leading-relaxed text-ink">{line}</p>
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={() => setIndex((current) => Math.max(0, current - 1))}
              disabled={index === 0}
              className="rounded-full border border-ink px-3 py-1.5 text-sm font-semibold disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setIndex((current) => Math.min(total - 1, current + 1))}
              disabled={index >= total - 1}
              className="rounded-full bg-ink px-3 py-1.5 text-sm font-semibold text-paper disabled:opacity-40"
            >
              Next
            </button>
            <p className="text-sm text-ink/55">
              {index + 1} of {total}
            </p>
          </div>
        </>
      )}
    </div>
  );
}
