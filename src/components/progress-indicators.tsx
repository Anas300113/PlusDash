"use client";

export function DailyRing({ value, label }: { value: number; label: string }) {
  const radius = 31;
  const circumference = 2 * Math.PI * radius;
  const dash = circumference * value / 100;

  return (
    <div className="daily-ring" role="img" aria-label={label}>
      <svg viewBox="0 0 76 76" aria-hidden="true">
        <circle className="ring-track" cx="38" cy="38" r={radius} />
        <circle
          className="ring-progress"
          cx="38"
          cy="38"
          r={radius}
          strokeDasharray={`${dash} ${circumference}`}
          strokeDashoffset={0}
        />
      </svg>
      <span className="ring-center">
        <strong>18</strong>
        <small>of 30 min</small>
      </span>
    </div>
  );
}

export function MasteryBar({ value, label }: { value: number; label: string }) {
  return (
    <div
      className="mastery-track"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
      aria-valuetext={`${value}% mastered`}
    >
      <span className="mastery-fill" style={{ width: `${value}%` }} />
    </div>
  );
}
