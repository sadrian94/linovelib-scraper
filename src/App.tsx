import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Download, Library, Settings as SettingsIcon } from 'lucide-react';
import Downloader from './components/Downloader';
import Shelf from './components/Shelf';
import Settings from './components/Settings';
import Reader from './components/Reader';

export default function App() {
  const [tab, setTab] = useState<'downloader' | 'shelf' | 'settings'>('downloader');
  const [port, setPort] = useState<number>(8000);
  const [activeReading, setActiveReading] = useState<{bookId: string, volumeId: number} | null>(null);

  useEffect(() => {
    invoke<number>('get_server_port')
      .then((p) => setPort(p))
      .catch((e) => console.error("Failed to load server port:", e));
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      {/* Navigation Sidebar */}
      <aside className="w-64 bg-[#11131a] border-r border-[#242936] flex flex-col justify-between p-4 z-10">
        <div>
          <div className="flex items-center gap-3 mb-8 px-2">
            <div className="w-8 h-8 rounded-lg bg-[#ff7233] flex items-center justify-center font-bold text-black">B</div>
            <h1 className="font-semibold text-lg tracking-wider">哔哩轻小说</h1>
          </div>
          
          <nav className="space-y-1">
            <button 
              onClick={() => { setTab('downloader'); setActiveReading(null); }}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${tab === 'downloader' && !activeReading ? 'bg-[#ff7233]/10 text-[#ff7233] font-medium' : 'text-gray-400 hover:text-gray-200'}`}
            >
              <Download size={18} /> 下载小说
            </button>
            <button 
              onClick={() => { setTab('shelf'); }}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${(tab === 'shelf' || activeReading) ? 'bg-[#ff7233]/10 text-[#ff7233] font-medium' : 'text-gray-400 hover:text-gray-200'}`}
            >
              <Library size={18} /> 本地书架
            </button>
          </nav>
        </div>

        <button 
          onClick={() => { setTab('settings'); setActiveReading(null); }}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${tab === 'settings' ? 'bg-[#ff7233]/10 text-[#ff7233] font-medium' : 'text-gray-400 hover:text-gray-200'}`}
        >
          <SettingsIcon size={18} /> 软件设置
        </button>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 bg-[#0d0e12] overflow-hidden relative">
        {activeReading ? (
          <Reader bookId={activeReading.bookId} volumeId={activeReading.volumeId} port={port} onClose={() => setActiveReading(null)} />
        ) : (
          <>
            {tab === 'downloader' && <Downloader port={port} />}
            {tab === 'shelf' && <Shelf port={port} onRead={(b, v) => setActiveReading({bookId: b, volumeId: v})} />}
            {tab === 'settings' && <Settings port={port} />}
          </>
        )}
      </main>
    </div>
  );
}
