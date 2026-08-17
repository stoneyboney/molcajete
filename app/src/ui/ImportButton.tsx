import { useId } from 'react'

/**
 * A plain file input, styled as a button.
 *
 * `accept` is `.json` rather than `.molcajete.json`: iOS matches the accept
 * list against the system's idea of a file's type, and a double extension is
 * not one — narrowing it further greys the bundle out in the Files picker. The
 * real gate is `parseBundle`, which has to run on the contents anyway.
 */
export function ImportButton({
  onFile,
  busy,
  label,
}: {
  onFile: (file: File) => void
  busy: boolean
  label: string
}) {
  const id = useId()

  return (
    <>
      <input
        id={id}
        type="file"
        accept=".json,application/json"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0]
          // Cleared before dispatching, so picking the same file again — after
          // rebuilding the bundle on the desktop — still fires a change event.
          event.target.value = ''
          if (file) onFile(file)
        }}
      />
      <label
        htmlFor={id}
        aria-busy={busy}
        className="bg-accent inline-flex cursor-pointer items-center rounded-full px-4 py-2 text-sm font-medium text-white aria-busy:opacity-60"
      >
        {busy ? 'Importiere …' : label}
      </label>
    </>
  )
}
