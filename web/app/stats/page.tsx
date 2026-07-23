"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type Stats } from "@/lib/api";

export default function StatsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getStats()
      .then(setStats)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load stats."));
  }, []);

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <Link href="/" className="text-sm text-muted hover:text-ink transition-colors">
          ← Books
        </Link>
        <h1 className="text-2xl font-semibold font-serif">Stats</h1>
      </div>

      {error && <p className="text-danger text-sm">{error}</p>}
      {!stats && !error && <p className="text-muted">Loading…</p>}

      {stats && (
        <>
          <HeroRow stats={stats} />
          <Heatmap stats={stats} />
          <NewWordsPerBook stats={stats} />
          <VocabDepth stats={stats} />
          <Milestones stats={stats} />
        </>
      )}
    </main>
  );
}

/* ---------- Hero numbers ---------- */

function HeroRow({ stats }: { stats: Stats }) {
  const { totals, streak } = stats;
  const tiles = [
    { label: "Words learned", value: totals.words_total, hint: `${totals.words_known} known` },
    { label: "Day streak", value: streak.current, hint: `best ${streak.longest} 🔥` },
    { label: "Books finished", value: totals.books_finished, hint: "" },
    { label: "This week", value: totals.words_week, hint: `${totals.pages_week} pages` },
  ];
  return (
    <section className="grid grid-cols-2 gap-3">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-xl border border-border bg-surface p-4 shadow-sm">
          <div className="text-3xl font-semibold font-serif text-ink tabular-nums">{t.value}</div>
          <div className="text-sm text-muted mt-0.5">{t.label}</div>
          {t.hint && <div className="text-xs text-muted mt-0.5">{t.hint}</div>}
        </div>
      ))}
    </section>
  );
}

/* ---------- Activity heatmap (GitHub-style) ---------- */

const DAY_MS = 24 * 60 * 60 * 1000;

function localISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

function intensity(count: number): number {
  if (count <= 0) return 0;
  if (count <= 2) return 1;
  if (count <= 5) return 2;
  if (count <= 10) return 3;
  return 4;
}

