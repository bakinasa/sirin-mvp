import { create } from "zustand";
import { persist } from "zustand/middleware";

type AuthState = {
  token: string | null;
  setToken: (token: string | null) => void;
  dark: boolean;
  toggleDark: () => void;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      setToken: (token) => set({ token }),
      dark: false,
      toggleDark: () => {
        const next = !get().dark;
        document.documentElement.classList.toggle("dark", next);
        set({ dark: next });
      },
    }),
    { name: "aistudio-auth" }
  )
);
