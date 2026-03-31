import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { User } from '../types';

const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined) ?? '';

interface AuthContextValue {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function authPost(path: string, body: object): Promise<{ access_token: string; user: User }> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = (data as { detail?: string }).detail ?? detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json() as Promise<{ access_token: string; user: User }>;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount: validate stored token
  useEffect(() => {
    const stored = localStorage.getItem('auth_token');
    if (!stored) {
      setIsLoading(false);
      return;
    }
    fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${stored}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error('Invalid token');
        return res.json() as Promise<User>;
      })
      .then((u) => {
        setToken(stored);
        setUser(u);
      })
      .catch(() => {
        localStorage.removeItem('auth_token');
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await authPost('/auth/login', { email, password });
    localStorage.setItem('auth_token', data.access_token);
    setToken(data.access_token);
    setUser(data.user);
  }, []);

  const register = useCallback(
    async (email: string, password: string, displayName?: string) => {
      const data = await authPost('/auth/register', {
        email,
        password,
        display_name: displayName || undefined,
      });
      localStorage.setItem('auth_token', data.access_token);
      setToken(data.access_token);
      setUser(data.user);
    },
    [],
  );

  const logout = useCallback(() => {
    localStorage.removeItem('auth_token');
    setToken(null);
    setUser(null);
  }, []);

  // Listen for 401 signals from the API client (expired / revoked token)
  useEffect(() => {
    window.addEventListener('auth:logout', logout);
    return () => window.removeEventListener('auth:logout', logout);
  }, [logout]);

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
