import { useState } from "react";
import { api } from "../api";

/**
 * A shop puts itself in the directory.
 * Registration does not add the legal bonus. The score starts at the base 50.
 */
const EMPTY = {
  name: "",
  phone: "",
  paybill: "",
  instagram: "",
  facebook: "",
  tiktok: "",
  location: "",
  category: "",
  about: "",
  kra_pin: "",
  brs_number: "",
};

export default function RegisterModal({ onClose, onCreated }) {
  const [form, setForm] = useState(EMPTY);
  const [created, setCreated] = useState(null);
  const [matches, setMatches] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api.register({
        name: form.name.trim(),
        phone: form.phone.trim(),
        paybill: form.paybill.trim() || null,
        instagram: form.instagram.trim() || null,
        facebook: form.facebook.trim() || null,
        tiktok: form.tiktok.trim() || null,
        location: form.location.trim() || "Kenya",
        category: form.category.trim() || "General",
        about: form.about.trim(),
        kra_pin: form.kra_pin.trim() || null,
        brs_number: form.brs_number.trim() || null,
      });
      const found = await api.tiktokMatches(created.id).catch(() => []);
      if (found.length) {
        setCreated(created);
        setMatches(found);
      } else {
        onCreated(created);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function connect(match) {
    setBusy(true);
    setError("");
    try {
      const claimed = await api.claimTiktok(created.id, match.id);
      onCreated(claimed);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <div className="fixed inset-0 z-30 flex items-end justify-center bg-ink/40 p-4 sm:items-center">
        <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-[28px] bg-card p-5 shadow-card sm:p-7">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-ink/45">Shop registered</p>
          <h2 className="mt-1 font-display text-3xl">Is one of these your TikTok?</h2>
          <p className="mt-3 text-sm leading-relaxed text-ink/70">
            Buyers have already looked up these TikTok shops. Connect yours and its comments move onto your page. To prove it is
            yours, your shop's phone number or paybill must be in that TikTok bio.
          </p>
          <ul className="mt-4 space-y-3">
            {matches.map((match) => (
              <li key={match.id} className="rounded-2xl border border-line px-4 py-3">
                <p className="font-semibold text-ink">
                  {match.name} <span className="font-normal text-ink/55">@{match.tiktok}</span>
                </p>
                {match.about && <p className="mt-1 text-sm text-ink/70">{match.about}</p>}
                <p className="mt-1 text-xs text-ink/50">
                  {match.comments} comment{match.comments === 1 ? "" : "s"} on file{match.same_handle ? ", same handle you entered" : ""}
                </p>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => connect(match)}
                  className="mt-2 rounded-full bg-ink px-4 py-1.5 text-sm font-semibold text-paper disabled:opacity-60"
                >
                  {busy ? "Connecting…" : "This is mine"}
                </button>
              </li>
            ))}
          </ul>
          {error && (
            <p role="alert" className="mt-3 rounded-xl bg-[#f8e4df] px-3 py-2 text-sm text-noise">
              {error}
            </p>
          )}
          <button type="button" onClick={() => onCreated(created)} className="mt-4 text-sm text-ink/60 underline">
            None of these are mine
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center bg-ink/40 p-4 sm:items-center">
      <form onSubmit={submit} className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-[28px] bg-card p-5 shadow-card sm:p-7">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-ink/45">Shop registration</p>
            <h2 className="mt-1 font-display text-3xl">Put your shop on file</h2>
          </div>
          <button type="button" onClick={onClose} className="text-sm text-ink/55">
            Close
          </button>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-ink/70">
          Add the KRA PIN and BRS number if you have them. When the shop name matches that registry record, the score starts at 75. A number we do not have on file is saved and the score stays 50. If you add a TikTok handle we also check it for comments, and we will show any TikTok shop that looks like yours so you can connect it.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Shop name" value={form.name} onChange={(value) => setField("name", value)} required />
          <Field label="Phone" value={form.phone} onChange={(value) => setField("phone", value)} placeholder="0712345678" required />
          <Field label="Paybill" value={form.paybill} onChange={(value) => setField("paybill", value)} placeholder="400200" />
          <Field label="KRA PIN" value={form.kra_pin} onChange={(value) => setField("kra_pin", value)} placeholder="A123456789Z" />
          <Field label="BRS number" value={form.brs_number} onChange={(value) => setField("brs_number", value)} placeholder="PVT-9X2K41" />
          <Field label="Location" value={form.location} onChange={(value) => setField("location", value)} placeholder="Kayole, Nairobi" />
          <Field label="Instagram" value={form.instagram} onChange={(value) => setField("instagram", value)} placeholder="@yourshop" />
          <Field label="Facebook page" value={form.facebook} onChange={(value) => setField("facebook", value)} />
          <Field label="TikTok" value={form.tiktok} onChange={(value) => setField("tiktok", value)} placeholder="@yourshop" />
          <Field label="Category" value={form.category} onChange={(value) => setField("category", value)} placeholder="Fashion" />
        </div>
        <label className="mt-3 block text-sm font-medium">
          About the shop
          <textarea className="field mt-1" rows={3} value={form.about} onChange={(event) => setField("about", event.target.value)} />
        </label>
        {error && (
          <p role="alert" className="mt-3 rounded-xl bg-[#f8e4df] px-3 py-2 text-sm text-noise">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy} className="mt-4 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper disabled:opacity-60">
          {busy ? "Saving…" : "Register shop"}
        </button>
      </form>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, required }) {
  return (
    <label className="text-sm font-medium">
      {label}
      <input
        className="field mt-1"
        value={value}
        required={required}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
