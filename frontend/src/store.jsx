/*
 * store.jsx — shared app state (resume result, interview session, final report).
 * Saved in sessionStorage so a page refresh does not lose progress.
 */
import { createContext, useCallback, useContext, useState } from "react";

const KEY = "careerlens-state";
const Ctx = createContext(null);

const EMPTY = { role: "SDE", jdText: "", resume: null, sessionId: null, report: null };

function load() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY));
    return saved ? { ...EMPTY, ...saved } : EMPTY;
  } catch {
    return EMPTY;
  }
}

export function AppProvider({ children }) {
  const [state, setState] = useState(load);

  const update = useCallback((patch) => {
    setState((prev) => {
      const next = { ...prev, ...patch };
      try {
        sessionStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        /* storage full or blocked: keep working in memory */
      }
      return next;
    });
  }, []);

  return <Ctx.Provider value={{ state, update }}>{children}</Ctx.Provider>;
}

export function useApp() {
  return useContext(Ctx);
}
