/**
 * Splits a pasted blob of SMS into individual messages. Real multi-line SMS
 * (bank messages often wrap mid-sentence) must stay intact, so this splits
 * on blank lines or a `---` separator line — never on every newline.
 */
export function splitSmsMessages(raw: string): string[] {
  const normalized = raw.replace(/\r\n/g, '\n').trim()
  if (!normalized) return []
  const blocks = normalized.split(/\n[ \t]*-{3,}[ \t]*\n|\n{2,}/)
  return blocks.map((block) => block.trim()).filter(Boolean)
}
