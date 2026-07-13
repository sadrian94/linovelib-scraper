

interface ReaderProps {
  bookId: string;
  volumeId: number;
  port: number;
  onClose: () => void;
}

export default function Reader({ bookId, volumeId, port, onClose }: ReaderProps) {
  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold">阅读器</h2>
        <button onClick={onClose} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm text-white">
          返回书架
        </button>
      </div>
      <p className="text-gray-400">正在阅读书籍: {bookId}, 卷号: {volumeId}. 后台API端口: {port}</p>
    </div>
  );
}
