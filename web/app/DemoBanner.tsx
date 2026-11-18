"use client";

import { useEffect, useState } from "react";
import { demoCredits, demoSeededLemmas, resetDemo } from "@/lib/demo";

const REPO = "https://github.com/miobix/MbxRead-public";

export default function DemoBanner() {
  const [credits, setCredits] = useState<string[]>([]);
  const [seeded, setSeeded] = useState<string[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    demoCredits().then(setCredits);
    demoSeededLemmas().then(setSeeded);
  }, []);

  return (
    <div className="border-b border-border bg-highlight px-4 py-2 text-sm text-ink">
      <div className="mx-auto flex max-w-3xl flex-wrap items-baseline gap-x-3 gap-y-1">
        <strong>Demo with sample data.</strong>
        <span>Tap a word, save it, and watch its other forms light up.</span>
        <button type="button" className="btn-link" onClick={() => setOpen(!open)}>
          {open ? "Less" : "What's real?"}
        </button>
      </div>
      {open && (
        <div className="mx-auto mt-2 flex max-w-3xl flex-col gap-1.5 text-muted">
          <p>
            There is no server behind this page. Tokens, lemmas, translations (DeepL) and
            dictionary entries (krdict) were recorded from the real app for the words in
            these texts. Words you save stay in this browser only.
          </p>
          <p>
            The services are not live. Similar usage and its Explain line were seeded with real
            output from the app&apos;s local models ({seeded.join(", ")}). Importing, feeds and
            Anki sync need the full app.
          </p>
          <p>
            Two sample texts were written for this demo.{" "}
            {credits.map((c) => (
              <span key={c}>{c} </span>
            ))}
          </p>
          <p className="flex flex-wrap gap-x-4">
            <a className="btn-link" href={REPO}>
              Source code
            </a>
            <button
              type="button"
              className="btn-link"
              onClick={() => {
                resetDemo();
                window.location.reload();
              }}
            >
              Reset my saved words
            </button>
          </p>
        </div>
      )}
    </div>
  );
}
