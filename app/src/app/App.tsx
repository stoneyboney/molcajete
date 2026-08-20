import { ChapterList } from '../ui/ChapterList'
import { Diagnose } from '../ui/Diagnose'
import { Library } from '../ui/Library'
import { Notizen } from '../ui/Notizen'
import { Reader } from '../ui/Reader'
import { Review } from '../ui/Review'
import { Statistik } from '../ui/Statistik'
import { TeachingSession } from '../ui/TeachingSession'
import { useRoute } from './useRoute'

export function App() {
  const route = useRoute()

  switch (route.name) {
    case 'library':
      return <Library />
    case 'review':
      return <Review />
    case 'diagnose':
      return <Diagnose />
    case 'notizen':
      return <Notizen />
    case 'statistik':
      return <Statistik />
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
