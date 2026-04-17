import { invoke, isTauri } from "@tauri-apps/api/core";

export type NativeBilibiliCookieSource = {
  browserId: string;
  browserName: string;
  profileName: string;
  cookieCount: number;
  hasFullSet: boolean;
  cookieHeader: string;
  sessdata?: string | null;
  biliJct?: string | null;
  buvid3?: string | null;
  sessdataPreview?: string | null;
  biliJctPreview?: string | null;
  buvid3Preview?: string | null;
};

export type NativeBilibiliCookieReadResponse = {
  selected?: NativeBilibiliCookieSource | null;
  sources: NativeBilibiliCookieSource[];
  message: string;
};

export function isDesktopTauri() {
  return isTauri();
}

export async function readLocalBilibiliCookie() {
  if (!isTauri()) {
    throw new Error("该功能仅在 OneRadar 桌面版可用。");
  }
  return invoke<NativeBilibiliCookieReadResponse>("read_local_bilibili_cookie");
}
