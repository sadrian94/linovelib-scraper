

interface SettingsProps {
  port: number;
}

export default function Settings({ port }: SettingsProps) {
  return (
    <div className="p-8">
      <h2 className="text-xl font-bold mb-6">软件设置</h2>
      <p className="text-gray-400">设置组件暂未实现。后台API端口: {port}</p>
    </div>
  );
}
