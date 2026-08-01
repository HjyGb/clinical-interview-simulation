import { BrowserRouter, Routes, Route } from "react-router-dom";

function App() {
  return (
    <BrowserRouter>
      <div style={{ padding: "2rem", fontFamily: "sans-serif" }}>
        <h1>🩺 临床问诊模拟系统</h1>
        <p>Clinical Interview Simulation — AI-Powered Virtual Standardized Patient</p>
        <Routes>
          <Route path="/" element={<p>系统已就绪。开始开发问诊模块。</p>} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
