export default function SearchBar({ value, onChange, onSubmit, onExample, loading }) {
  const examples = [
    { label: "Paybill 400200", value: "400200" },
    { label: "@trendyclothez_ke", value: "@trendyclothez_ke" },
    { label: "0722 113 344", value: "0722113344" },
    { label: "KRA P051987654Z", value: "P051987654Z" },
  ];

  return (
    <form
      className="mt-8"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label htmlFor="shop-search" className="text-sm font-medium text-ink">
        Search a shop
      </label>
      <div className="mt-2 flex flex-col gap-2 sm:flex-row">
        <input
          id="shop-search"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Paybill, phone, @handle, shop name, or KRA PIN"
          autoComplete="off"
          className="w-full rounded-full border border-line bg-card px-5 py-3.5 text-base text-ink shadow-sm outline-none ring-signal/30 placeholder:text-ink/40 focus:ring-2"
        />
        <button
          type="submit"
          className="rounded-full bg-deep px-6 py-3.5 text-sm font-semibold tracking-wide text-paper transition hover:bg-ink disabled:opacity-60"
          disabled={loading}
        >
          {loading ? "Checking…" : "Check signal"}
        </button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {examples.map((example) => (
          <button
            key={example.value}
            type="button"
            onClick={() => onExample(example.value)}
            className="rounded-full border border-line bg-card/70 px-3 py-1.5 text-sm text-ink/80 transition hover:border-signal hover:text-ink"
          >
            {example.label}
          </button>
        ))}
      </div>
    </form>
  );
}
