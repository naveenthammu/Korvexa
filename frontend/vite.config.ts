import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  envDir: "..",
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    exclude: ["node_modules/**", "dist/**", "tests/**"],
  },
  server: {
    port: 5173,
  },
});
