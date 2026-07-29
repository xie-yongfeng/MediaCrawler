import { createRouter, createWebHistory } from "vue-router";
import BriefPage from "../pages/BriefPage.vue";
import SettingsPage from "../pages/SettingsPage.vue";
import TimelinePage from "../pages/TimelinePage.vue";
import WatchlistPage from "../pages/WatchlistPage.vue";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/", redirect: { name: "brief" } },
    { path: "/brief", name: "brief", component: BriefPage },
    { path: "/watchlist", name: "watchlist", component: WatchlistPage },
    { path: "/timeline", name: "timeline", component: TimelinePage },
    { path: "/settings", name: "settings", component: SettingsPage },
  ],
});

export default router;
