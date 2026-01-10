import React, { useState } from 'react';


// 注意：这里暂时保留 Demo 的逻辑结构，后续联调时再替换为 API 调用
const App: React.FC = () => {
  // 页面配置对应的状态（Demo 里的 st.set_page_config 对应的内容）
  const pageTitle = "电气设计图纸审查AI小助手";
  document.title = pageTitle;

  // Demo 里的前端状态
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [extractedText, setExtractedText] = useState('');
  const [reviewResult, setReviewResult] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Demo 里的文件选择逻辑
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setUploadedFile(e.target.files[0]);
    }
  };

  // Demo 里的提交逻辑（暂时空实现，后续联调时调用后端 API）
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadedFile) return;

    setIsLoading(true);
    // 这里暂时不写逻辑，等迁移完成后，再替换为调用后端 /api/review 接口
    setIsLoading(false);
    // 临时用 Demo 里的提示文本占位
    setExtractedText("【迁移占位】文本提取结果将在联调后显示");
    setReviewResult("【迁移占位】AI审查结果将在联调后显示");
  };


  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '20px' }}>
      {/* Demo 里的 st.title 和说明 */}
      <h1>⚡ {pageTitle}</h1>
      <hr />
      <h3>使用说明</h3>
      <ul>
        <li>支持上传格式：PDF、PNG、JPG、JPEG、WEBP、DWG、DXF</li>
        <li>CAD 图纸(.dwg, .dxf)可上传，系统会自动转换为图片进行处理</li>
        <li>系统将自动提取文本并进行 AI 合规性审查</li>
      </ul>
      <hr />

      {/* Demo 里的 st.file_uploader */}
      <form onSubmit={handleSubmit}>
        <input
          type="file"
          onChange={handleFileChange}
          accept=".pdf,.png,.jpg,.jpeg,.webp,.dwg,.dxf"
        />
        <button type="submit" disabled={isLoading} style={{ marginLeft: '10px' }}>
          {isLoading ? '处理中...' : '上传并审查'}
        </button>
      </form>

      {/* Demo 里的 st.text_area 提取结果展示 */}
      {extractedText && (
        <div style={{ marginTop: '20px' }}>
          <h3>第一步：图纸文本提取结果</h3>
          <textarea
            value={extractedText}
            readOnly
            style={{ width: '100%', height: '200px' }}
          />
        </div>
      )}

      {/* Demo 里的 AI 审查结果展示 */}
      {reviewResult && (
        <div style={{ marginTop: '20px' }}>
          <h3>第二步：AI 智能审查结果</h3>
          <div style={{ padding: '10px', border: '1px solid #ccc' }}>
            {reviewResult}
          </div>
        </div>
      )}
    </div>
  );
};

export default App;