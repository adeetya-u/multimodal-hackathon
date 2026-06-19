import { Route, Routes, useLocation } from "react-router-dom";
import { DevNav } from "./components/DevNav";
import { LandingPage } from "./routes/LandingPage";
import { ORPage } from "./routes/ORPage";
import { PrepPage } from "./routes/PrepPage";
import { SummaryPage } from "./routes/SummaryPage";

export default function App() {
  const { pathname } = useLocation();
  const showDevNav = pathname !== "/or" && pathname !== "/";

  return (
    <>
      {showDevNav && <DevNav />}
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/prep" element={<PrepPage />} />
        <Route path="/or" element={<ORPage />} />
        <Route path="/summary" element={<SummaryPage />} />
      </Routes>
    </>
  );
}
