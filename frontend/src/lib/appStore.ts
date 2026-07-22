import { create } from "zustand";

type Theme = "light" | "dark";

interface AppStore {
  theme: Theme;
  toggleTheme: () => void;
}

export const useAppStore = create<AppStore>((set) => ({
  theme: "light",
  toggleTheme: () => set((state) => ({ theme: state.theme === "light" ? "dark" : "light" })),
}));
