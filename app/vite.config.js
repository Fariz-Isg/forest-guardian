import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { createFirmsHandler } from './firms-proxy.js'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // .env lives at the project root (one level up), alongside data/ and model/
  const env = loadEnv(mode, process.cwd() + '/..', 'FIRMS_')

  function firmsProxyPlugin() {
    return {
      name: 'firms-proxy',
      configureServer(server) {
        server.middlewares.use('/api/firms', createFirmsHandler(env.FIRMS_MAP_KEY))
      },
    }
  }

  return {
    envDir: '..',
    plugins: [react(), firmsProxyPlugin()],
    optimizeDeps: { exclude: ['maplibre-gl'] },
  }
})