function Heatmap({ stats }: { stats: Stats }) {
  const weeks = useMemo(() => {
    const counts = new Map(stats.activity.map((a) => [a.date, a.words + a.pages]));
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const start = new Date(today.getTime() - 363 * DAY_MS);
    start.setDate(start.getDate() - start.getDay()); // back up to Sunday

    const days: { date: string; count: number }[] = [];
    for (let t = start.getTime(); t <= today.getTime(); t += DAY_MS) {
      const iso = localISO(new Date(t));
      days.push({ date: iso, count: counts.get(iso) ?? 0 });
    }
    const chunked: { date: string; count: number }[][] = [];
    for (let i = 0; i < days.length; i += 7) chunked.push(days.slice(i, i + 7));
    return chunked;
  }, [stats.activity]);

  const activeDays = stats.activity.filter((a) => a.words + a.pages > 0).length;

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-medium text-muted">Activity</h2>
        <span className="text-xs text-muted">{activeDays} active days</span>
      </div>
      <div className="overflow-x-auto">
        <div className="flex gap-[3px]">
          {weeks.map((week, wi) => (
            <div key={wi} className="flex flex-col gap-[3px]">
              {week.map((day) => {
                const level = intensity(day.count);
                return (
                  <div
                    key={day.date}
                    title={`${day.date}: ${day.count} action${day.count === 1 ? "" : "s"}`}
                    className="w-[11px] h-[11px] rounded-[2px]"
                    style={{
                      backgroundColor:
                        level === 0 ? "var(--color-border)" : "var(--color-accent)",
                      opacity: level === 0 ? 0.4 : 0.25 + level * 0.1875,
                    }}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-1 text-xs text-muted self-end">
        <span>less</span>
        {[0, 1, 2, 3, 4].map((level) => (
          <span
            key={level}
            className="w-[11px] h-[11px] rounded-[2px]"
            style={{
              backgroundColor: level === 0 ? "var(--color-border)" : "var(--color-accent)",
              opacity: level === 0 ? 0.4 : 0.25 + level * 0.1875,
            }}
          />
        ))}
        <span>more</span>
      </div>
    </section>
  );
}

/* ---------- New words per book (line — watch it flatten) ---------- */

function NewWordsPerBook({ stats }: { stats: Stats }) {
  const rows = stats.new_words_per_book;
  if (rows.length === 0) {
    return (
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-muted">New words per book</h2>
        <p className="text-xs text-muted">
          Save words while reading and this line appears — watch it flatten as a genre or
          author stops surprising you.
        </p>
      </section>
    );
  }

  const W = 320;
  const H = 120;
  const pad = { l: 8, r: 8, t: 10, b: 10 };
  const max = Math.max(...rows.map((r) => r.new_words), 1);
  const x = (i: number) =>
    rows.length === 1
      ? W / 2
      : pad.l + (i * (W - pad.l - pad.r)) / (rows.length - 1);
  const y = (v: number) => pad.t + (1 - v / max) * (H - pad.t - pad.b);
  const points = rows.map((r, i) => `${x(i)},${y(r.new_words)}`).join(" ");

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-medium text-muted">New words per book</h2>
      <div className="rounded-xl border border-border bg-surface p-3 shadow-sm">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="New words per book">
          <polyline
            points={points}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {rows.map((r, i) => (
            <circle key={r.book_id} cx={x(i)} cy={y(r.new_words)} r={3} fill="var(--color-accent)">
              <title>
                {r.title}: {r.new_words} new
                {r.pages_read > 0 ? ` · ${(r.new_words / r.pages_read).toFixed(1)}/pg` : ""}
              </title>
            </circle>
          ))}
        </svg>
      </div>
      <p className="text-xs text-muted">
        {rows.length} book{rows.length === 1 ? "" : "s"} · newest on the right
      </p>
    </section>
  );
}

/* ---------- Vocab depth by NIKL grade ---------- */

const GRADE_META: { key: "A" | "B" | "C" | "unlisted"; label: string; color: string }[] = [
  { key: "A", label: "Beginner", color: "var(--color-accent)" },
  { key: "B", label: "Intermediate", color: "var(--color-highlight)" },
  { key: "C", label: "Advanced", color: "var(--color-danger)" },
  { key: "unlisted", label: "Off-list", color: "var(--color-border)" },
];

function VocabDepth({ stats }: { stats: Stats }) {
  const { buckets, beginner_pct } = stats.vocab_depth;
  const total = buckets.A + buckets.B + buckets.C + buckets.unlisted;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-medium text-muted">Vocabulary depth</h2>
      <div className="rounded-xl border border-border bg-surface p-4 shadow-sm flex flex-col gap-3">
        {beginner_pct !== null && (
          <div className="text-sm text-ink">
            You know{" "}
            <span className="font-semibold text-accent">{Math.round(beginner_pct * 100)}%</span>{" "}
            of beginner Korean vocabulary.
          </div>
        )}
        {total === 0 ? (
          <p className="text-xs text-muted">Save some words to see your vocabulary breakdown.</p>
        ) : (
          <>
            <div className="flex h-3 w-full overflow-hidden rounded-full">
              {GRADE_META.map((g) => {
                const v = buckets[g.key];
                if (v === 0) return null;
                return (
                  <div
                    key={g.key}
                    style={{ width: `${(v / total) * 100}%`, backgroundColor: g.color }}
                    title={`${g.label}: ${v}`}
                  />
                );
              })}
            </div>
            <div className="grid grid-cols-2 gap-1.5 text-xs">
              {GRADE_META.map((g) => (
                <div key={g.key} className="flex items-center gap-1.5 text-muted">
                  <span
                    className="w-2.5 h-2.5 rounded-sm shrink-0"
                    style={{ backgroundColor: g.color }}
                  />
                  {g.label}
                  <span className="text-ink tabular-nums ml-auto">{buckets[g.key]}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

/* ---------- Milestone badges ---------- */

function nextMilestone(value: number, tiers: number[]): number | null {
  return tiers.find((t) => t > value) ?? null;
}

function Milestones({ stats }: { stats: Stats }) {
  const wordTiers = [50, 100, 250, 500, 1000, 2500, 5000];
  const streakTiers = [3, 7, 14, 30, 100, 365];
  const bookTiers = [1, 5, 10, 25, 50];

  const badges: { label: string; done: boolean }[] = [];
  const push = (value: number, tiers: number[], fmt: (t: number) => string) => {
    tiers.forEach((t) => badges.push({ label: fmt(t), done: value >= t }));
    const next = nextMilestone(value, tiers);
    return next;
  };

  push(stats.totals.words_total, wordTiers, (t) => `${t} words`);
  push(stats.streak.longest, streakTiers, (t) => `${t}-day streak`);
  push(stats.totals.books_finished, bookTiers, (t) => `${t} books`);

  return (
    <section className="flex flex-col gap-2 pb-4">
      <h2 className="text-sm font-medium text-muted">Milestones</h2>
      <div className="flex flex-wrap gap-2">
        {badges.map((b) => (
          <span
            key={b.label}
            className={`rounded-full px-3 py-1 text-xs border transition-colors ${
              b.done
                ? "bg-accent text-accent-ink border-accent"
                : "border-border text-muted opacity-60"
            }`}
          >
            {b.done ? "★ " : ""}
            {b.label}
          </span>
        ))}
      </div>
    </section>
  );
}
