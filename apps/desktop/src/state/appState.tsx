import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, createApiClient } from "../api/client";
import type { ApiBootstrapResponse, ApiFolderEntry, ApiHealth, ApiProvider } from "../api/types";
import {
  UPDATE_CHECK_INTERVAL_MS,
  checkForAppUpdates,
  getCurrentAppVersion,
  type UpdateCheckState
} from "../utils/updateCheck";

const STORAGE_KEY = "oneradar.desktop.state";
const RUNTIME_API_URL = window.__ONERADAR_CONFIG__?.apiBaseUrl;
const DEFAULT_API_URL =
  RUNTIME_API_URL ??
  import.meta.env.VITE_ONERADAR_DEFAULT_API_URL ??
  (import.meta.env.DEV ? "" : "http://127.0.0.1:8000");

type ThemeMode = "system" | "light" | "dark";
type ResolvedTheme = "light" | "dark";

type SavedState = {
  apiBaseUrl: string;
  themeMode: ThemeMode;
};

type ConnectionState = "idle" | "checking" | "connected" | "unavailable";

type AppStateValue = {
  apiBaseUrl: string;
  setApiBaseUrl: (next: string) => void;
  themeMode: ThemeMode;
  setThemeMode: (next: ThemeMode) => void;
  resolvedTheme: ResolvedTheme;
  health: ApiHealth | null;
  connectionState: ConnectionState;
  lastError: string | null;
  workspace: ApiBootstrapResponse | null;
  folders: ApiFolderEntry[];
  providers: ApiProvider[];
  updateCheck: UpdateCheckState;
  refreshConnection: (targetBaseUrl?: string) => Promise<void>;
  loadWorkspace: () => Promise<void>;
  loadFolders: () => Promise<ApiFolderEntry[]>;
  loadProviders: () => Promise<ApiProvider[]>;
  checkForUpdates: () => Promise<UpdateCheckState>;
};

const AppStateContext = createContext<AppStateValue | null>(null);

function shouldPreferRuntimeApiUrl(savedApiBaseUrl?: string): boolean {
  if (RUNTIME_API_URL === undefined) {
    return false;
  }
  if (!savedApiBaseUrl) {
    return true;
  }
  return [
    "http://127.0.0.1:8000",
    "http://192.168.100.55:8000",
    "http://192.168.100.55:18000"
  ].includes(savedApiBaseUrl);
}

