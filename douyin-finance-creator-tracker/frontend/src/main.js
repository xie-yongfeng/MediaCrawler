import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './style.css'

function syncViewportHeight() {
  const height = window.visualViewport?.height || window.innerHeight;
  document.documentElement.style.setProperty('--app-viewport-height', `${Math.round(height)}px`);
}

syncViewportHeight();
window.addEventListener('resize', syncViewportHeight, { passive: true });
window.addEventListener('orientationchange', syncViewportHeight, { passive: true });
window.visualViewport?.addEventListener('resize', syncViewportHeight, { passive: true });
window.visualViewport?.addEventListener('scroll', syncViewportHeight, { passive: true });

createApp(App).use(router).mount('#app')
