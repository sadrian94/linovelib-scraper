import { useEffect, useRef, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { ReactReader } from 'react-reader';
import { Language, translations } from '../utils/i18n';

interface ReaderProps {
  bookId: string;
  volumeId: number;
  port: number;
  language: Language;
  onClose: () => void;
}

interface ShelfBook {
  book_id: string;
  volume_id: number;
  title: string;
  volume_name: string;
  reading_progress_cfi?: string | null;
}

/** Render the EPUB archive directly. `.library` is not a reader input. */
export default function Reader({ bookId, volumeId, port, language, onClose }: ReaderProps) {
  const [book, setBook] = useState<ShelfBook | null>(null);
  const [location, setLocation] = useState<string | number>(0);
  const saveTimer = useRef<number | undefined>();
  const t = (key: string) => translations[language]?.[key] || key;

  useEffect(() => {
    let active = true;
    fetch(`http://127.0.0.1:${port}/api/shelf`)
      .then((response) => response.json())
      .then((books: ShelfBook[]) => {
        const matched = books.find((item) => item.book_id === bookId && item.volume_id === volumeId);
        if (!active || !matched) return;
        setBook(matched);
        setLocation(matched.reading_progress_cfi || 0);
      })
      .catch(console.error);
    return () => {
      active = false;
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
    };
  }, [bookId, volumeId, port]);

  const saveLocation = (epubCfi: string) => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      fetch(`http://127.0.0.1:${port}/api/shelf/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          book_id: bookId,
          volume_id: volumeId,
          epub_cfi: epubCfi,
        }),
      }).catch(console.error);
    }, 500);
  };

  if (!book) return null;
  const epubUrl = `http://127.0.0.1:${port}/api/reader/epub/${encodeURIComponent(bookId)}/${volumeId}`;

  return (
    <div className="h-full w-full flex flex-col overflow-hidden bg-[#11131a]">
      <header className="h-14 shrink-0 border-b border-[#242936] px-4 flex items-center gap-3">
        <button onClick={onClose} className="p-2 hover:bg-[#242936] rounded-lg text-gray-400 hover:text-gray-200 transition-all" aria-label={t('back')}>
          <ArrowLeft size={18} />
        </button>
        <span className="text-sm font-medium text-gray-200 truncate">{book.title} {book.volume_name}</span>
      </header>
      <div className="flex-1 min-h-0">
        <ReactReader
          url={epubUrl}
          location={location}
          locationChanged={(epubCfi: string) => {
            setLocation(epubCfi);
            saveLocation(epubCfi);
          }}
          showToc
          epubOptions={{ flow: 'scrolled', manager: 'continuous' }}
        />
      </div>
    </div>
  );
}
