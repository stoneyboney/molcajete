import { memo } from 'react'
import type { ParagraphView } from '../domain/view/readerView'

/**
 * One paragraph. Memoised, and given a view model it never recomputes: the
 * runs, the dotted-underline flag and the reveal gloss are all decided in the
 * domain layer, so re-rendering the chapter costs a referential equality check
 * per paragraph and nothing else.
 *
 * No `onClick` here. A chapter has tens of thousands of words and the handler
 * is delegated to the article above, which is one listener instead of 30,000
 * closures.
 *
 * The reveal gloss is always in the DOM when it exists, hidden by CSS. That is
 * what makes the toggle a single attribute flip on the article rather than a
 * re-render of a thousand paragraphs.
 */
export const Paragraph = memo(function Paragraph({
  view,
}: {
  view: ParagraphView
}) {
  return (
    <p
      data-pid={view.id}
      className="reader-paragraph"
      style={{ containIntrinsicSize: `auto ${view.estimatedHeightPx}px` }}
    >
      {view.runs.map((run, index) => {
        if (run.kind === 'text') return run.text
        if (run.reveal !== null) {
          return (
            <ruby key={index} data-t={run.key} className="word word-marked">
              {run.text}
              <rt>{run.reveal}</rt>
            </ruby>
          )
        }
        return (
          <span
            key={index}
            data-t={run.key}
            className={run.marked ? 'word word-marked' : 'word'}
          >
            {run.text}
          </span>
        )
      })}
    </p>
  )
})
