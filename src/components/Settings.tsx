import { useState, useEffect } from 'react';
import { translations, Language } from '../utils/i18n';

interface SettingsProps {
  port: number;
  language: Language;
  onLanguageChange: (lang: Language) => void;
}

export default function Settings({ port, language, onLanguageChange }: SettingsProps) {
  const [cfg, setCfg] = useState({
    download_path: './out',
    theme: 'Dark',
    interval: '500',
    numthread: '4',
    headless_mode: 'True',
    app_language: 'zh-TW',
    conversion_mode: 'traditional'
  });

  const t = (key: string) => translations[language]?.[key] || key;

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
      if (res.ok) {
        alert(t('saveSuccess'));
        onLanguageChange(cfg.app_language as Language);
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="p-8 h-full max-w-xl flex flex-col justify-between overflow-y-auto">
      <div className="space-y-6">
        <h2 className="text-xl font-bold">{t('settingsHeader')}</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">{t('downloadPath')}</label>
            <input 
              type="text" value={cfg.download_path} onChange={e => setCfg({ ...cfg, download_path: e.target.value })}
              className="w-full bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
            />
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">{t('downloadInterval')}</label>
              <input 
                type="number" value={cfg.interval} onChange={e => setCfg({ ...cfg, interval: e.target.value })}
                className="w-full bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">{t('maxThreads')}</label>
              <input 
                type="number" value={cfg.numthread} onChange={e => setCfg({ ...cfg, numthread: e.target.value })}
                className="w-full bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">{t('headlessMode')}</label>
            <select 
              value={cfg.headless_mode} onChange={e => setCfg({ ...cfg, headless_mode: e.target.value })}
              className="w-full bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
            >
              <option value="True">{t('headlessEnabled')}</option>
              <option value="False">{t('headlessDisabled')}</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">{t('appLanguage')}</label>
              <select 
                value={cfg.app_language} onChange={e => setCfg({ ...cfg, app_language: e.target.value })}
                className="w-full bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
              >
                <option value="zh-TW">繁體中文</option>
                <option value="zh-CN">简体中文</option>
                <option value="en">English</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">{t('novelFontConversion')}</label>
              <select 
                value={cfg.conversion_mode} onChange={e => setCfg({ ...cfg, conversion_mode: e.target.value })}
                className="w-full bg-[#161920] border border-[#242936] rounded-lg p-2 text-sm focus:outline-none focus:border-[#ff7233]"
              >
                <option value="none">{t('fontNone')}</option>
                <option value="traditional">{t('fontTraditional')}</option>
                <option value="simplified">{t('fontSimplified')}</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <button 
        onClick={handleSave}
        className="w-full bg-[#ff7233] hover:bg-[#e05e26] text-black font-semibold rounded-lg p-3 text-sm transition-all mt-6"
      >
        {t('saveSettings')}
      </button>
    </div>
  );
}
