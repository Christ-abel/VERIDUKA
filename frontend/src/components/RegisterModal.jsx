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
};

export default function RegisterModal({ onClose, onCreated }) {
  const [form, setForm] = useState(EMPTY);
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
      });
      onCreated(created);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
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
          This adds the shop to the directory at a score of 50. A KRA or BRS match is a separate check. Instagram, Facebook, and TikTok handles become links. They are not pulled in as comments.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Shop name" value={form.name} onChange={(value) => setField("name", value)} required />
          <Field label="Phone" value={form.phone} onChange={(value) => setField("phone", value)} placeholder="0712345678" required />
          <Field label="Paybill" value={form.paybill} onChange={(value) => setField("paybill", value)} placeholder="400200" />
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
