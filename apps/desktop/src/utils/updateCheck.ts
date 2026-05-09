import { getVersion } from "@tauri-apps/api/app";
import { isDesktopTauri } from "../api/native";

export const UPDATE_CHECK_INTERVAL_MS = 10 * 60 * 1000;

const DEFAULT_UPDATE_CHECK_URL = "https://api.github.com/repos/Wh1te0ne/OneRadar/releases/latest";
const UPDATE_CHECK_URL =
  window.__ONERADAR_CONFIG__?.updateCheckUrl ||
  import.meta.env.VITE_ONERADAR_UPDATE_CHECK_URL ||
  DEFAULT_UPDATE_CHECK_URL;

export type UpdateCheckStatus = "idle" | "checking" | "current" | "available" | "error";

export type UpdateCheckState = {
  status: UpdateCheckStatus;
  currentVersion: string;
  latestVersion?: string;
  releaseName?: string;
  releaseUrl?: string;
  notes?: string;
  checkedAt?: string;
  message?: string;
};

type UpdateManifest = {
  version?: string;
  tag_name?: string;
  name?: string;
  html_url?: string;
  url?: string;
  notes?: string;
  body?: string;
  published_at?: string;
};

function cleanVersion(version: string | undefined): number[] {
  if (!version) return [];
  const cleaned = version.trim().replace(/^[vV]/, "").split(/[+-]/)[0];
  return cleaned.split(".").map((part) => {
    const match = part.match(/^\d+/);
    return match ? Number(match[0]) : 0;
  });
}

function isNewerVersion(latest: string | undefined, current: string) {
  const latestParts = cleanVersion(latest);
  const currentParts = cleanVersion(current);
  if (!latestParts.length || !currentParts.length) return false;

  const maxLength = Math.max(latestParts.length, currentParts.length);
  for (let index = 0; index < maxLength; index += 1) {
    const latestPart = latestParts[index] ?? 0;
    const currentPart = currentParts[index] ?? 0;
    if (latestPart > currentPart) return true;
    if (latestPart < currentPart) return false;
  }
  return false;
}

export async function getCurrentAppVersion() {
  if (isDesktopTauri()) {
    try {
      return await getVersion();
    } catch {
      return __APP_VERSION__;
    }
  }
  return __APP_VERSION__;
}

export async function checkForAppUpdates(currentVersion: string): Promise<UpdateCheckState> {
  try {
    const response = await fetch(UPDATE_CHECK_URL, {
      headers: {
        Accept: "application/json",
      },
    });
    if (!response.ok) {
      throw new Error(`更新信息读取失败：${response.status}`);
    }

    const manifest = (await response.json()) as UpdateManifest;
    const latestVersion = manifest.version ?? manifest.tag_name;
    if (!latestVersion) {
      throw new Error("更新信息缺少版本号。");
    }

    const available = isNewerVersion(latestVersion, currentVersion);
    return {
      status: available ? "available" : "current",
      currentVersion,
      latestVersion,
      releaseName: manifest.name,
      releaseUrl: manifest.html_url ?? manifest.url,
      notes: manifest.notes ?? manifest.body,
      checkedAt: new Date().toISOString(),
      message: available ? "发现新版本。" : "当前已经是最新版本。",
    };
  } catch (error) {
    return {
      status: "error",
      currentVersion,
      checkedAt: new Date().toISOString(),
      message: error instanceof Error ? error.message : "更新检查失败。",
    };
  }
}
