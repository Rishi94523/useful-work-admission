import { defineConfig } from 'vite';
import { resolve } from 'path';
import dts from 'vite-plugin-dts';

export default defineConfig({
  plugins: [
    dts({
      insertTypesEntry: true,
    }),
  ],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/index.ts'),
      name: 'PoUWCaptcha',
      formats: ['es', 'umd', 'iife'],
      fileName: (format) => {
        if (format === 'es') return 'pouw-captcha.esm.js';
        if (format === 'umd') return 'pouw-captcha.umd.js';
        return 'pouw-captcha.iife.js';
      },
    },
    rollupOptions: {
      external: [],
      output: {
        globals: {},
        assetFileNames: 'pouw-captcha.[ext]',
      },
    },
    sourcemap: true,
    minify: 'esbuild',
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'production'),
  },
  server: {
    port: 5173,
    cors: true,
  },
});
