// SPDX-License-Identifier: Apache-2.0
const NUMBER = new Intl.NumberFormat("en", { maximumSignificantDigits: 3 });

export function formatQuantity(value: number | null): string {
  return value === null || !Number.isFinite(value)
    ? "unknown"
    : NUMBER.format(value);
}

/**
 * A range on a track: the span from `low` to `high`, and the point estimate when there
 * is one. The numbers beside the track are the text equivalent; the track itself is
 * decoration. `min` and `max` set the scale, so bars for one objective can share it.
 */
export function RangeBar({
  label,
  low,
  high,
  point = null,
  min,
  max,
  unit = "",
  tone = "neutral",
  className,
}: {
  readonly label: string;
  readonly low: number | null;
  readonly high: number | null;
  readonly point?: number | null;
  readonly min: number;
  readonly max: number;
  readonly unit?: string;
  readonly tone?: "neutral" | "ok" | "brass" | "bad" | "unknown";
  readonly className?: string;
}) {
  const span = max - min;
  const place = (value: number | null): number | null =>
    value === null || !Number.isFinite(value) || span <= 0
      ? null
      : Math.min(100, Math.max(0, ((value - min) / span) * 100));
  const left = place(low);
  const right = place(high);
  const mark = place(point);
  const known = left !== null && right !== null;
  const text = known
    ? `${formatQuantity(low)}–${formatQuantity(high)}${unit === "" ? "" : ` ${unit}`}`
    : "unknown";
  const classes = [
    "rangebar",
    `rangebar-${known ? tone : "unknown"}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={classes}>
      <span className="rangebar-label">{label}</span>
      <span className="rangebar-track" aria-hidden="true">
        {known ? (
          <span
            className="rangebar-fill"
            style={{ left: `${left}%`, width: `${Math.max(1, right - left)}%` }}
          />
        ) : null}
        {mark === null ? null : (
          <span className="rangebar-point" style={{ left: `${mark}%` }} />
        )}
      </span>
      <span className="rangebar-text mono">{text}</span>
    </span>
  );
}
