import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import RegisterModal from "./components/RegisterModal";
import ReportModal from "./components/ReportModal";
import SearchBar from "./components/SearchBar";
import SmsSimulator from "./components/SmsSimulator";
import VendorDossier from "./components/VendorDossier";
import { formatPhone, handleOf, whatsappUrl } from "./format";

const BANDS = [
  { id: "", label: "All shops" },
  { id: "VERIFIED_SIGNAL", label: "Verified signal" },
  { id: "MODERATE_RISK", label: "Moderate risk" },
  { id: "HIGH_NOISE", label: "Fraud alert" },
];

export default function App() {
  const [query, setQuery] = useState("");
  const [directory, setDirectory] = useState([]);
  const [vendor, setVendor] = useState(null);
  const [searching, setSearching] = useState(false);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState("");
  const [reportSeed, setReportSeed] = useState(null);
  const [registering, setRegistering] = useState(false);
  const [band, setBand] = useState("");
  const [picked, setPicked] = useState([]);
  const [comparing, setComparing] = useState(false);
  const [smsJob, setSmsJob] = useState(null);
  const smsJobId = useRef(0);
  const explicit = useRef(false);
  const requestId = useRef(0);

  useEffect(() => {
    if (explicit.current) {
      explicit.current = false;
      return undefined;
    }
    const handle = setTimeout(() => {
      loadDirectory(query);
    }, query ? 280 : 0);
    return () => clearTimeout(handle);
  }, [query]);

  async function loadDirectory(nextQuery) {
    const id = ++requestId.current;
    if (nextQuery.trim()) setSearching(true);
    try {
      const data = await api.search(nextQuery.trim());
      if (id !== requestId.current) return null;
      setDirectory(data.results);
      setError("");
      return data;
    } catch (err) {
      if (id === requestId.current) setError(err.message);
      return null;
    } finally {
      if (id === requestId.current) {
        setSearching(false);
        setBooting(false);
      }
    }
  }

  async function commitSearch(next = query) {
    if (next !== query) explicit.current = true;
    setQuery(next);
    setMissing("");
    setSearching(true);
    const data = await loadDirectory(next);
    if (!data) return;
    if (!next.trim()) {
      setVendor(null);
      return;
    }
    const top = data.results[0];
    if (!top) {
      setVendor(null);
      setMissing(next.trim());
      return;
    }
    if (data.results.length === 1 || top.match_field !== "name") {
      await openVendor(top.id);
    } else {
      setVendor(null);
    }
  }

  async function openVendor(id) {
    try {
      const detail = await api.vendor(id);
      setVendor(detail);
      setMissing("");
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshVendor() {
    if (!vendor) return;
    await openVendor(vendor.id);
    await loadDirectory(query);
  }

  function openReport(seed) {
    setReportSeed(seed);
  }

  function queueSms(text) {
    smsJobId.current += 1;
    setSmsJob({ id: smsJobId.current, text });
  }

  function togglePick(shop) {
    setPicked((current) => {
      if (current.some((item) => item.id === shop.id)) return current.filter((item) => item.id !== shop.id);
      if (current.length >= 3) return current;
      return [...current, shop];
    });
  }

  function chooseBand(next) {
    setBand(next);
    setVendor(null);
    setComparing(false);
  }

  return (
    <div className="min-h-screen text-ink">
      <header className="border-b border-white/10 bg-deep text-[#f3ecdf]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 lg:px-6">
          <div className="flex items-center gap-3">
            <SignalMark />
            <div>
              <p className="font-display text-2xl leading-none">VeriDuka</p>
              <p className="mt-1 text-[11px] uppercase tracking-[0.18em] text-[#c5d5c9]">Merchant trust signals</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <p className="hidden text-sm text-[#c5d5c9] sm:block">Zinduathon 3.0</p>
            <button
              type="button"
              onClick={() => setRegistering(true)}
              className="rounded-full bg-[#f3ecdf] px-3 py-1.5 text-sm font-semibold text-deep"
            >
              Register a shop
            </button>
            <button
              type="button"
              onClick={() => openReport({ vendorId: null, vendorName: "", identifier: query.trim() })}
              className="rounded-full border border-white/20 px-3 py-1.5 text-sm"
            >
              Report a shop
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid min-w-0 max-w-6xl items-start gap-8 px-4 py-8 lg:grid-cols-[minmax(0,1fr)_340px] lg:px-6">
        <section className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal">Noise vs signal</p>
          <h1 className="mt-3 max-w-3xl font-display text-4xl leading-[1.08] text-ink sm:text-5xl">
            VeriDuka. Filter out online shopping noise with verified trust signals
          </h1>
          <p className="mt-4 max-w-2xl text-lg leading-relaxed text-ink/75">
            Ghost shops hide behind new Instagram accounts, borrowed paybills, and reviews that never describe an order.
            VeriDuka reads the legal record and the buyer reports that do.
          </p>
          <SignalCompare onPick={chooseBand} active={band} />
          <SearchBar
            value={query}
            onChange={setQuery}
            onSubmit={() => commitSearch(query)}
            onExample={(value) => commitSearch(value)}
            loading={searching}
          />
          <p className="mt-4 text-sm text-ink/60">
            Base 50. Legal match +25. Verified praise +5, up to +20. Scam -20. Delay or poor service -5. Complaints under 30 days count double. Instagram, Facebook, and TikTok are links you open yourself.
          </p>

          {error && (
            <p role="alert" className="mt-4 rounded-2xl bg-[#f8e4df] px-4 py-3 text-sm text-noise">
              {error}
            </p>
          )}

          <div className="mt-8">
            {vendor ? (
              <VendorDossier
                vendor={vendor}
                onBack={() => setVendor(null)}
                onChanged={refreshVendor}
                onSms={queueSms}
                onReport={() =>
                  openReport({
                    vendorId: vendor.id,
                    vendorName: vendor.name,
                    identifier: vendor.paybill || vendor.phone || (vendor.instagram ? `@${vendor.instagram}` : vendor.name),
                  })
                }
              />
            ) : comparing ? (
              <CompareBoard
                shops={picked}
                onClose={() => setComparing(false)}
                onOpen={(id) => {
                  setComparing(false);
                  openVendor(id);
                }}
              />
            ) : (
              <Directory
                shops={directory}
                band={band}
                onBand={chooseBand}
                picked={picked}
                onToggle={togglePick}
                onCompare={() => setComparing(true)}
                onClear={() => setPicked([])}
                booting={booting}
                query={query}
                missing={missing}
                onOpen={openVendor}
                onReportUnknown={() => openReport({ vendorId: null, vendorName: "", identifier: missing })}
                suppressEmpty={Boolean(error)}
              />
            )}
          </div>
          <footer className="mt-10 text-sm leading-relaxed text-ink/55">
            Scores are decision signals, not a promise of a perfect order. Confirm the till name inside M-Pesa before you pay.
            Legal checks use a mock BRS and KRA file so the prototype runs without government credentials.
          </footer>
        </section>
        <div className="min-w-0 lg:sticky lg:top-6">
          <SmsSimulator job={smsJob} />
        </div>
      </main>

      {registering && (
        <RegisterModal
          onClose={() => setRegistering(false)}
          onCreated={async (created) => {
            setRegistering(false);
            await loadDirectory("");
            setQuery("");
            await openVendor(created.id);
          }}
        />
      )}

      {reportSeed && (
        <ReportModal
          seed={reportSeed}
          onClose={() => setReportSeed(null)}
          onSubmitted={async (created) => {
            setReportSeed(null);
            await openVendor(created.vendor_id);
            await loadDirectory(query);
          }}
        />
      )}
    </div>
  );
}

function Directory({
  shops,
  band,
  onBand,
  picked,
  onToggle,
  onCompare,
  onClear,
  booting,
  query,
  missing,
  onOpen,
  onReportUnknown,
  suppressEmpty,
}) {
  if (booting) {
    return <p className="text-sm text-ink/60">Opening the signal room…</p>;
  }
  const visible = shops.filter((shop) => !band || shop.band === band);
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h2 className="font-display text-3xl">{query.trim() ? "Matches" : "Shops on file"}</h2>
        <p className="text-sm text-ink/50">{visible.length} signal{visible.length === 1 ? "" : "s"}</p>
      </div>
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter by band">
        {BANDS.map((item) => (
          <button
            key={item.id || "all"}
            type="button"
            aria-pressed={band === item.id}
            onClick={() => onBand(item.id)}
            className={`rounded-full border px-3 py-1.5 text-sm font-medium ${
              band === item.id ? "border-ink bg-ink text-paper" : "border-line bg-card text-ink/75"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      {picked.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-card px-4 py-3">
          <p className="text-sm text-ink/75">{picked.length} selected. Compare up to 3 shops on one poster.</p>
          <div className="flex gap-2">
            <button type="button" onClick={onClear} className="rounded-full px-3 py-1.5 text-sm text-ink/60">
              Clear
            </button>
            <button
              type="button"
              onClick={onCompare}
              disabled={picked.length < 2}
              className="rounded-full bg-ink px-4 py-1.5 text-sm font-semibold text-paper disabled:opacity-40"
            >
              Compare
            </button>
          </div>
        </div>
      )}
      {missing && (
        <div className="mb-4 rounded-[24px] border border-noise/30 bg-[#f8e4df] p-4">
          <p className="font-semibold text-noise">No trusted record for {missing}.</p>
          <p className="mt-1 text-sm leading-relaxed text-ink/75">
            Silence is not a clean bill of health. Treat an unknown paybill as unverified noise until a real order is on file.
          </p>
          <button type="button" onClick={onReportUnknown} className="mt-3 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper">
            Report this identifier
          </button>
        </div>
      )}
        {visible.length === 0 && !missing && !suppressEmpty && (
        <p className="rounded-2xl bg-card px-4 py-6 text-sm text-ink/70">No shop matches that yet. Check the spelling, or file a report.</p>
      )}
      <div className="grid gap-3">
        {visible.map((shop) => (
          <ShopCard
            key={shop.id}
            shop={shop}
            picked={picked.some((item) => item.id === shop.id)}
            onOpen={() => onOpen(shop.id)}
            onToggle={() => onToggle(shop)}
          />
        ))}
      </div>
    </div>
  );
}

function ShopCard({ shop, picked, onOpen, onToggle }) {
  return (
    <article className={`rounded-[24px] border bg-card p-4 shadow-sm transition hover:-translate-y-0.5 ${picked ? "border-signal ring-2 ring-signal/30" : "border-line hover:border-ink/20"}`}>
      <div className="flex items-start justify-between gap-4">
        <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left">
          <p className="text-xs uppercase tracking-[0.14em] text-ink/45">
            {shop.category}
            {shop.match_field !== "directory" && shop.match_field !== "name" ? `, matched ${shop.match_field.replace("_", " ")}` : ""}
          </p>
          <h3 className="mt-1 font-display text-2xl leading-tight">{shop.name}</h3>
          <p className="mt-1 text-sm text-ink/65">{shop.location}</p>
        </button>
        <button type="button" onClick={onOpen} className="text-right">
          <p className={`font-display text-4xl leading-none ${shop.band === "VERIFIED_SIGNAL" ? "text-signal" : shop.band === "MODERATE_RISK" ? "text-caution" : "text-noise"}`}>{shop.score}</p>
          <p className="mt-1 max-w-28 text-[11px] font-semibold uppercase tracking-wide text-ink/50">{shop.label}</p>
        </button>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink/70">
          {[
            shop.paybill ? `Paybill ${shop.paybill}` : null,
            shop.phone ? formatPhone(shop.phone) : null,
            shop.instagram ? handleOf(shop.instagram) : null,
            shop.kra_pin || null,
          ]
            .filter(Boolean)
            .join(", ")}
        </p>
        <button
          type="button"
          aria-pressed={picked}
          onClick={onToggle}
          className={`rounded-full border px-3 py-1 text-xs font-semibold ${picked ? "border-signal bg-signal/10 text-signal" : "border-line text-ink/70"}`}
        >
          {picked ? "Selected" : "Compare"}
        </button>
      </div>
    </article>
  );
}

function CompareBoard({ shops, onClose, onOpen }) {
  const best = Math.max(...shops.map((shop) => shop.score));
  return (
    <div>
      <button type="button" onClick={onClose} className="text-sm font-medium text-signal hover:underline">
        Back to the list
      </button>
      <h2 className="mt-3 font-display text-3xl">Side by side</h2>
      <p className="mt-1 text-sm text-ink/65">The higher score is the stronger signal. Read the advice before you pay.</p>
      <div className={`mt-4 grid gap-3 ${shops.length > 2 ? "md:grid-cols-3" : "md:grid-cols-2"}`}>
        {shops.map((shop) => {
          const chat = whatsappUrl(
            shop.phone,
            `I compared shops on VeriDuka. ${shop.name} scores ${shop.score}. Is this paybill still yours?`,
          );
          return (
            <article key={shop.id} className={`rounded-[24px] border bg-card p-4 ${shop.score === best ? "border-signal" : "border-line"}`}>
              <p className="text-xs uppercase tracking-[0.14em] text-ink/45">{shop.score === best ? "Stronger signal" : shop.category}</p>
              <h3 className="mt-1 font-display text-2xl leading-tight">{shop.name}</h3>
              <p className={`mt-2 font-display text-5xl ${shop.band === "VERIFIED_SIGNAL" ? "text-signal" : shop.band === "MODERATE_RISK" ? "text-caution" : "text-noise"}`}>{shop.score}</p>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink/50">{shop.label}</p>
              <p className="mt-3 text-sm leading-relaxed text-ink/75">{shop.advice}</p>
              <ul className="mt-3 space-y-1 text-sm text-ink/70">
                <li>{shop.paybill ? `Paybill ${shop.paybill}` : "No paybill"}</li>
                <li>{shop.kra_status === "verified" ? "Active KRA" : "KRA not active"}</li>
                <li>{shop.brs_status === "verified" ? "BRS registered" : "BRS not registered"}</li>
                <li>{shop.mpesa_verified ? "M-Pesa verified" : "M-Pesa not verified"}</li>
              </ul>
              <div className="mt-4 flex flex-wrap gap-2">
                <button type="button" onClick={() => onOpen(shop.id)} className="rounded-full bg-ink px-3 py-1.5 text-sm font-semibold text-paper">
                  Open
                </button>
                {chat && (
                  <a href={chat} target="_blank" rel="noreferrer" className="rounded-full border border-ink px-3 py-1.5 text-sm font-semibold">
                    WhatsApp
                  </a>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function SignalCompare({ onPick, active }) {
  return (
    <div className="mt-6 grid max-w-xl grid-cols-2 gap-4">
      <button type="button" onClick={() => onPick(active === "HIGH_NOISE" ? "" : "HIGH_NOISE")} className={`rounded-2xl p-2 text-left ${active === "HIGH_NOISE" ? "bg-noise/10" : ""}`}>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-noise">Noise</p>
        <div className="mt-2 flex h-14 items-end gap-1" aria-hidden="true">
          {[30, 80, 20, 90, 40, 70, 25, 85].map((height, index) => (
            <span
              key={index}
              className="noise-bar w-1.5 rounded-full bg-noise/80"
              style={{ height: `${height}%`, animationDelay: `${index * 0.07}s` }}
            />
          ))}
        </div>
        <p className="mt-2 text-sm text-ink/65">Fake praise, unverified tills, shops that vanish after payment.</p>
      </button>
      <button type="button" onClick={() => onPick(active === "VERIFIED_SIGNAL" ? "" : "VERIFIED_SIGNAL")} className={`rounded-2xl p-2 text-left ${active === "VERIFIED_SIGNAL" ? "bg-signal/10" : ""}`}>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-signal">Signal</p>
        <div className="mt-2 flex h-14 items-end gap-1" aria-hidden="true">
          {[45, 62, 78, 90, 84, 96, 88, 100].map((height, index) => (
            <span
              key={index}
              className="eq-bar w-1.5 rounded-full bg-signal"
              style={{ height: `${height}%`, animationDelay: `${index * 0.12}s` }}
            />
          ))}
        </div>
        <p className="mt-2 text-sm text-ink/65">KRA, BRS, and reports that describe a real order.</p>
      </button>
    </div>
  );
}

function SignalMark() {
  return (
    <svg viewBox="0 0 36 36" className="h-9 w-9" aria-hidden="true">
      <rect x="4" y="20" width="6" height="12" rx="1.5" fill="#d7c4a3" />
      <rect x="15" y="12" width="6" height="20" rx="1.5" fill="#8fbf9b" />
      <rect x="26" y="4" width="6" height="28" rx="1.5" fill="#3dbe74" />
    </svg>
  );
}
