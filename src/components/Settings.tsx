import { useState, useEffect } from 'react';

export default function Settings({ port }: { port: number }) {
  const [cfg, setCfg] = useState({
    download_path: './out',
    theme: 'Dark',
    interval: '500',
    numthread: '4',
    headless_mode: 'True'
  });

  useEffect(() => {
    fetch(`http://127.0.0.1:${port}/api/config`)
      .then(res => res.json())
      .then(data => setCfg(prev => ({ ...prev, ...data })))
      .catch(e => console.error(e));
  }, [port]);

  const handleSave = async () => {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg)
      });
      if (res.ok) alert("设置保存成功");
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="p-8 h-full max-w-xl flex flex-col justify-between">
      <div>
        <h2 className="text-xl font-bold mb-6">软件设置</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">下载保存路径</label>
            <input 
              type="text" value={cfg.download_path} onChange={e => setCfg({ ...cfg, download_path: e.target.value })}
              className="w-full bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
            />
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">下载间隔 (毫秒)</label>
              <input 
                type="number" value={cfg.interval} onChange={e => setCfg({ ...cfg, interval: e.target.value })}
                className="w-full bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">最大下载线程</label>
              <input 
                type="number" value={cfg.numthread} onChange={e => setCfg({ ...cfg, numthread: e.target.value })}
                className="w-full bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">无头浏览器运行 (Headless)</label>
            <select 
              value={cfg.headless_mode} onChange={e => setCfg({ ...cfg, headless_mode: e.target.value })}
              className="w-full bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
            >
              <option value="True">开启 (背景运行)</option>
              <option value="False">关闭 (彈出視窗以手動破防)</option>
            </select>
          </div>
        </div>
      </div>

      <button 
        onClick={handleSave}
        className="w-full bg-[#ff7233] hover:bg-[#e05e26] text-black font-semibold rounded-lg p-3 text-sm transition-all"
      >
        保存设置
      </button>
    </div>
  );
}
