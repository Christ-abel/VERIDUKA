import { useEffect, useState } from "react";
import { api } from "../api";

const TYPES = [
  ["SCAM", "Scam"],
  ["NON_DELIVERY", "Non-delivery"],
  ["POOR_SERVICE", "Poor service"],
  ["POSITIVE", "Positive experience"],
];

export default function ReportModal({ seed, onClose, onSubmitted }) {
  const [vendorId, setVendorId] = useState(seed.vendorId || null);
  const [identifier, setIdentifier] = useState(seed.identifier || "");
  const [reportType, setReportType] = useState("SCAM");
  const [description, setDescription] = useState("");
  const [proofUrl, setProofUrl] = useState("");
  const [phone, setPhone] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  useEffect(() => {
    if (description.trim().length < 8) {
      setPreview(null);
      return undefined;
    }
    const handle = setTimeout(async () => {
      setPreviewing(true);
      try {
        const result = await api.classify({ description, report_type: reportType });
        setPreview(result);
      } catch {
        setPreview(null);
      } finally {
        setPreviewing(false);
      }
    }, 400);
    return () => clearTimeout(handle);
  }, [description, reportType]);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const body = {
      report_type: reportType,
      description: description.trim(),
      proof_url: proofUrl.trim() || null,
      user_phone: phone.trim(),
    };
    if (vendorId) body.vendor_id = vendorId;
    else body.identifier = identifier.trim();
    try {
      const created = await api.report(body);
      onSubmitted(created);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-ink/50 p-3 sm:items-center" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="report-title"
        className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-[28px] bg-card p-5 shadow-card sm:p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-ink/45">Buyer report</p>
            <h2 id="report-title" className="mt-1 font-display text-3xl text-ink">
              {seed.vendorName || "Report a shop"}
            </h2>
          </div>
          <button type="button" onClick={onClose} className="rounded-full px-2 py-1 text-sm text-ink/60 hover:bg-paper">
            Close
          </button>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-ink/70">
          Positive reports move the score when the text reads as a real review and a proof link is attached. The praise cap is +20. Spam is stored and ignored.
        </p>
        <form className="mt-5 space-y-4" onSubmit={submit}>
          <Field label="Shop identifier" htmlFor="identifier">
            <input
              id="identifier"
              value={identifier}
              onChange={(event) => {
                setIdentifier(event.target.value);
                setVendorId(null);
              }}
              placeholder="Paybill, phone, @handle, or shop name"
              required={!vendorId}
              className="field"
            />
          </Field>
          <Field label="What happened" htmlFor="report-type">
            <select id="report-type" value={reportType} onChange={(event) => setReportType(event.target.value)} className="field">
              {TYPES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Description" htmlFor="description">
            <textarea
              id="description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              required
              minLength={10}
              rows={5}
              placeholder="I paid the paybill on Friday. The rider never arrived and they blocked me on WhatsApp."
              className="field resize-y"
            />
          </Field>
          <div className="rounded-2xl bg-paper px-4 py-3 text-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink/45">Pattern reading</p>
            {previewing && <p className="mt-2 text-ink/60">Reading the report…</p>}
            {!previewing && !preview && <p className="mt-2 text-ink/60">Type a few sentences to preview the category.</p>}
            {preview && (
              <div className="mt-2">
                <p className="font-semibold text-ink">
                  {preview.label}, {Math.round(preview.confidence * 100)}% confidence
                </p>
                <p className="mt-1 leading-relaxed text-ink/75">{preview.summary}</p>
                {preview.is_false_report && (
                  <p className="mt-2 rounded-xl bg-[#f8e4df] px-3 py-2 text-noise">This draft would be excluded from the score.</p>
                )}
              </div>
            )}
          </div>
          <Field label="Proof link" htmlFor="proof">
            <input
              id="proof"
              value={proofUrl}
              onChange={(event) => setProofUrl(event.target.value)}
              placeholder="https://example.com/receipt"
              className="field"
            />
          </Field>
          <Field label="Your phone" htmlFor="phone">
            <input
              id="phone"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              required
              inputMode="tel"
              placeholder="0712345678"
              className="field"
            />
          </Field>
          {error && (
            <p role="alert" className="rounded-xl bg-[#f8e4df] px-3 py-2 text-sm text-noise">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={saving}
            className="w-full rounded-full bg-deep py-3 text-sm font-semibold text-paper disabled:opacity-60"
          >
            {saving ? "Filing…" : "File report"}
          </button>
        </form>
      </div>
    </div>
  );
}

function Field({ label, htmlFor, children }) {
  return (
    <label htmlFor={htmlFor} className="block text-sm font-medium text-ink">
      {label}
      <div className="mt-1">{children}</div>
    </label>
  );
}
