import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import CaseListPage from "./pages/CaseListPage";
import HistoryPage from "./pages/HistoryPage";
import InterviewPage from "./pages/InterviewPage";
import AssessmentPage from "./pages/AssessmentPage";
import ToastContainer from "./components/ui/ToastContainer";

function App() {
  return (
    <BrowserRouter>
      <ToastContainer />
      <Routes>
        <Route path="/" element={<Navigate to="/cases" replace />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/cases" element={<CaseListPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/interview/:id" element={<InterviewPage />} />
        <Route path="/assessment/:id" element={<AssessmentPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
