"use client";

import { useSyncExternalStore } from "react";

/**
 * Epic 24: how many rendered lines one reader page holds.
 *
 * This is deliberately a **per-device** setting in localStorage rather than a server
 * setting: a phone fits ~20 Korean characters per line and a laptop ~27, so a single
 * shared value can only ever be right on one of them. The reader lays pages out with
 * CSS columns (`height: Nlh`), so the browser breaks after exactly this many *real*
 * lines — this is an exact count, not the estimate the retired `page_rows` /
 * `chars_per_row` pair tried to be.
 *
 * Exposed through useSyncExternalStore rather than useState + useEffect so that
 * (a) the prerendered static export and the first client render agree — the server
 * snapshot is the default, and (b) changing it on /settings updates an open reader
 * without a reload, including in another tab via the `storage` event.
 */
const LINES_KEY = "readerLines";

export const DEFAULT_LINES = 15;
export const MIN_LINES = 5;
export const MAX_LINES = 40;

const listeners = new Set<() => void>();

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  // `storage` only fires for *other* tabs, hence the in-process listener set too.
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

function getSnapshot(): number {
  const raw = window.localStorage.getItem(LINES_KEY);
  const n = raw === null ? NaN : Number(raw);
  return Number.isFinite(n) && n >= MIN_LINES && n <= MAX_LINES ? n : DEFAULT_LINES;
}

function getServerSnapshot(): number {
  return DEFAULT_LINES;
}

export function useReaderLines(): number {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function setReaderLines(n: number): void {
  if (!Number.isFinite(n)) return;
  const clamped = Math.min(MAX_LINES, Math.max(MIN_LINES, Math.round(n)));
  window.localStorage.setItem(LINES_KEY, String(clamped));
  for (const listener of listeners) listener();
}
