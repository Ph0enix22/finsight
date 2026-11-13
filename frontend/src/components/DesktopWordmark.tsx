// Fills the empty margin beside the centred phone frame on wide (desktop/demo
// recording) viewports, so it reads as intentional rather than an unstyled gap.
export function DesktopWordmark({ personaName }: { personaName?: string }) {
  return (
    <div className="pointer-events-none fixed inset-y-0 left-0 hidden w-[calc(50%-215px)] flex-col items-end justify-center gap-1 pr-6 lg:flex">
      <p className="font-heading text-h1 text-foreground">FinSight</p>
      <p className="text-small text-muted-foreground">Know before you pay</p>
      {personaName && (
        <p className="mt-4 rounded-full bg-muted px-3 py-1 text-micro text-muted-foreground">
          {personaName}
        </p>
      )}
    </div>
  )
}
