import { useEffect, useState } from "react";
import { api } from "../api";
import { formatPhone, formatWhen, handleOf, signed, tone, whatsappUrl } from "../format";
import SocialPanel from "./SocialPanel";
import TrustGauge from "./TrustGauge";

const TABS = [
  { id: "legal", label: "Legal registration" },
  { id: "reports", label: "Incident reports" },
  { id: "social", label: "Public pages" },
  { id: "service", label: "Service rating" },
];

const STATUS = {
  verified: "On file",
  pending: "Pending",
  unverified: "Not on file",
};

const LABEL_TONE = {
  signal: "text-signal",
  caution: "text-caution",
  noise: "text-noise",
};

const BANNER_TONE = {
  signal: "border-signal/30 bg-signal/10",
  caution: "border-caution/30 bg-caution/10",
  noise: "border-noise/30 bg-noise/10",
};

export default function VendorDossier({ vendor, onBack, onReport, onChanged, onSms }) {
  const [tab, setTab] = useState("legal");
  const [checking, setChecking] = useState(false);
  const [legalMessage, setLegalMessage] = useState("");
  const [openPart, setOpenPart] = useState("");
  const band = tone(vendor.band);

  useEffect(() => {
    setTab("legal");
    setLegalMessage("");
    setOpenPart("");
  }, [vendor.id]);

  async function recheck() {
    setChecking(true);
    setLegalMessage("");
    try {
      const result = await api.verifyLegal({
        vendor_id: vendor.id,
        business_name: vendor.name,
        kra_pin: vendor.kra_pin,
        brs_number: vendor.brs_number,
      });
      setLegalMessage(result.message);
      await onChanged();
    } catch (error) {
      setLegalMessage(error.message);
    } finally {
      setChecking(false);
    }
  }

  const detail = vendor.score_detail;
  const parts = [
    { id: "base", label: `${detail.base} base`, text: "Every shop starts at 50, before a registry match or a buyer report." },
    {
      id: "legal",
      label: detail.legal_points ? `+${detail.legal_points} legal` : "0 legal",
      text: detail.legal_points
        ? "An active KRA PIN or a registered BRS record adds 25, once."
        : "There is no active KRA or BRS match, so the legal bonus stays at 0.",
    },
    {
      id: "reviews",
      label: detail.positive_points ? `+${detail.positive_points} reviews` : "0 reviews",
      text: "Verified praise adds 5, and the praise total stops at 20.",
    },
    {
      id: "scam",
      label: detail.scam_points ? `${detail.scam_points} scam` : "0 scam",
      text: "An unresolved scam removes 20. A scam from the last 30 days counts double.",
    },
    {
      id: "service",
      label: detail.service_points ? `${detail.service_points} service` : "0 service",
      text: "A late delivery or poor service removes 5, and a recent one counts double.",
    },
  ];
  const activePart = parts.find((part) => part.id === openPart);
  const lookup = vendor.paybill || vendor.phone || vendor.name;
  const chat = whatsappUrl(
    vendor.phone,
    `I checked ${vendor.name} on VeriDuka. The score is ${detail.score}. Is paybill ${vendor.paybill || "this shop"} still yours?`,
  );

  return (
    <article id="results" className="min-w-0 rounded-[28px] border border-line bg-card p-5 shadow-card sm:p-7">
      <button type="button" onClick={onBack} className="text-sm font-medium text-signal hover:underline">
        All shops
      </button>
      <div className="mt-4 flex flex-col items-center gap-6 md:flex-row md:items-start">
        <TrustGauge score={vendor.score} band={vendor.band} />
        <div className="min-w-0 flex-1 text-center md:text-left">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-ink/50">
            {vendor.category}, {vendor.location}
          </p>
          <h2 className="mt-1 font-display text-4xl leading-tight text-ink">{vendor.name}</h2>
          <p className={`mt-3 text-sm font-semibold uppercase tracking-[0.14em] ${LABEL_TONE[band]}`}>{vendor.label}</p>
          <div className="mt-4 flex flex-wrap justify-center gap-2 md:justify-start">
            <Badge on={vendor.badges.brs_registered} onLabel="BRS Registered" offLabel="BRS not registered" />
            <Badge on={vendor.badges.kra_active} onLabel="Active KRA PIN" offLabel="KRA PIN inactive" />
            <Badge on={vendor.badges.mpesa_verified} onLabel="M-Pesa Verified" offLabel="M-Pesa not verified" />
          </div>
          <div className="mt-4 flex flex-wrap justify-center gap-2 md:justify-start">
            {chat && (
              <a href={chat} target="_blank" rel="noreferrer" className="rounded-full bg-[#128C7E] px-4 py-2 text-sm font-semibold text-white">
                Ask on WhatsApp
              </a>
            )}
            <button type="button" onClick={() => onSms?.(`VERIFY ${lookup}`)} className="rounded-full border border-ink px-4 py-2 text-sm font-semibold">
              Check by SMS
            </button>
            <button type="button" onClick={() => onSms?.(`COMMENTS ${lookup}`)} className="rounded-full border border-ink px-4 py-2 text-sm font-semibold">
              Read reviews by SMS
            </button>
          </div>
        </div>
      </div>

      <div className={`mt-6 rounded-2xl border px-4 py-3 text-sm leading-relaxed text-ink ${BANNER_TONE[band]}`}>
        <p className="font-semibold">{vendor.advice}</p>
        <p className="mt-1 text-ink/75">{vendor.about}</p>
      </div>

      <div className="mt-4 rounded-2xl bg-paper px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Score parts">
            {parts.map((part) => (
              <button
                key={part.id}
                type="button"
                aria-pressed={openPart === part.id}
                onClick={() => setOpenPart((current) => (current === part.id ? "" : part.id))}
                className={`rounded-full border px-3 py-1 font-mono text-sm ${
                  openPart === part.id ? "border-ink bg-ink text-paper" : "border-line bg-card text-ink/80"
                }`}
              >
                {part.label}
              </button>
            ))}
            <span className="self-center font-mono text-sm text-ink/70">= {detail.score}</span>
          </div>
          <button
            type="button"
            onClick={onReport}
            className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper"
          >
            Add a report
          </button>
        </div>
        {activePart && <p className="mt-3 text-sm leading-relaxed text-ink/75">{activePart.text}</p>}
        {detail.raw !== detail.score && <p className="mt-2 text-xs text-ink/50">Raw total {detail.raw}, clamped between 0 and 100.</p>}
      </div>
      <p className="mt-3 text-sm text-ink/60">
        Score inputs are the registry and classified buyer reports. SMS repeats this number. Social pages are links, not inputs.
      </p>
      <ul className="mt-3 space-y-1 text-sm text-ink/70">
        {detail.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>

      <div className="mt-6 flex gap-2 overflow-x-auto border-b border-line" role="tablist">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
              tab === item.id ? "border-signal text-ink" : "border-transparent text-ink/55"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="pt-5" role="tabpanel">
        {tab === "legal" && (
          <LegalPanel vendor={vendor} checking={checking} message={legalMessage} onRecheck={recheck} />
        )}
        {tab === "reports" && (
          <ReportList
            reports={vendor.reports.filter((item) => item.source !== "social")}
            shopName={vendor.name}
            onChanged={onChanged}
          />
        )}
        {tab === "social" && <SocialPanel vendor={vendor} />}
        {tab === "service" && <ServicePanel rating={detail.service_rating} />}
      </div>
    </article>
  );
}

function Badge({ on, onLabel, offLabel }) {
  return (
    <span
      className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide ${
        on ? "border-signal/30 bg-signal/10 text-signal" : "border-line bg-paper text-ink/45"
      }`}
    >
      {on ? onLabel : offLabel}
    </span>
  );
}

function LegalPanel({ vendor, checking, message, onRecheck }) {
  const rows = [
    ["Trading phone", vendor.phone ? formatPhone(vendor.phone) : "None"],
    ["M-Pesa paybill", vendor.paybill || "None"],
    ["Instagram", vendor.instagram ? handleOf(vendor.instagram) : "None"],
    ["KRA PIN", vendor.kra_pin || "None on file"],
    ["KRA status", STATUS[vendor.kra_status] || vendor.kra_status],
    ["BRS number", vendor.brs_number || "None on file"],
    ["BRS status", STATUS[vendor.brs_status] || vendor.brs_status],
  ];

  return (
    <div>
      <p className="text-sm text-ink/70">
        Registry answers come from the bundled BRS and KRA mock, the stand-in for the official APIs.
      </p>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="rounded-2xl bg-paper px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-ink/45">{label}</dt>
            <dd className="mt-1 font-medium text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      {vendor.official && (
        <div className="mt-4 rounded-2xl border border-line px-4 py-3 text-sm">
          <p className="font-semibold text-ink">{vendor.official.registered_name}</p>
          <p className="mt-1 text-ink/70">
            {vendor.official.entity_type.replaceAll("_", " ")}, {vendor.official.county}, registered{" "}
            {vendor.official.registered_on}
          </p>
          <p className="mt-1 text-ink/70">
            Official KRA {vendor.official.kra_status}, BRS {vendor.official.brs_status}.
          </p>
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onRecheck}
          disabled={checking}
          className="rounded-full border border-ink px-4 py-2 text-sm font-semibold disabled:opacity-60"
        >
          {checking ? "Checking registry…" : "Check mock registry"}
        </button>
        {message && <p className="text-sm text-ink/80">{message}</p>}
      </div>
    </div>
  );
}

function ReplyBox({ report, shopName, onChanged }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [author, setAuthor] = useState(shopName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.reply(report.id, { text, author });
      setText("");
      setOpen(false);
      onChanged?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="mt-2 text-sm text-signal">
        Reply publicly
      </button>
    );
  }
  return (
    <form onSubmit={submit} className="mt-3 space-y-2">
      <input
        value={author}
        onChange={(event) => setAuthor(event.target.value)}
        aria-label="Replying as"
        className="w-full rounded-xl border border-line px-3 py-2 text-sm"
      />
      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        aria-label="Public reply"
        rows={3}
        maxLength={1000}
        placeholder="Write your side. A reply does not change the score."
        className="w-full rounded-xl border border-line px-3 py-2 text-sm"
      />
      {error && <p className="text-xs text-noise">{error}</p>}
      <div className="flex gap-3">
        <button type="submit" disabled={busy} className="text-sm font-medium text-signal disabled:opacity-50">
          {busy ? "Posting..." : "Post reply"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="text-sm text-ink/55">
          Cancel
        </button>
      </div>
    </form>
  );
}

function ResolveButton({ report, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function resolve() {
    const reviewer = window.prompt("Reviewer name. Resolving stops this scam report from costing points.");
    if (!reviewer) return;
    setBusy(true);
    setError("");
    try {
      await api.resolve(report.id, { reviewer });
      onChanged?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span>
      <button type="button" onClick={resolve} disabled={busy} className="ml-4 text-sm text-ink/60 underline disabled:opacity-50">
        {busy ? "Saving..." : "Mark resolved (review)"}
      </button>
      {error && <span className="ml-2 text-xs text-noise">{error}</span>}
    </span>
  );
}

function ReportList({ reports, shopName, onChanged }) {
  if (!reports.length) {
    return <p className="text-sm text-ink/70">No buyer reports yet. The score is the 50 base plus any legal bonus.</p>;
  }
  return (
    <ul className="space-y-3">
      {reports.map((report) => (
        <li key={report.id} className="rounded-2xl border border-line px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-ink">{report.ai_label || report.report_type}</p>
            <p className="font-mono text-sm text-ink/70">{signed(report.impact?.points || 0)}</p>
          </div>
          <p className="mt-1 text-xs uppercase tracking-wide text-ink/45">
            {[
              formatWhen(report.created_at),
              report.source === "social"
                ? `${report.platform || "social"}${report.author_handle ? ` @${report.author_handle}` : ""}`
                : `reporter ${report.user_phone_masked}`,
              report.verified ? "proof checked" : "",
              report.is_false_report ? "excluded" : "",
              report.impact?.recent && report.impact?.points < 0 ? "double penalty" : "",
            ]
              .filter(Boolean)
              .join(", ")}
          </p>
          <p className="mt-2 text-sm leading-relaxed text-ink/85">{report.description}</p>
          <p className="mt-2 text-xs text-ink/55">{report.impact?.reason}</p>
          {report.proof_url && (
            <a href={report.proof_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm text-signal">
              View proof
            </a>
          )}
          {report.resolved && (
            <p className="mt-2 text-xs font-medium text-signal">
              Resolved{report.resolved_by ? ` by ${report.resolved_by}` : ""}
              {report.resolved_at ? `, ${formatWhen(report.resolved_at)}` : ""}
            </p>
          )}
          {report.replies?.map((reply) => (
            <div key={reply.id} className="mt-3 rounded-xl bg-ink/5 px-3 py-2">
              <p className="text-xs uppercase tracking-wide text-ink/45">
                Reply from {reply.author}, {formatWhen(reply.created_at)}
              </p>
              <p className="mt-1 text-sm leading-relaxed text-ink/85">{reply.text}</p>
            </div>
          ))}
          <div>
            <ReplyBox report={report} shopName={shopName} onChanged={onChanged} />
            {report.ai_category === "SCAM" && !report.resolved && <ResolveButton report={report} onChanged={onChanged} />}
          </div>
        </li>
      ))}
    </ul>
  );
}

function ServicePanel({ rating }) {
  const counts = rating?.counts || { positive: 0, service: 0, scam: 0, excluded: 0 };
  const rows = [
    ["Positive reviews", counts.positive, "bg-signal"],
    ["Delivery or service", counts.service, "bg-caution"],
    ["Scam reports", counts.scam, "bg-noise"],
  ];
  const max = Math.max(1, ...rows.map((row) => row[1]));

  return (
    <div>
      {rating?.stars == null ? (
        <p className="text-sm text-ink/70">No counted buyer pattern yet.</p>
      ) : (
        <div className="flex items-end gap-3">
          <p className="font-display text-5xl leading-none">{rating.stars.toFixed(1)}</p>
          <div>
            <Stars value={rating.stars} />
            <p className="mt-1 text-sm text-ink/60">{rating.positive_pct}% of counted reports are positive</p>
          </div>
        </div>
      )}
      <div className="mt-5 space-y-3">
        {rows.map(([label, value, color]) => (
          <div key={label}>
            <div className="mb-1 flex justify-between text-sm">
              <span>{label}</span>
              <span className="font-medium">{value}</span>
            </div>
            <div className="h-2 rounded-full bg-paper">
              <div className={`h-2 rounded-full ${color}`} style={{ width: `${(value / max) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-4 text-sm text-ink/60">{counts.excluded} report{counts.excluded === 1 ? "" : "s"} excluded as spam or too thin to verify.</p>
    </div>
  );
}

function Stars({ value }) {
  return (
    <div className="flex gap-1" aria-hidden="true">
      {Array.from({ length: 5 }, (_, index) => {
        const fill = Math.max(0, Math.min(1, value - index));
        return (
          <span key={index} className="relative inline-block h-4 w-4">
            <Star className="text-line" />
            <span className="absolute inset-y-0 left-0 overflow-hidden" style={{ width: `${fill * 100}%` }}>
              <Star className="text-caution" />
            </span>
          </span>
        );
      })}
    </div>
  );
}

function Star({ className }) {
  return (
    <svg viewBox="0 0 20 20" className={`h-4 w-4 ${className}`} fill="currentColor">
      <path d="M10 1.8 12.4 7l5.6.6-4.2 3.8 1.2 5.5L10 14.2 4.9 16.9 6.1 11.4 2 7.6 7.6 7 10 1.8Z" />
    </svg>
  );
}
