# Anki sync

How to push saved terms from MbxRead into Anki, and how the sync actually
works under the hood. See `docs/SPEC.md` section 8 and `docs/ARCHITECTURE.md`
for the full technical spec; this is the practical how-to.

## One-time setup

1. **Anki desktop**, with the **AnkiConnect** add-on (code `2055492159`).
2. That's it. You do **not** need to add anything to
   AnkiConnect's `webCorsOriginList` config. That CORS allowlist only applies to
   requests sent *from a browser* (with an `Origin` header); MbxRead's
   sync call goes server-to-server (the FastAPI backend calling AnkiConnect
   directly over `httpx`), which isn't subject to that check at all.

## Daily use

1. Open **Anki desktop** and leave it running. Sync only works while Anki is open.
2. Read as normal — tap words, translate, save them. Every term saved with
   status **learning** is a sync candidate.
3. Go to `/terms` in the app (link next to "+ Add book" on the home page).
4. Click **Sync to Anki**.
5. You'll see a result: `Added X, updated Y` (plus a list of any per-term
   failures). Check Anki's card browser to confirm.
6. Run your normal AnkiWeb sync (or however you get cards to AnkiDroid) —
   MbxRead only talks to the local Anki desktop app, not AnkiWeb.

## What happens on Sync

- **New terms** — any `learning` term not yet synced (`anki_note_id` is empty)
  gets added as a new note:
  - Note type: `Basic`
  - `Front` = the term's lemma
  - `Back` = the translation, plus the saved example sentence in italics below
    it (if there is one)
  - Tag: `korean-reader` (kept from the old repo name, like the note type names)
  - Deck: whatever you picked when saving the term (falls back to Anki's own
    `Default` deck for older/hand-seeded terms with no deck set)
- **Edited terms** — if you later change a synced term's translation, notes,
  deck, or sentence, it's marked dirty, and the next Sync pushes those changes
  into the *same* Anki note (`updateNoteFields`) — it never creates a
  duplicate.
- **known / ignored terms** — never synced. If a term was already synced and
  you later mark it known/ignored, its existing Anki note is left alone (not
  deleted, not touched).
- **Deletes** — deleting a term in MbxRead does **not** delete its Anki
  note. Anki notes are only ever added or updated, never removed by sync.

## Troubleshooting

- **"Anki is not running (or AnkiConnect missing)"** — Anki desktop isn't open,
  or the AnkiConnect add-on isn't installed/enabled. Open Anki and try again.
- **A term shows up under "failed"** — the per-term error from AnkiConnect is
  shown next to it (e.g. a duplicate-note conflict). Other terms in the same
  sync still go through; a single bad note doesn't block the rest.
- **Want to compare backends or debug a translation before saving** — that's
  the `/read` popover's Translate/Dictionary buttons, unrelated to Anki sync.
