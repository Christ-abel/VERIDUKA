import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const PRESETS = [
  "VERIFY 400200",
  "COMMENTS 400200",
  "NEXT",
  "VERIFY 522522",
  "HELP",
];

let messageId = 1;

export default function SmsSimulator() {
  const [draft, setDraft] = useState("VERIFY 400200");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: messageId++,
      role: "in",
      text: "VERIFY checks a shop. COMMENTS reads reviews one by one. NEXT for the next review. REGISTER Name, 07..., paybill.",
      meta: "ThriveWave sandbox",
    },
  ]);
  const threadRef = useRef(null);

  useEffect(() => {
    const node = threadRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, busy]);

  async function send(text) {
    const outbound = text.trim();
    if (!outbound || busy) return;
    setMessages((current) => [...current, { id: messageId++, role: "out", text: outbound }]);
    setDraft("");
    setBusy(true);
    try {
      const data = await api.sms({ text: outbound, from: "0711000111" });
      setMessages((current) => [
        ...current,
        {
          id: messageId++,
          role: "in",
          text: data.reply,
          meta: `${data.dispatch.status} ${data.dispatch.provider_ref}`,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { id: messageId++, role: "in", text: error.message, meta: "delivery failed" },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="mx-auto w-full max-w-sm lg:mx-0">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-display text-2xl text-ink">SMS sandbox</h2>
        <p className="text-xs uppercase tracking-[0.14em] text-ink/50">ThriveWave</p>
      </div>
      <div className="rounded-[2rem] border border-ink bg-deep p-3 shadow-card">
        <div className="overflow-hidden rounded-[1.4rem] bg-[#f4efe4]">
          <div className="flex items-center justify-between bg-[#173528] px-4 py-3 text-[#f3ecdf]">
            <div>
              <p className="text-[10px] uppercase tracking-[0.16em] text-[#b7c9bc]">Sender ID</p>
              <p className="font-semibold">VERIDUKA</p>
            </div>
            <p className="text-xs text-[#b7c9bc]">0711 000 111</p>
          </div>
          <div ref={threadRef} className="flex h-[26rem] flex-col gap-3 overflow-y-auto px-3 py-4">
            {messages.map((message) => (
              <div key={message.id} className={message.role === "out" ? "ml-8 self-end" : "mr-8 self-start"}>
                <p
                  className={`rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                    message.role === "out" ? "rounded-br-md bg-deep text-paper" : "rounded-bl-md bg-white text-ink"
                  }`}
                >
                  {message.text}
                </p>
                {message.meta && <p className="mt-1 px-1 text-[10px] uppercase tracking-wide text-ink/45">{message.meta}</p>}
              </div>
            ))}
            {busy && <p className="text-xs text-ink/50">Scoring the till…</p>}
          </div>
          <form
            className="flex gap-2 border-t border-line bg-white p-3"
            onSubmit={(event) => {
              event.preventDefault();
              send(draft);
            }}
          >
            <label className="sr-only" htmlFor="sms-draft">
              SMS text
            </label>
            <input
              id="sms-draft"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="VERIFY 400200"
              className="w-full rounded-full border border-line px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-signal/30"
            />
            <button
              type="submit"
              disabled={busy}
              className="rounded-full bg-signal px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
            >
              Send
            </button>
          </form>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => send(preset)}
            className="rounded-full border border-line bg-card px-3 py-1.5 text-xs font-medium text-ink/80 hover:border-signal"
          >
            {preset}
          </button>
        ))}
      </div>
      <p className="mt-3 text-xs leading-relaxed text-ink/60">
        The phone calls the same webhook a ThriveWave inbound message would hit. Dispatch stays mocked unless THRIVEWAVE_LIVE is on.
      </p>
    </aside>
  );
}