function loadSavedState(): SavedState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { apiBaseUrl: DEFAULT_API_URL, themeMode: "system" };
    }
    const parsed = JSON.parse(raw) as Partial<SavedState>;
    return {
      apiBaseUrl: shouldPreferRuntimeApiUrl(parsed.apiBaseUrl) ? DEFAULT_API_URL : parsed.apiBaseUrl || DEFAULT_API_URL,
      themeMode: parsed.themeMode === "light" || parsed.themeMode === "dark" ? parsed.themeMode : "system"
    };
  } catch {
    return { apiBaseUrl: DEFAULT_API_URL, themeMode: "system" };
  }
}

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") {
    return "dark";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [savedState] = useState<SavedState>(() => loadSavedState());
  const [apiBaseUrl, setApiBaseUrl] = useState(savedState.apiBaseUrl);
  const [themeMode, setThemeMode] = useState<ThemeMode>(savedState.themeMode);
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(getSystemTheme());
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [workspace, setWorkspace] = useState<ApiBootstrapResponse | null>(null);
  const [folders, setFolders] = useState<ApiFolderEntry[]>([]);
  const [providers, setProviders] = useState<ApiProvider[]>([]);
  const [updateCheck, setUpdateCheck] = useState<UpdateCheckState>({ status: "idle", currentVersion: __APP_VERSION__ });
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [lastError, setLastError] = useState<string | null>(null);

  useEffect(() => {
    const state: SavedState = { apiBaseUrl, themeMode };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [apiBaseUrl, themeMode]);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const applyTheme = () => {
      const nextTheme = themeMode === "system" ? (mediaQuery.matches ? "dark" : "light") : themeMode;
      setResolvedTheme(nextTheme);
    };

    applyTheme();

    if (themeMode !== "system") {
      return;
    }

    const handler = () => applyTheme();
    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", handler);
      return () => mediaQuery.removeEventListener("change", handler);
    }

    mediaQuery.addListener(handler);
    return () => mediaQuery.removeListener(handler);
  }, [themeMode]);

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.style.colorScheme = resolvedTheme;
  }, [resolvedTheme]);

  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);

  const loadWorkspace = async () => {
    setLastError(null);
    const [healthResult, bootstrapResult, foldersResult, providersResult] = await Promise.allSettled([
      client.health(),
      client.bootstrap(),
      client.listFolders(),
      client.listProviders()
    ]);

    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
      setConnectionState("connected");
    } else {
      setHealth(null);
      setConnectionState("unavailable");
      setLastError(healthResult.reason instanceof Error ? healthResult.reason.message : "连接失败");
    }

    if (bootstrapResult.status === "fulfilled") {
      setWorkspace(bootstrapResult.value);
    }

    if (foldersResult.status === "fulfilled") {
      setFolders(foldersResult.value.items);
    }

    if (providersResult.status === "fulfilled") {
      setProviders(providersResult.value.items);
    }
  };

  const refreshConnection = async (targetBaseUrl?: string) => {
    const activeBaseUrl = targetBaseUrl?.trim() || apiBaseUrl;
    const activeClient = createApiClient(activeBaseUrl);
    setConnectionState("checking");
    setLastError(null);
    try {
      const nextHealth = await activeClient.health();
      setApiBaseUrl(activeBaseUrl);
      setHealth(nextHealth);
      setConnectionState("connected");
      const [bootstrapResult, foldersResult, providersResult] = await Promise.allSettled([
        activeClient.bootstrap(),
        activeClient.listFolders(),
        activeClient.listProviders()
      ]);
      if (bootstrapResult.status === "fulfilled") {
        setWorkspace(bootstrapResult.value);
      }
      if (foldersResult.status === "fulfilled") {
        setFolders(foldersResult.value.items);
      }
      if (providersResult.status === "fulfilled") {
        setProviders(providersResult.value.items);
      }
    } catch (error) {
      setHealth(null);
      setConnectionState("unavailable");
      setLastError(error instanceof Error ? error.message : "连接失败");
    }
  };

  const loadFolders = async () => {
    try {
      const response = await client.listFolders();
      setFolders(response.items);
      return response.items;
    } catch (error) {
      setLastError(error instanceof ApiError ? error.message : "读取知识库失败");
      return [];
    }
  };

  const loadProviders = async () => {
    try {
      const response = await client.listProviders();
      setProviders(response.items);
      return response.items;
    } catch (error) {
      setLastError(error instanceof ApiError ? error.message : "读取模型服务失败");
      return [];
    }
  };

  const checkForUpdates = async () => {
    const currentVersion = await getCurrentAppVersion();
    setUpdateCheck((current) => ({ ...current, status: "checking", currentVersion }));
    const result = await checkForAppUpdates(currentVersion);
    setUpdateCheck(result);
    return result;
  };

  useEffect(() => {
    void loadWorkspace();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void checkForUpdates();
    const intervalId = window.setInterval(() => {
      void checkForUpdates();
    }, UPDATE_CHECK_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value: AppStateValue = {
    apiBaseUrl,
    setApiBaseUrl,
    themeMode,
    setThemeMode,
    resolvedTheme,
    health,
    connectionState,
    lastError,
    workspace,
    folders,
    providers,
    updateCheck,
    refreshConnection,
    loadWorkspace,
    loadFolders,
    loadProviders,
    checkForUpdates
  };

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const value = useContext(AppStateContext);
  if (!value) {
    throw new Error("useAppState must be used inside AppStateProvider");
  }
  return value;
}


