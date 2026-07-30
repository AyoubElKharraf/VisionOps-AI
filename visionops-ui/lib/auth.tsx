"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { API_URL } from "@/lib/api";

const TOKEN_KEY = "visionops.accessToken";
const USER_KEY = "visionops.authUser";

export type AuthUser = {
  id: string;
  username: string;
  full_name: string | null;
  role: "admin" | "operator";
  is_active: boolean;
  created_at: string;
};

type AuthStatus = {
  auth_enforced: boolean;
  api_key_enabled: boolean;
  jwt_enabled: boolean;
};

type AuthContextValue = {
  ready: boolean;
  status: AuthStatus | null;
  user: AuthUser | null;
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isAdmin: boolean;
  requiresLogin: boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const boot = async () => {
      const storedToken =
        typeof window !== "undefined" ? window.localStorage.getItem(TOKEN_KEY) : null;
      const storedUser = readStoredUser();
      if (storedToken) {
        setToken(storedToken);
        setUser(storedUser);
      }

      try {
        const res = await fetch(`${API_URL}/api/v1/auth/status`, { cache: "no-store" });
        if (res.ok) {
          const next = (await res.json()) as AuthStatus;
          setStatus(next);
          if (storedToken && next.jwt_enabled) {
            const me = await fetch(`${API_URL}/api/v1/auth/me`, {
              headers: { Authorization: `Bearer ${storedToken}` },
              cache: "no-store",
            });
            if (me.ok) {
              const profile = (await me.json()) as AuthUser;
              setUser(profile);
              window.localStorage.setItem(USER_KEY, JSON.stringify(profile));
            } else {
              window.localStorage.removeItem(TOKEN_KEY);
              window.localStorage.removeItem(USER_KEY);
              setToken(null);
              setUser(null);
            }
          }
        }
      } catch {
        setStatus({
          auth_enforced: false,
          api_key_enabled: false,
          jwt_enabled: false,
        });
      } finally {
        setReady(true);
      }
    };
    void boot();
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || "Login failed");
    }
    const body = (await res.json()) as {
      access_token: string;
      user: AuthUser;
    };
    window.localStorage.setItem(TOKEN_KEY, body.access_token);
    window.localStorage.setItem(USER_KEY, JSON.stringify(body.user));
    setToken(body.access_token);
    setUser(body.user);
  }, []);

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      ready,
      status,
      user,
      token,
      login,
      logout,
      isAdmin: user?.role === "admin",
      requiresLogin: Boolean(status?.jwt_enabled) && !token,
    }),
    [ready, status, user, token, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

export function getStoredAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}
