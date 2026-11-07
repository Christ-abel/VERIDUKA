export function formatPhone(local) {
  if (!local) return "";
  const digits = String(local).replace(/\D/g, "");
  if (digits.length !== 10) return local;
  return `${digits.slice(0, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`;
}

export function formatWhen(iso) {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const days = Math.floor((Date.now() - then.getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  return then.toLocaleDateString("en-KE", { day: "numeric", month: "short", year: "numeric" });
}

export function handleOf(value) {
  if (!value) return "";
  return value.startsWith("@") ? value : `@${value}`;
}

export function tone(band) {
  if (band === "VERIFIED_SIGNAL") return "signal";
  if (band === "MODERATE_RISK") return "caution";
  return "noise";
}

export function signed(value) {
  if (value > 0) return `+${value}`;
  return String(value);
}
