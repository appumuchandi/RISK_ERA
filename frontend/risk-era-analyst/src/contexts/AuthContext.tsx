import { createContext, useContext, useState, useEffect } from "react";
import type { ReactNode } from "react";

type AuthContextValue = {
  token: string | null;
  username: string | null;
  role: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export const AuthProvider: React.FC<{ children: ReactNode; initialToken?: string }> = ({
  children,
  initialToken,
}) => {
  const [token, setToken] = useState<string | null>(() => initialToken || localStorage.getItem("risk_era_token"));
  const [username, setUsername] = useState<string | null>(() => localStorage.getItem("risk_era_username"));
  const [role, setRole] = useState<string | null>(() => localStorage.getItem("risk_era_role"));
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(false);
  }, []);

  const login = async (usernameIn: string, password: string) => {
    setIsLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: usernameIn, password }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || "Invalid credentials");
      }
      const access = data.access_token as string;
      const r = (data.role as string) || "analyst";
      setToken(access);
      setUsername(usernameIn);
      setRole(r);
      localStorage.setItem("risk_era_token", access);
      localStorage.setItem("risk_era_username", usernameIn);
      localStorage.setItem("risk_era_role", r);
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    setToken(null);
    setUsername(null);
    setRole(null);
    localStorage.removeItem("risk_era_token");
    localStorage.removeItem("risk_era_username");
    localStorage.removeItem("risk_era_role");
  };

  return (
    <AuthContext.Provider value={{ token, username, role, login, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
};

export default AuthContext;
