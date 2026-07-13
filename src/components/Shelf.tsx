interface ShelfProps {
  port: number;
  onRead: (bookId: string, volumeId: number) => void;
}

export default function Shelf({ port, onRead }: ShelfProps) {
  return (
    <div className="p-8">
      <h2 className="text-xl font-bold mb-6">本地书架</h2>
      <p className="text-gray-400 mb-4">书架组件暂未实现。正在运行于端口: {port}</p>
      <button onClick={() => onRead("2704", 1)} className="px-4 py-2 bg-[#ff7233] hover:bg-[#e05e26] text-black font-semibold rounded text-sm transition-all">
        测试打开阅读器 (书籍 2704, 第 1 卷)
      </button>
    </div>
  );
}
