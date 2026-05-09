/// <reference types="vite/client" />

declare const __APP_VERSION__: string;

interface Window {
  __ONERADAR_CONFIG__?: {
    apiBaseUrl?: string;
    updateCheckUrl?: string;
  };
}
