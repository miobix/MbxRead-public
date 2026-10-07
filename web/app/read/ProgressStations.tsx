const STOPS = 10;

/** Reading progress drawn as a metro line: a stop at every 10% of the text, the
 *  reader sitting on the nearest one, with the exact percentage under it. */
export function ProgressStations({ percent }: { percent: number }) {
  const here = Math.round(percent / (100 / STOPS));

  return (
    <div
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Reading progress"
      className="relative flex justify-between"
    >
      <span className="absolute left-[11px] right-[11px] top-[6px] h-1 rounded-full bg-line" />
      <span
        className="absolute left-[11px] top-[6px] h-1 rounded-full bg-accent"
        style={{ width: `calc((100% - 22px) * ${here / STOPS})` }}
      />
      {Array.from({ length: STOPS + 1 }, (_, n) => (
        <span
          key={n}
          className="relative z-10 flex w-[22px] min-h-[32px] flex-col items-center gap-1 text-[11px] tabular-nums"
        >
          <span
            className={
              n === here
                ? "h-4 w-4 rounded-full border-4 border-accent bg-paper"
                : `mt-[3px] h-2.5 w-2.5 rounded-full border-2 bg-paper ${
                    n < here ? "border-accent" : "border-line"
                  }`
            }
          />
          {n === here && <span className="font-semibold text-ink">{percent}%</span>}
        </span>
      ))}
    </div>
  );
}
