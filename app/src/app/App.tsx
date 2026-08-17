import { ChapterList } from '../ui/ChapterList'
import { Library } from '../ui/Library'
import { Reader } from '../ui/Reader'
import { TeachingSession } from '../ui/TeachingSession'
import { useRoute } from './useRoute'

export function App() {
  const route = useRoute()

  switch (route.name) {
    case 'library':
      return <Library />
    case 'chapters':
      return <ChapterList bookId={route.bookId} />
    case 'reader':
      return (
        <Reader
          // Remounting on a chapter change is what resets the reveal-all
          // toggle, which SPEC §13.3 requires not to persist across chapters.
          key={`${route.bookId}/${route.chapterIndex}`}
          bookId={route.bookId}
          chapterIndex={route.chapterIndex}
        />
      )
    case 'session':
      return (
        <TeachingSession
          key={`${route.bookId}/${route.chapterIndex}`}
          bookId={route.bookId}
          chapterIndex={route.chapterIndex}
        />
      )
  }
}
