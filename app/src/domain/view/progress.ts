/**
 * Reading progress, expressed as the fraction of a chapter that is behind you.
 *
 * Paragraph-based rather than pixel-based on purpose: the same position has to
 * mean the same thing at a different type size, in landscape, and on a phone
 * instead of an iPad.
 */

/** 0 at the first paragraph, 1 at the last. */
export function readingFraction(
  paragraphIndex: number,
  paragraphCount: number,
): number {
  if (paragraphCount <= 1) return 1
  const clamped = Math.min(Math.max(paragraphIndex, 0), paragraphCount - 1)
  return clamped / (paragraphCount - 1)
}
