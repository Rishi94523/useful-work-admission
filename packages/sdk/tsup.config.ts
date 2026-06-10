import { defineConfig } from 'tsup';

export default defineConfig({
  entry: {
    index: 'src/index.ts',
    server: 'src/server.ts',
    'vanilla/index': 'src/vanilla/index.ts',
    'react/index': 'src/react/index.tsx',
    'vue/index': 'src/vue/index.ts',
  },
  format: ['cjs', 'esm'],
  dts: true,
  sourcemap: true,
  clean: true,
  splitting: false,
  external: ['@pouw/widget', 'react', 'react-dom', 'vue'],
  outExtension({ format }) {
    return {
      js: format === 'esm' ? '.esm.js' : '.js',
    };
  },
});
