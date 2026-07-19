import { createContext, useContext, useState, useCallback } from "react";
import { authApi } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("costguard_token"));

  const login = useCallback(async (email, password) => {
    const res = await authApi.login(email, password);
    const t = res.data.access_token;
    localStorage.setItem("costguard_token", t);
    setToken(t);
    return t;
  }, []);

  const signup = useCallback(async (orgName, email, password) => {
    await authApi.signup({ organization_name: orgName, email, password });
    return login(email, password);
  }, [login]);

  const logout = useCallback(() => {
    localStorage.removeItem("costguard_token");
    setToken(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, isAuthenticated: !!token, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
