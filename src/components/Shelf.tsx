import { useState, useEffect } from 'react';
import { Trash2, BookOpen, RefreshCw } from 'lucide-react';
import { translations, Language } from '../utils/i18n';

interface Book {
  book_id: string;
  volume_id: number;
  title: string;
  volume_name: string;
  author: string;
  publisher: string;
  cover_path: string;
  epub_path: string;
  cache_path: string;
  download_date: string;
}

interface ShelfProps {
  port: number;
  language: Language;
  onRead: (b: string, v: number) => void;
}

export default function Shelf({ port, language, onRead }: ShelfProps) {
  const [books, setBooks] = useState<Book[]>([]);
  const [search, setSearch] = useState('');
  const [converting, setConverting] = useState<string | null>(null);

  const t = (key: string) => translations[language]?.[key] || key;

  const fetchBooks = async () => {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/shelf`);
      const data = await res.json();
      setBooks(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchBooks();
  }, [port]);

  const handleDelete = async (bId: string, vId: number) => {
    if (!confirm(t('deleteConfirm'))) return;
    try {
      await fetch(`http://127.0.0.1:${port}/api/shelf/${bId}/${vId}`, { method: 'DELETE' });
      fetchBooks();
    } catch (e) {
      console.error(e);
    }
  };

  const handleConvert = async (bookId: string, volumeId: number) => {
    const key = `${bookId}_${volumeId}`;
    setConverting(key);
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/shelf/convert/${bookId}/${volumeId}`, {
        method: 'POST'
      });
      if (res.ok) {
        await fetchBooks();
      } else {
        console.error('Failed to convert book font');
      }
    } catch (e) {
      console.error(e);
    } finally {
      setConverting(null);
    }
  };

  const filtered = books.filter(b => 
    b.title.toLowerCase().includes(search.toLowerCase()) || 
    b.author.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-8 h-full flex flex-col overflow-hidden">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold">{t('shelfHeader')}</h2>
        <input 
          type="text" placeholder={t('searchPlaceholder')} value={search} onChange={e => setSearch(e.target.value)}
          className="bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm w-64 focus:outline-none focus:border-[#ff7233]"
        />
      </div>

      {/* Shelf Grid */}
      <div className="flex-1 overflow-y-auto pr-2">
        {filtered.length === 0 ? (
          <div className="h-full flex items-center justify-center text-gray-500 text-sm">{t('emptyShelf')}</div>
        ) : (
          <div className="grid grid-cols-4 gap-6">
            {filtered.map(book => (
              <div key={`${book.book_id}_${book.volume_id}`} className="bg-[#161920] border border-[#242936] rounded-xl overflow-hidden group flex flex-col justify-between">
                <div className="relative aspect-[3/4] bg-gray-900 flex items-center justify-center overflow-hidden">
                  <img 
                    src={`http://127.0.0.1:${port}/api/reader/asset?path=${encodeURIComponent(book.cover_path)}`} 
                    alt={book.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  />
                  <div className="absolute inset-0 bg-black/70 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-3">
                    <button 
                      onClick={() => onRead(book.book_id, book.volume_id)}
                      className="p-2 bg-[#ff7233] text-black rounded-full hover:scale-110 transition-transform" title={t('readOnline')}
                    >
                      <BookOpen size={20} />
                    </button>
                    <button 
                      onClick={() => handleConvert(book.book_id, book.volume_id)}
                      disabled={converting === `${book.book_id}_${book.volume_id}`}
                      className="p-2 bg-blue-600 text-white rounded-full hover:scale-110 transition-transform disabled:opacity-50 disabled:hover:scale-100" title={t('shelf.tooltip.convert')}
                    >
                      <RefreshCw size={20} className={converting === `${book.book_id}_${book.volume_id}` ? 'animate-spin' : ''} />
                    </button>
                    <button 
                      onClick={() => handleDelete(book.book_id, book.volume_id)}
                      className="p-2 bg-red-600 text-white rounded-full hover:scale-110 transition-transform" title={t('delete')}
                    >
                      <Trash2 size={20} />
                    </button>
                  </div>
                </div>
                <div className="p-3">
                  <h3 className="font-semibold text-sm truncate">{book.title}</h3>
                  <p className="text-xs text-[#ff7233] truncate mb-1">{book.volume_name}</p>
                  <p className="text-xs text-gray-400 truncate">{book.author}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
