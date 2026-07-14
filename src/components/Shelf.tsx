import { useState, useEffect } from 'react';
import { Trash2, BookOpen, RefreshCw, ArrowLeft } from 'lucide-react';
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
  const [selectedBookId, setSelectedBookId] = useState<string | null>(null);

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
      const res = await fetch(`http://127.0.0.1:${port}/api/shelf`);
      const data = await res.json();
      setBooks(data);
      
      const remainingVols = data.filter((b: Book) => b.book_id === bId);
      if (remainingVols.length === 0) {
        setSelectedBookId(null);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleConvert = async (bId: string, vId: number) => {
    setConverting(`${bId}_${vId}`);
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/shelf/convert/${bId}/${vId}`, { method: 'POST' });
      if (res.ok) {
        fetchBooks();
      } else {
        alert(t('shelf.error.convert'));
      }
    } catch (e) {
      console.error(e);
      alert(t('shelf.error.convert'));
    } finally {
      setConverting(null);
    }
  };

  // Group books by book_id
  const groupsMap: Record<string, Book[]> = {};
  for (const book of books) {
    if (!groupsMap[book.book_id]) {
      groupsMap[book.book_id] = [];
    }
    groupsMap[book.book_id].push(book);
  }

  const groupedBooks = Object.keys(groupsMap).map(bookId => {
    const vols = groupsMap[bookId];
    vols.sort((a, b) => a.volume_id - b.volume_id);
    const firstVol = vols[0];
    return {
      book_id: bookId,
      title: firstVol.title,
      author: firstVol.author,
      publisher: firstVol.publisher,
      cover_path: firstVol.cover_path,
      volumes: vols,
    };
  });

  const filteredGroups = groupedBooks.filter(group => 
    group.title.toLowerCase().includes(search.toLowerCase()) || 
    group.author.toLowerCase().includes(search.toLowerCase())
  );

  const selectedGroup = selectedBookId ? groupedBooks.find(g => g.book_id === selectedBookId) : null;

  return (
    <div className="p-8 h-full flex flex-col overflow-hidden">
      {selectedBookId === null ? (
        <>
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-bold">{t('shelfHeader')}</h2>
            <input 
              type="text" placeholder={t('searchPlaceholder')} value={search} onChange={e => setSearch(e.target.value)}
              className="bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm w-64 focus:outline-none focus:border-[#ff7233]"
            />
          </div>

          {/* Shelf Grid */}
          <div className="flex-1 overflow-y-auto pr-2">
            {filteredGroups.length === 0 ? (
              <div className="h-full flex items-center justify-center text-gray-500 text-sm">{t('emptyShelf')}</div>
            ) : (
              <div className="grid grid-cols-4 gap-6">
                {filteredGroups.map(group => (
                  <div 
                    key={group.book_id} 
                    onClick={() => setSelectedBookId(group.book_id)}
                    className="bg-[#161920] border border-[#242936] hover:border-[#ff7233]/50 rounded-xl overflow-hidden group flex flex-col justify-between cursor-pointer transition-all duration-200"
                  >
                    <div className="relative aspect-[3/4] bg-gray-900 flex items-center justify-center overflow-hidden">
                      <img 
                        src={`http://127.0.0.1:${port}/api/reader/asset?path=${encodeURIComponent(group.cover_path)}`} 
                        alt={group.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      />
                      <div className="absolute top-2 right-2 bg-[#ff7233] text-black text-xs font-bold px-2 py-1 rounded-md shadow-lg z-10">
                        {group.volumes.length} {t('shelf.volumesCount')}
                      </div>
                    </div>
                    <div className="p-3">
                      <h3 className="font-semibold text-sm truncate text-white group-hover:text-[#ff7233] transition-colors">{group.title}</h3>
                      <p className="text-xs text-gray-400 truncate mt-1">{group.author}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : (
        selectedGroup && (
          <>
            <div className="flex items-center gap-4 mb-6">
              <button 
                onClick={() => setSelectedBookId(null)}
                className="p-2 bg-[#161920] border border-[#242936] hover:border-[#ff7233] rounded-lg transition-colors text-gray-400 hover:text-white flex items-center justify-center"
                title={t('shelf.backToShelf')}
              >
                <ArrowLeft size={18} />
              </button>
              <h2 className="text-xl font-bold">{t('shelf.backToShelf')}</h2>
            </div>

            <div className="flex-1 flex gap-8 overflow-hidden">
              {/* Left Panel: Series Info */}
              <div className="w-1/3 max-w-[280px] flex flex-col gap-4 overflow-y-auto">
                <div className="relative aspect-[3/4] bg-gray-900 rounded-xl overflow-hidden border border-[#242936] shadow-xl">
                  <img 
                    src={`http://127.0.0.1:${port}/api/reader/asset?path=${encodeURIComponent(selectedGroup.cover_path)}`} 
                    alt={selectedGroup.title} className="w-full h-full object-cover"
                  />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-white leading-snug mb-2">{selectedGroup.title}</h3>
                  <p className="text-sm text-gray-400 truncate">
                    <span className="text-gray-500 font-medium mr-1">Author:</span>{selectedGroup.author}
                  </p>
                  <p className="text-xs text-gray-500 truncate mt-1">
                    <span className="text-gray-500 font-medium mr-1">Publisher:</span>{selectedGroup.publisher}
                  </p>
                </div>
              </div>

              {/* Right Panel: Volumes List */}
              <div className="flex-1 bg-[#161920]/40 border border-[#242936] rounded-xl flex flex-col overflow-hidden">
                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                  {selectedGroup.volumes.map(volume => {
                    const isConverting = converting === `${volume.book_id}_${volume.volume_id}`;
                    const isAnyConverting = converting !== null;
                    
                    return (
                      <div 
                        key={volume.volume_id}
                        className="flex items-center justify-between p-4 bg-[#161920] border border-[#242936] hover:border-[#ff7233]/30 rounded-xl transition-all"
                      >
                        <div className="flex items-center flex-1 min-w-0 pr-4 gap-4">
                          <img 
                            src={`http://127.0.0.1:${port}/api/reader/asset?path=${encodeURIComponent(volume.cover_path)}`} 
                            alt={volume.volume_name} 
                            className="w-10 h-14 object-cover rounded border border-[#242936] bg-gray-900 shadow-sm"
                          />
                          <div className="min-w-0">
                            <h4 className="font-semibold text-sm text-white truncate">{volume.volume_name}</h4>
                            <p className="text-xs text-gray-500 mt-1">
                              {t('shelf.downloadDate')}: {volume.download_date || 'N/A'}
                            </p>
                          </div>
                        </div>
                        
                        <div className="flex items-center gap-2">
                          {/* Read Online */}
                          <button
                            onClick={() => onRead(volume.book_id, volume.volume_id)}
                            disabled={isAnyConverting}
                            className="p-2 bg-[#ff7233] text-black rounded-lg hover:scale-105 active:scale-95 transition-transform disabled:opacity-30 disabled:pointer-events-none flex items-center justify-center"
                            title={t('readOnline')}
                          >
                            <BookOpen size={18} />
                          </button>

                          {/* Convert Font */}
                          <button
                            onClick={() => handleConvert(volume.book_id, volume.volume_id)}
                            disabled={isAnyConverting}
                            className="p-2 bg-[#242936] border border-[#2d3342] text-white rounded-lg hover:scale-105 active:scale-95 transition-transform disabled:opacity-30 disabled:pointer-events-none flex items-center justify-center"
                            title={t('shelf.tooltip.convert')}
                          >
                            {isConverting ? (
                              <RefreshCw size={18} className="animate-spin text-[#ff7233]" />
                            ) : (
                              <RefreshCw size={18} />
                            )}
                          </button>

                          {/* Delete */}
                          <button
                            onClick={() => handleDelete(volume.book_id, volume.volume_id)}
                            disabled={isAnyConverting}
                            className="p-2 bg-red-600/20 border border-red-600/30 text-red-400 rounded-lg hover:bg-red-600 hover:text-white hover:scale-105 active:scale-95 transition-all disabled:opacity-30 disabled:pointer-events-none flex items-center justify-center"
                            title={t('delete')}
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </>
        )
      )}
    </div>
  );
}
