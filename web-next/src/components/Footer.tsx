import { Calendar, standardDate } from "@/lib/dates.ts";

export default function Footer({ win }: { win?: { from: string; to: string } }) {
  const cal = win && new Calendar(win.from);
  return (
    <footer className="foot" id="footer">
      {win && cal && (
        <p>
          Data from {standardDate(cal.date(0))} to {standardDate(cal.date(cal.day(win.to)))} (UTC), from the public GitHub
          repositories of the WHATWG’s Living Standards. An item is counted as open from its creation to its last close.
        </p>
      )}
      <p>
        Not affiliated with the WHATWG. Source and data:{" "}
        <a href="https://github.com/foolip/spec-stats">foolip/spec-stats</a>.
      </p>
    </footer>
  );
}
