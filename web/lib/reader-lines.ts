"use client";

import { useSyncExternalStore } from "react";

/**
 * Rendered lines per reader page, per device (a phone and a laptop fit different
 * amounts per line). useSyncExternalStore keeps the static export's first render in
 * agreement and updates an open reader, even in another tab, without a reload.
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
