import { useState, useEffect, useRef } from 'react';
import { ArrowLeft, ZoomIn, ZoomOut, Menu } from 'lucide-react';
import { translations, Language } from '../utils/i18n';

interface ReaderProps {
  bookId: string;
  volumeId: number;
  port: number;
  language: Language;
  onClose: () => void;
}

interface Chapter {
  title: string;
  file: string;
}

export default function Reader({ bookId, volumeId, port, language, onClose }: ReaderProps) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [content, setContent] = useState('');
  const [fontSize, setFontSize] = useState(16);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [bookMeta, setBookMeta] = useState<any>(null);

  const readerRef = useRef<HTMLDivElement>(null);
  const lastSaveRef = useRef(0);
  const savedScrollPositionRef = useRef(0.0);
  const isInitialLoad = useRef(true);
  const isRestoringScroll = useRef(false);

  const t = (key: string) => translations[language]?.[key] || key;

  const restoreScroll = (scrollRatio: number) => {
    if (!readerRef.current) return;
    const container = readerRef.current;
    const maxScroll = container.scrollHeight - container.clientHeight;
    const targetScroll = Math.max(0, Math.min(maxScroll, Math.round(scrollRatio * container.scrollHeight)));
    if (Math.abs(container.scrollTop - targetScroll) > 1) {
      isRestoringScroll.current = true;
      container.scrollTop = targetScroll;
    }
  };

  const activeIdxRef = useRef(activeIdx);
  const chaptersRef = useRef(chapters);

  useEffect(() => {
    activeIdxRef.current = activeIdx;
    chaptersRef.current = chapters;
  }, [activeIdx, chapters]);

  // Fetch Table of Contents and metadata
  useEffect(() => {
    let active = true;
    const loadBook = async () => {
      try {
        const shelfRes = await fetch(`http://127.0.0.1:${port}/api/shelf`);
        const shelfData = await shelfRes.json();
        if (!active) return;
        const meta = shelfData.find((b: any) => b.book_id === bookId && b.volume_id === volumeId);
        if (!meta) return;
        setBookMeta(meta);

        const cachePath = meta.cache_path;
        const tocUrl = `http://127.0.0.1:${port}/api/reader/asset?path=${encodeURIComponent(cachePath + '/OEBPS/toc.ncx')}`;
        const tocRes = await fetch(tocUrl);
        const tocText = await tocRes.text();
        if (!active) return;

        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(tocText, "text/xml");
        const navPoints = xmlDoc.getElementsByTagName("navPoint");
        
        const chaps: Chapter[] = [];
        
        // Check if color.xhtml exists and prepend it as the first chapter
        const colorPath = cachePath + '/OEBPS/Text/color.xhtml';
        const colorUrl = `http://127.0.0.1:${port}/api/reader/asset?path=${encodeURIComponent(colorPath)}`;
        try {
          const colorRes = await fetch(colorUrl);
          if (colorRes.ok && active) {
            chaps.push({ 
              title: translations[language]?.['reader.colorPage'] || 'Color pages',
              file: 'color.xhtml' 
            });
          }
        } catch (e) {
          console.log("No color.xhtml available:", e);
        }

        for (let i = 0; i < navPoints.length; i++) {
          const title = navPoints[i].getElementsByTagName("text")[0]?.textContent || '';
          const src = navPoints[i].getElementsByTagName("content")[0]?.getAttribute("src") || '';
          const file = src.replace('Text/', '');
          chaps.push({ title, file });
        }

        if (!active) return;
        setChapters(chaps);
        const progressChapter = meta.reading_progress_chapter || 0;
        setActiveIdx(progressChapter < chaps.length ? progressChapter : 0);
      } catch (e) {
        console.error(e);
      }
    };

    loadBook();
    return () => {
      active = false;
    };
  }, [bookId, volumeId, port]);

  // Capture image load events to adjust scroll position as height changes dynamically
  useEffect(() => {
    // Restore initial scroll position after content renders and DOM updates
    if (readerRef.current && savedScrollPositionRef.current > 0) {
      restoreScroll(savedScrollPositionRef.current);
    } else if (readerRef.current) {
      readerRef.current.scrollTop = 0;
    }

    const handleImageLoad = () => {
      if (readerRef.current && savedScrollPositionRef.current > 0) {
        restoreScroll(savedScrollPositionRef.current);
      }
    };
    const container = readerRef.current;
    if (container) {
      container.addEventListener('load', handleImageLoad, true); // Capture phase
    }
    return () => {
      if (container) {
        container.removeEventListener('load', handleImageLoad, true);
      }
    };
  }, [content]);

  // Load active chapter content
  useEffect(() => {
    if (chapters.length === 0 || !bookMeta) return;
    let active = true;
    const loadChapter = async () => {
      try {
        const cachePath = bookMeta.cache_path;
        const chapFileRaw = chapters[activeIdx].file;
        const chapFile = chapFileRaw.split('#')[0];
        const chapUrl = `http://127.0.0.1:${port}/api/reader/asset?path=${encodeURIComponent(cachePath + '/OEBPS/Text/' + chapFile)}`;
        const res = await fetch(chapUrl);
        const rawText = await res.text();

        if (!active) return;

        const doc = new DOMParser().parseFromString(rawText, 'text/html');
        
        // Re-write image source paths
        const images = doc.getElementsByTagName('img');
        for (let i = 0; i < images.length; i++) {
          const src = images[i].getAttribute('src') || '';
          if (src.includes('../Images/')) {
            const imgName = src.replace('../Images/', '');
            const imgFullPath = `${cachePath}/OEBPS/Images/${imgName}`;
            images[i].setAttribute('src', `http://127.0.0.1:${port}/api/reader/asset?path=${encodeURIComponent(imgFullPath)}`);
            images[i].setAttribute('class', 'max-w-full my-4 rounded-lg block mx-auto shadow-md');
          }
        }

        // Re-write SVG image source paths
        const svgImages = doc.getElementsByTagName('image');
        for (let i = 0; i < svgImages.length; i++) {
          const href = svgImages[i].getAttribute('xlink:href') || svgImages[i].getAttribute('href') || '';
          if (href.includes('../Images/')) {
            const imgName = href.replace('../Images/', '');
            const imgFullPath = `${cachePath}/OEBPS/Images/${imgName}`;
            const rewrittenUrl = `http://127.0.0.1:${port}/api/reader/asset?path=${encodeURIComponent(imgFullPath)}`;
            svgImages[i].setAttribute('xlink:href', rewrittenUrl);
            svgImages[i].setAttribute('href', rewrittenUrl);
          }
        }

        const bodyHtml = doc.body.innerHTML;
        setContent(bodyHtml);

        // Update the ref to be restored in the [content] effect
        const savedScroll = isInitialLoad.current ? (bookMeta.reading_progress_scroll || 0.0) : 0.0;
        isInitialLoad.current = false;
        savedScrollPositionRef.current = savedScroll;

        // Save current chapter progress
        await fetch(`http://127.0.0.1:${port}/api/shelf/progress`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            book_id: bookId,
            volume_id: volumeId,
            chapter_index: activeIdx,
            scroll_position: savedScroll
          })
        });

      } catch (e) {
        console.error(e);
      }
    };

    loadChapter();
    return () => {
      active = false;
    };
  }, [activeIdx, chapters, bookMeta, bookId, volumeId, port]);

  // Save final scroll position ONLY on book exit / component unmount
  useEffect(() => {
    return () => {
      if (chaptersRef.current.length > 0) {
        const position = savedScrollPositionRef.current;
        fetch(`http://127.0.0.1:${port}/api/shelf/progress`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            book_id: bookId,
            volume_id: volumeId,
            chapter_index: activeIdxRef.current,
            scroll_position: position
          })
        }).catch(console.error);
      }
    };
  }, [bookId, volumeId, port]);

  const handleScroll = () => {
    if (!readerRef.current || chapters.length === 0) return;
    if (isRestoringScroll.current) {
      isRestoringScroll.current = false;
      return;
    }
    const container = readerRef.current;
    const position = container.scrollHeight > 0 ? (container.scrollTop / container.scrollHeight) : 0.0;
    
    savedScrollPositionRef.current = position;
    
    const now = Date.now();
    if (now - lastSaveRef.current > 3000) {
      lastSaveRef.current = now;
      fetch(`http://127.0.0.1:${port}/api/shelf/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          book_id: bookId,
          volume_id: volumeId,
          chapter_index: activeIdx,
          scroll_position: position
        })
      }).catch(console.error);
    }
  };

  return (
    <div className="h-full w-full flex overflow-hidden">
      {/* Sidebar Chapters Menu */}
      {sidebarOpen && (
        <aside className="w-80 bg-[#161920] border-r border-[#242936] flex flex-col overflow-hidden">
          <div className="p-4 border-b border-[#242936] flex justify-between items-center">
            <span className="font-semibold text-sm">{t('tableOfContents')}</span>
            <span className="text-xs text-gray-500">{chapters.length} {t('chaptersCount')}</span>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {chapters.map((chap, i) => (
              <button 
                key={i} onClick={() => setActiveIdx(i)}
                className={`w-full text-left p-2 rounded-lg text-xs truncate transition-all ${activeIdx === i ? 'bg-[#ff7233]/20 text-[#ff7233]' : 'text-gray-400 hover:bg-[#242936] hover:text-gray-200'}`}
              >
                {chap.title}
              </button>
            ))}
          </div>
        </aside>
      )}

      {/* Reading Pane */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header controls */}
        <header className="h-14 border-b border-[#242936] bg-[#11131a] px-4 flex justify-between items-center z-10">
          <div className="flex items-center gap-3">
            <button onClick={onClose} className="p-2 hover:bg-[#242936] rounded-lg text-gray-400 hover:text-gray-200 transition-all">
              <ArrowLeft size={18} />
            </button>
            <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-2 hover:bg-[#242936] rounded-lg text-gray-400 hover:text-gray-200 transition-all">
              <Menu size={18} />
            </button>
            {chapters.length > 0 && <span className="text-sm font-medium">{chapters[activeIdx].title}</span>}
          </div>

          <div className="flex items-center gap-2">
            <button onClick={() => setFontSize(Math.max(12, fontSize - 2))} className="p-2 hover:bg-[#242936] rounded-lg text-gray-400 hover:text-gray-200 transition-all">
              <ZoomOut size={16} />
            </button>
            <span className="text-xs text-gray-400 select-none">{fontSize}px</span>
            <button onClick={() => setFontSize(Math.min(30, fontSize + 2))} className="p-2 hover:bg-[#242936] rounded-lg text-gray-400 hover:text-gray-200 transition-all">
              <ZoomIn size={16} />
            </button>
          </div>
        </header>

        {/* Core Text container */}
        <div 
          ref={readerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-12 max-w-4xl mx-auto w-full"
          style={{ fontSize: `${fontSize}px`, lineHeight: 1.8 }}
        >
          <div 
            className="text-gray-300 select-text space-y-4 reader-content"
            dangerouslySetInnerHTML={{ __html: content }}
          />
          
          {/* Pagination footer */}
          <div className="flex justify-between items-center mt-12 pt-6 border-t border-[#242936] text-xs text-gray-500">
            <button 
              disabled={activeIdx === 0} onClick={() => setActiveIdx(prev => prev - 1)}
              className="px-4 py-2 bg-[#161920] border border-[#242936] rounded-lg hover:border-[#ff7233] disabled:opacity-50 disabled:hover:border-[#242936]"
            >
              {t('prevChapter')}
            </button>
            <span>{activeIdx + 1} / {chapters.length}</span>
            <button 
              disabled={activeIdx === chapters.length - 1} onClick={() => setActiveIdx(prev => prev + 1)}
              className="px-4 py-2 bg-[#161920] border border-[#242936] rounded-lg hover:border-[#ff7233] disabled:opacity-50 disabled:hover:border-[#242936]"
            >
              {t('nextChapter')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
