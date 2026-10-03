/** Plain evidence ID label; the provenance drawer arrives with Spec 10. */
export function EvidenceId({ id }: { id: string }) {
  return (
    <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-600">
      {id}
    </code>
  )
}
