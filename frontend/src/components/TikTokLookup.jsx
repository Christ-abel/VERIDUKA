import { useState } from "react";
import { api } from "../api";

const TONE = {
  SCAM: "text-noise",
  DELAYED_DELIVERY: "text-caution",
  BAD_SERVICE: "text-caution",
  POSITIVE: "text-signal",
  SPAM: "text-ink/50",
};

function compact(value) {
  return new Intl.NumberFormat("en", { notation: "compact" }).format(value || 0);
}

export default function TikTokLookup({ onSaved }) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function run(save = false) {
    if (!query.trim()) return;
    setBusy(true);
    setError("");
    try {
      const data = await api.tiktokLookup({ query: query.trim(), save });
      setResult(data);
      if (save) onSaved?.(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const profile = result?.profile;
  return (
    <section className="mt-8 rounded-[24px] border border-line bg-card p-5" aria-label="TikTok shop lookup">
      <h2 className="font-display text-2xl">Check a TikTok shop</h2>
      <p className="mt-1 text-sm leading-relaxed text-ink/70">
        Paste the shop's TikTok link or @handle. We read the public profile and a few recent comments, and classify them.
        This only reads. Nothing is saved or scored unless you choose to.
      </p>
      <form
        className="mt-3 flex flex-col gap-2 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          run(false);
        }}
      >
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="TikTok link or handle"
          placeholder="https://www.tiktok.com/@shopname or @shopname"
          className="min-w-0 flex-1 rounded-xl border border-line px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={busy || !query.trim()}
          className="rounded-full bg-ink px-5 py-2 text-sm font-semibold text-paper disabled:opacity-40"
        >
          {busy ? "Reading TikTok…" : "Look up"}
        </button>
      </form>
      {busy && <p className="mt-2 text-xs text-ink/55">This can take a minute or two while TikTok is read.</p>}
      {error && (
        <p role="alert" className="mt-3 rounded-2xl bg-[#f8e4df] px-4 py-3 text-sm text-noise">
          {error}
        </p>
      )}

      {profile && (
        <div className="mt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-lg font-semibold text-ink">
              {profile.nickname} <span className="font-normal text-ink/55">@{profile.handle}</span>
            </p>
            <a href={profile.profile_url} target="_blank" rel="noreferrer" className="text-sm text-signal">
              Open on TikTok
            </a>
          </div>
          <p className="mt-1 text-xs uppercase tracking-wide text-ink/45">
            {[
              `${compact(profile.followers)} followers`,
              `${compact(profile.likes)} likes`,
              `${compact(profile.videos)} videos`,
              profile.verified ? "TikTok verified" : "not TikTok verified",
              profile.tiktok_seller ? "TikTok Shop seller" : "",
              profile.business_account ? `business account${profile.business_category ? `, ${profile.business_category}` : ""}` : "",
            ]
              .filter(Boolean)
              .join(", ")}
          </p>
          {profile.bio && <p className="mt-2 text-sm leading-relaxed text-ink/85">{profile.bio}</p>}
          {profile.bio_link && <p className="mt-1 break-all text-xs text-ink/55">Link in bio: {profile.bio_link}</p>}

          <h3 className="mt-4 text-sm font-semibold text-ink">
            {result.comments.length
              ? `${result.comments.length} recent comment${result.comments.length === 1 ? "" : "s"} read`
              : "No comments were available on the latest videos"}
          </h3>
          {result.comments.length > 0 && (
            <ul className="mt-2 space-y-2">
              {result.comments.map((comment) => (
                <li key={comment.external_id || comment.text} className="rounded-2xl border border-line px-3 py-2">
                  <p className="text-sm leading-relaxed text-ink/85">{comment.text}</p>
                  <p className="mt-1 text-xs text-ink/55">
                    @{comment.author} ·{" "}
                    <span className={`font-medium ${TONE[comment.classification.category] || ""}`}>
                      {comment.classification.label}
                    </span>{" "}
                    · {Math.round(comment.classification.confidence * 100)}% pattern confidence
                  </p>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => run(true)}
              disabled={busy}
              className="rounded-full border border-ink px-4 py-1.5 text-sm font-semibold text-ink disabled:opacity-40"
            >
              Save shop and comments
            </button>
            <p className="text-xs text-ink/55">{result.note}</p>
          </div>
        </div>
      )}
    </section>
  );
}
