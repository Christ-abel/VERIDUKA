import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import RegisterModal from "./components/RegisterModal";
import ReportModal from "./components/ReportModal";
import SearchBar from "./components/SearchBar";
import SmsSimulator from "./components/SmsSimulator";
import VendorDossier from "./components/VendorDossier";
import { formatPhone, handleOf } from "./format";

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

      <main className="mx-auto grid max-w-6xl items-start gap-8 px-4 py-8 lg:grid-cols-[minmax(0,1fr)_340px] lg:px-6">
        <section>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal">Noise vs signal</p>
          <h1 className="mt-3 max-w-3xl font-display text-4xl leading-[1.08] text-ink sm:text-5xl">
            VeriDuka. Filter out online shopping noise with verified trust signals
          </h1>
          <p className="mt-4 max-w-2xl text-lg leading-relaxed text-ink/75">
            Ghost shops hide behind new Instagram accounts, borrowed paybills, and reviews that never describe an order.
            VeriDuka reads the legal record and the buyer reports that do.
          </p>
          <SignalCompare />
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
                onReport={() =>
                  openReport({
                    vendorId: vendor.id,
                    vendorName: vendor.name,
                    identifier: vendor.paybill || vendor.phone || (vendor.instagram ? `@${vendor.instagram}` : vendor.name),
                  })
                }
              />
            ) : (
              <Directory
                shops={directory}
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
        <div className="lg:sticky lg:top-6">
          <SmsSimulator />
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

function Directory({ shops, booting, query, missing, onOpen, onReportUnknown, suppressEmpty }) {
  if (booting) {
    return <p className="text-sm text-ink/60">Opening the signal room…</p>;
  }
  return (
    <div>
      <div className="mb-4 flex items-end justify-between gap-3">
        <h2 className="font-display text-3xl">{query.trim() ? "Matches" : "Shops on file"}</h2>
        <p className="text-sm text-ink/50">{shops.length} signal{shops.length === 1 ? "" : "s"}</p>
      </div>
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
        {shops.length === 0 && !missing && !suppressEmpty && (
        <p className="rounded-2xl bg-card px-4 py-6 text-sm text-ink/70">No shop matches that yet. Check the spelling, or file a report.</p>
      )}
      <div className="grid gap-3">
        {shops.map((shop) => (
          <ShopCard key={shop.id} shop={shop} onOpen={() => onOpen(shop.id)} />
        ))}
      </div>
    </div>
  );
}

function ShopCard({ shop, onOpen }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-[24px] border border-line bg-card p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-ink/20"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-ink/45">
            {shop.category}
            {shop.match_field !== "directory" && shop.match_field !== "name" ? `, matched ${shop.match_field.replace("_", " ")}` : ""}
          </p>
          <h3 className="mt-1 font-display text-2xl leading-tight">{shop.name}</h3>
          <p className="mt-1 text-sm text-ink/65">{shop.location}</p>
        </div>
        <div className="text-right">
          <p className={`font-display text-4xl leading-none ${shop.band === "VERIFIED_SIGNAL" ? "text-signal" : shop.band === "MODERATE_RISK" ? "text-caution" : "text-noise"}`}>{shop.score}</p>
          <p className="mt-1 max-w-28 text-[11px] font-semibold uppercase tracking-wide text-ink/50">{shop.label}</p>
        </div>
      </div>
      <p className="mt-3 text-sm text-ink/70">
        {[
          shop.paybill ? `Paybill ${shop.paybill}` : null,
          shop.phone ? formatPhone(shop.phone) : null,
          shop.instagram ? handleOf(shop.instagram) : null,
          shop.kra_pin || null,
        ]
          .filter(Boolean)
          .join(", ")}
      </p>
    </button>
  );
}

function SignalCompare() {
  return (
    <div className="mt-6 grid max-w-xl grid-cols-2 gap-4">
      <div>
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
      </div>
      <div>
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
      </div>
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
