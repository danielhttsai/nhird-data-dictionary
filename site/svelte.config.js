import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: '404.html',
      precompress: false,
      strict: true
    }),
    // GH Pages serves under https://<user>.github.io/<repo>/
    // set NHIRD_BASE_PATH=/nhird-data-dictionary at build time to enable
    paths: {
      base: process.env.NHIRD_BASE_PATH || ''
    },
    prerender: {
      handleHttpError: ({ path, message }) => {
        // ignore missing 404 for fallback
        if (path === '/404') return;
        throw new Error(message);
      }
    }
  }
};
