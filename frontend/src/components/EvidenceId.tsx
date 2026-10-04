const CHIP = 'rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-600'

/**
 * An evidence ID. With `onSelect` it is an interactable chip that opens the
 * provenance drawer; without it, a plain label.
 */
export function EvidenceId({ id, onSelect }: { id: string; onSelect?: (id: string) => void }) {
  if (!onSelect) return <code className={CHIP}>{id}</code>
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      aria-label={`Show evidence ${id}`}
      className={`${CHIP} underline decoration-dotted hover:bg-sky-100 hover:text-sky-800 focus:outline-none focus:ring-2 focus:ring-sky-500`}
    >
      {id}
    </button>
  )
}
