import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Download, Library, Settings as SettingsIcon } from 'lucide-react';
import Downloader from './components/Downloader';
import Shelf from './components/Shelf';
import Settings from './components/Settings';
import Reader from './components/Reader';
import { translations, Language } from './utils/i18n';

export default function App() {
  const [tab, setTab] = useState<'downloader' | 'shelf' | 'settings'>('downloader');
  const [port, setPort] = useState<number>(8000);
  const [language, setLanguage] = useState<Language>('zh-TW');
  const [activeReading, setActiveReading] = useState<{bookId: string, volumeId: number} | null>(null);

  const t = (key: string) => translations[language]?.[key] || key;

  useEffect(() => {
    invoke<number>('get_server_port')
      .then((p) => setPort(p))
      .catch((e) => console.error("Failed to load server port:", e));
  }, []);

  useEffect(() => {
    fetch(`http://127.0.0.1:${port}/api/config`)
      .then(res => res.json())
      .then(data => {
        if (data.app_language) {
          setLanguage(data.app_language as Language);
        }
      })
      .catch(e => console.error("Failed to fetch configuration:", e));
  }, [port]);

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      {/* Navigation Sidebar */}
      <aside className="w-64 bg-[#11131a] border-r border-[#242936] flex flex-col justify-between p-4 z-10">
        <div>
          <div className="flex items-center gap-3 mb-8 px-2">
            <div className="w-8 h-8 rounded-lg bg-[#ff7233] flex items-center justify-center font-bold text-black">B</div>
            <h1 className="font-semibold text-lg tracking-wider">{t('appName')}</h1>
          </div>
          
          <nav className="space-y-1">
            <button 
              onClick={() => { setTab('downloader'); setActiveReading(null); }}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${tab === 'downloader' && !activeReading ? 'bg-[#ff7233]/10 text-[#ff7233] font-medium' : 'text-gray-400 hover:text-gray-200'}`}
            >
              <Download size={18} /> {t('downloadNovel')}
            </button>
            <button 
              onClick={() => { setTab('shelf'); }}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${(tab === 'shelf' || activeReading) ? 'bg-[#ff7233]/10 text-[#ff7233] font-medium' : 'text-gray-400 hover:text-gray-200'}`}
            >
              <Library size={18} /> {t('localShelf')}
            </button>
          </nav>
        </div>

        <button 
          onClick={() => { setTab('settings'); setActiveReading(null); }}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${tab === 'settings' ? 'bg-[#ff7233]/10 text-[#ff7233] font-medium' : 'text-gray-400 hover:text-gray-200'}`}
        >
          <SettingsIcon size={18} /> {t('settings')}
        </button>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 bg-[#0d0e12] overflow-hidden relative">
        {activeReading ? (
          <Reader 
            key={`${activeReading.bookId}-${activeReading.volumeId}`}
            bookId={activeReading.bookId} 
            volumeId={activeReading.volumeId} 
            port={port} 
            language={language}
            onClose={() => setActiveReading(null)} 
          />
        ) : (
          <>
            {tab === 'downloader' && <Downloader port={port} language={language} />}
            {tab === 'shelf' && <Shelf port={port} language={language} onRead={(b, v) => setActiveReading({bookId: b, volumeId: v})} />}
            {tab === 'settings' && <Settings port={port} language={language} onLanguageChange={setLanguage} />}
          </>
        )}
      </main>
    </div>
  );
}
