import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  // Relatief, zodat dezelfde build op GitHub Pages en later op de hub werkt.
  base: "./",
  plugins: [
    VitePWA({
      registerType: "prompt",
      injectRegister: false,
      includeAssets: ["icon.svg", "apple-touch-icon.png"],
      manifestFilename: "manifest.webmanifest",
      manifest: {
        name: "Sequo",
        short_name: "Sequo",
        lang: "nl",
        display: "standalone",
        start_url: "./",
        scope: "./",
        background_color: "#F2F2F7",
        theme_color: "#F2F2F7",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: { clientsClaim: true, globPatterns: ["**/*.{js,css,html,svg,png,woff2}"] },
    }),
  ],
});
