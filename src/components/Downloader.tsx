import { useState, useEffect, useRef } from 'react';

export default function Downloader({ port }: { port: number }) {
  const [bookId, setBookId] = useState('');
  const [volumeId, setVolumeId] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('idle');
  const [inputPrompt, setInputPrompt] = useState('');
  const [inputOptions, setInputOptions] = useState<string[]>([]);
  const [submitVal, setSubmitVal] = useState('');

  const logEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const connectWS = () => {
      const ws = new WebSocket(`ws://127.0.0.1:${port}/api/download/ws`);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'init') {
          setLogs(data.logs);
          setProgress(data.progress);
          setStatus(data.status);
          setInputPrompt(data.input_prompt);
        } else if (data.type === 'log') {
          setLogs(prev => [...prev, data.message]);
        } else if (data.type === 'progress') {
          setProgress(data.value);
        } else if (data.type === 'status') {
          setStatus(data.status);
          if (data.status !== 'input_required') {
            setInputPrompt('');
          }
        } else if (data.type === 'input_prompt') {
          setInputPrompt(data.message);
          setInputOptions(data.options || []);
          setSubmitVal('');
          setStatus('input_required');
        }
      };

      ws.onclose = () => {
        setTimeout(connectWS, 2000);
      };
    };

    connectWS();
    return () => wsRef.current?.close();
  }, [port]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const handleDownload = async () => {
    if (!bookId) return;
    setLogs([]);
    setProgress(0);
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book_id: bookId, volume_id: volumeId })
      });
      if (!res.ok) alert("Error starting download");
    } catch (e) {
      console.error(e);
    }
  };

  const handleSubmitInput = async () => {
    try {
      await fetch(`http://127.0.0.1:${port}/api/download/submit_input`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: submitVal })
      });
      setInputPrompt('');
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="p-8 h-full flex flex-col">
      <h2 className="text-xl font-bold mb-6">下载轻小说</h2>
      
      {/* Controls Grid */}
      <div className="grid grid-cols-3 gap-4 mb-6 bg-[#161920] border border-[#242936] p-4 rounded-xl">
        <div>
          <label className="block text-xs text-gray-400 mb-1">书籍 ID</label>
          <input 
            type="text" value={bookId} onChange={e => setBookId(e.target.value)}
            placeholder="例如 2704" className="w-full bg-[#0d0e12] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">卷号 (選填，多卷以 - 或逗號分隔)</label>
          <input 
            type="text" value={volumeId} onChange={e => setVolumeId(e.target.value)}
            placeholder="空代表列出目录, 1-3 代表1至3卷" className="w-full bg-[#0d0e12] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
          />
        </div>
        <div className="flex items-end">
          <button 
            onClick={handleDownload} disabled={status === 'downloading' || status === 'input_required'}
            className="w-full bg-[#ff7233] hover:bg-[#e05e26] disabled:bg-gray-700 text-black font-semibold rounded-lg p-2 text-sm transition-all"
          >
            {status === 'downloading' ? '下载中...' : '开始下载'}
          </button>
        </div>
      </div>

      {/* Console logs */}
      <div className="flex-1 bg-[#090a0f] border border-[#242936] rounded-xl p-4 font-mono text-xs overflow-y-auto space-y-1 mb-4">
        {logs.map((log, idx) => (
          <div key={idx} className="text-gray-300 whitespace-pre-wrap">{log}</div>
        ))}
        <div ref={logEndRef} />
      </div>

      {/* Progress Display */}
      {progress > 0 && (
        <div className="w-full bg-[#161920] h-2 rounded-full overflow-hidden mb-2">
          <div className="bg-[#ff7233] h-full transition-all duration-300" style={{ width: `${progress}%` }} />
        </div>
      )}

      {/* Input Dialog Overlay */}
      {status === 'input_required' && (
        <div className="absolute inset-0 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-[#161920] border border-[#242936] p-6 rounded-xl w-96 max-w-full">
            <h3 className="font-semibold mb-2">需要手动输入</h3>
            <p className="text-sm text-gray-400 mb-4">{inputPrompt}</p>

            {inputOptions.length > 0 ? (
              <select 
                value={submitVal} onChange={e => setSubmitVal(e.target.value)}
                className="w-full bg-[#0d0e12] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none mb-4"
              >
                <option value="">-- 请选择 --</option>
                {inputOptions.map((opt, i) => <option key={i} value={opt}>{opt}</option>)}
              </select>
            ) : (
              <input 
                type="text" value={submitVal} onChange={e => setSubmitVal(e.target.value)}
                className="w-full bg-[#0d0e12] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none mb-4"
              />
            )}

            <button 
              onClick={handleSubmitInput}
              className="w-full bg-[#ff7233] hover:bg-[#e05e26] text-black font-semibold rounded-lg p-2 text-sm"
            >
              确定
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
