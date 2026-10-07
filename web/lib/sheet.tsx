import { useRef } from "react";
import { TOPICS } from "@/lib/topics";

/** Bottom sheet on phones, centered dialog from `sm` up. The footer sits outside the
 *  scrolling body so the actions stay reachable under a long form. */
export function Sheet({
  title,
  onClose,
  footer,
  children,
}: {
  title: string;
  onClose: () => void;
  footer: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 bg-black/25 flex items-end sm:items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label={title}
        className="w-full sm:max-w-md max-h-[90vh] flex flex-col bg-surface border-t border-border sm:border sm:rounded-lg shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4 px-5 pt-5 pb-3">
          <h2 className="text-xl font-bold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-mr-1.5 rounded p-1.5 text-muted hover:text-ink transition-colors"
          >
            <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" aria-hidden>
              <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
            </svg>
          </button>
        </div>
        <div className="flex flex-col gap-5 overflow-y-auto px-5 pb-5">{children}</div>
        <div className="flex gap-3 border-t border-border px-5 py-4">{footer}</div>
      </div>
    </div>
  );
}

/** A labelled form row: label on top, control full width, optional hint under. */
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

/** Topic as tappable chips: the list is short and fixed, so a select only hid it. */
export function TopicPicker({ value, onChange }: { value: string; onChange: (t: string) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium">Topic</span>
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Topic">
        {["", ...TOPICS].map((t) => {
          const on = value === t;
          return (
            <button
              key={t || "none"}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange(t)}
              className={`rounded border px-3 py-1.5 text-sm transition-colors ${
                on
                  ? "border-accent bg-accent text-accent-ink"
                  : "border-border text-muted hover:text-ink hover:border-accent"
              }`}
            >
              {t || "None"}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** A styled stand-in for the browser's bare "Choose File" control. */
export function FilePicker({
  prompt,
  accept,
  multiple,
  files,
  onChange,
}: {
  prompt: string;
  accept: string;
  multiple?: boolean;
  files: File[];
  onChange: (files: File[]) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const chosen =
    files.length === 0
      ? null
      : files.length === 1
        ? files[0].name
        : `${files.length} files selected`;

  return (
    <>
      <button
        type="button"
        onClick={() => input.current?.click()}
        className="flex items-center justify-between gap-3 rounded border border-dashed border-border bg-paper px-4 py-3 text-left text-sm hover:border-accent transition-colors"
      >
        <span className={`min-w-0 truncate ${chosen ? "text-ink" : "text-muted"}`}>
          {chosen ?? prompt}
        </span>
        <span className="shrink-0 font-medium text-accent">{chosen ? "Change" : "Browse"}</span>
      </button>
      <input
        ref={input}
        type="file"
        accept={accept}
        multiple={multiple}
        hidden
        onChange={(e) => {
          onChange(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
    </>
  );
}
