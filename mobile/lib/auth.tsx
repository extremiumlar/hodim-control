import { createContext, useCallback, useContext, useEffect, useState } from "react";

import {
  clearStoredToken,
  getMe,
  getStoredToken,
  setStoredToken,
  TokenOut,
  UserOut,
} from "./api";

interface AuthState {
  loading: boolean;
  user: UserOut | null;
  signIn: (token: TokenOut) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  loading: true,
  user: null,
  signIn: async () => {},
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<UserOut | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const token = await getStoredToken();
        if (token) setUser(await getMe());
      } catch {
        await clearStoredToken();
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const signIn = useCallback(async (token: TokenOut) => {
    await setStoredToken(token.access_token);
    setUser(token.user);
  }, []);

  const signOut = useCallback(async () => {
    await clearStoredToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ loading, user, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
