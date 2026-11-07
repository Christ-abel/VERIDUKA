import { useState } from "react";
import { api } from "../api";
import { formatWhen, signed } from "../format";

const PLATFORMS = [
  ["instagram", "Instagram"],
  ["facebook", "Facebook"],
  ["tiktok", "TikTok"],
  ["x", "X"],
  ["whatsapp", "WhatsApp"],
];

export default function SocialPanel({ vendor, onChanged }) {
  const [platform, setPlatform] = useState("instagram");
  const [comments, setComments] = useState("");
  const [permalink, setPermalink] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const social = (vendor.reports || []).filter((item) => item.source === "social");

  async function submit(event) {
    event.preventDefault();
    const lines = comments
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length >= 8);
    if (!lines.length) {
      setError("Add at least one comment of 8 characters or more. Put each comment on its own line.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api.importSocial({
        vendor_id: vendor.id,
        platform,
        permalink: permalink.trim() || null,
        comments: lines.map((text) => ({ text })),
      });
      setComments("");
      setNotice(
        `Saved ${result.imported}. ${result.counted} can move the score. ${result.held} are held until they have a clear reading and a post link. Score is now ${result.score}%.`,
      );
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function sync() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api.syncSocial();
      setNotice(result.message);
      if (result.imported) await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="text-sm leading-relaxed text-ink/75">
        Comments come from people, or from a shop that has connected its own Instagram professional account.
        Paste one public comment per line. Include the post link if the comment should move the trust score.
        VeriDuka does not log into Instagram or read an account that has not authorized the app.
      </p>
      <form className="mt-4 space-y-3" onSubmit={submit}>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm font-medium" htmlFor="social-platform">
            Platform
            <select
              id="social-platform"
              className="field mt-1"
              value={platform}
              onChange={(event) => setPlatform(event.target.value)}
            >
              {PLATFORMS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium" htmlFor="social-link">
            Post link
            <input
              id="social-link"
              className="field mt-1"
              value={permalink}
              onChange={(event) => setPermalink(event.target.value)}
              placeholder="https://www.instagram.com/p/example"
            />
          </label>
        </div>
        <label className="block text-sm font-medium" htmlFor="social-comments">
          Comments
          <textarea
            id="social-comments"
            className="field mt-1"
            rows={5}
            value={comments}
            onChange={(event) => setComments(event.target.value)}
            placeholder={"Paid the paybill and they blocked me. Nothing was delivered.\nFast delivery and the item was genuine. I recommend this shop."}
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <button type="submit" disabled={busy} className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper disabled:opacity-60">
            {busy ? "Saving…" : "Add comments"}
          </button>
          <button type="button" onClick={sync} disabled={busy} className="rounded-full border border-ink px-4 py-2 text-sm font-semibold disabled:opacity-60">
            Sync connected Instagram
          </button>
        </div>
      </form>
      {notice && <p className="mt-3 text-sm text-ink/80">{notice}</p>}
      {error && (
        <p role="alert" className="mt-3 rounded-xl bg-[#f8e4df] px-3 py-2 text-sm text-noise">
          {error}
        </p>
      )}
      <ul className="mt-5 space-y-3">
        {social.length === 0 && <li className="text-sm text-ink/60">No social comments on this shop yet.</li>}
        {social.map((report) => (
          <li key={report.id} className="rounded-2xl border border-line px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold">{report.ai_label}</p>
              <p className="font-mono text-sm">{signed(report.impact?.points || 0)}</p>
            </div>
            <p className="mt-1 text-xs uppercase tracking-wide text-ink/45">
              {formatWhen(report.created_at)}, {report.platform}
              {report.author_handle ? ` @${report.author_handle}` : ""}
            </p>
            <p className="mt-2 text-sm leading-relaxed">{report.description}</p>
            <p className="mt-2 text-xs text-ink/55">{report.impact?.reason}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
