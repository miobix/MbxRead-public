import Link from "next/link";

export function BackLink({ href = "/", label = "Library" }: { href?: string; label?: string }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1 self-start text-sm font-medium text-accent hover:opacity-80 transition-opacity"
    >
      <svg
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
        className="h-4 w-4"
      >
        <path d="M10 3 5 8l5 5" />
      </svg>
      {label}
    </Link>
  );
}
