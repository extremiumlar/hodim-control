import { createContext, useCallback, useContext, useEffect, useState } from "react";

import {
  ApiError,
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
      } catch (e) {
        // FAQAT 401 da chiqaramiz. Ilgari HAR QANDAY xato tokenni
        // o'chirardi — ya'ni internetsiz joyda ilovani ochgan xodim
        // (aynan davomat belgilaydigan payt) tizimdan chiqib qolardi va
        // qaytadan Telegram orqali kirishga majbur bo'lardi.
        // Haqiqiy bekor qilish `lib/api.ts` da 401 javobida bajariladi.
        if (e instanceof ApiError && e.status === 401) {
          await clearStoredToken();
        }
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
    // MA'LUM CHEKLOV: WebView'ning `localStorage`iga kiritilgan JWT nusxasi
    // (`components/EmbeddedWeb.tsx`) shu yerdan tozalanmaydi —
    // `clearCache` faqat O'RNATILGAN WebView ref'i orqali chaqiriladi, chiqish
    // paytida esa hech qanday WebView ochiq emas. Amaliy ta'siri cheklangan:
    // bo'lim ekranlari saqlangan tokensiz umuman ochilmaydi (`useWebPhase`).
    // To'liq yechim — WebView'ga 30 kunlik JWT o'rniga qisqa muddatli
    // alohida token berish (audit hisoboti, B3-5); o'shanda bu qoldiq
    // bir necha daqiqada o'z-o'zidan yaroqsiz bo'ladi.
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
