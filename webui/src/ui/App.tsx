import { AnimatePresence, motion } from "framer-motion";
import React from "react";
import { HashRouter, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { PromptProvider } from "./components/PromptProvider";
import { SnowflakeField } from "./components/SnowflakeField";
import { ChatPage } from "./pages/ChatPage";
import { SettingsPage } from "./pages/SettingsPage";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-screen">
      <SnowflakeField />
      <div className="relative z-10 border-b border-[#87CEEB]/35 bg-white/70 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <div className="text-sm font-semibold tracking-wide text-slate-900">FASS Hub</div>
          <nav className="flex items-center gap-3 text-sm">
            <NavLink className={({ isActive }) => (isActive ? "text-[#FFB6C1]" : "text-slate-500 hover:text-slate-900")} to="/chat">
              Chat
            </NavLink>
            <NavLink className={({ isActive }) => (isActive ? "text-[#FFB6C1]" : "text-slate-500 hover:text-slate-900")} to="/settings">
              Settings
            </NavLink>
          </nav>
          <div className="flex-1" />
        </div>
      </div>
      <div className="relative z-10 mx-auto max-w-6xl px-4 py-6">{children}</div>
    </div>
  );
}

function Page({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route
          path="/"
          element={
            <Page>
              <ChatPage />
            </Page>
          }
        />
        <Route
          path="/chat"
          element={
            <Page>
              <ChatPage />
            </Page>
          }
        />
        <Route
          path="/settings"
          element={
            <Page>
              <SettingsPage />
            </Page>
          }
        />
      </Routes>
    </AnimatePresence>
  );
}

export function App() {
  return (
    <HashRouter>
      <PromptProvider>
        <Shell>
          <AnimatedRoutes />
        </Shell>
      </PromptProvider>
    </HashRouter>
  );
}
