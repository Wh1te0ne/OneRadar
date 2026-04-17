import type {
  ApiBilibiliCookieParseResponse,
  ApiBilibiliIntegrationSettings,
  ApiBootstrapResponse,
  ApiCreateFolderResponse,
  ApiFeedPreviewResponse,
  ApiFolderEntry,
  ApiHealth,
  ApiImportResponse,
  ApiItemDetail,
  ApiItemSummary,
  ApiListResponse,
  ApiMoveItemResponse,
  ApiProvider
} from "./types";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  const normalized = baseUrl.trim().replace(/\/+$/, "");
  return normalized.endsWith("/api") ? normalized.slice(0, -4) : normalized;
}

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!text) {
    return {} as T;
  }

  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError("服务端返回了无法解析的数据", response.status);
  }
}

async function request<T>(baseUrl: string, path: string, options: RequestInit = {}): Promise<T> {
  try {
    const response = await fetch(normalizeBaseUrl(baseUrl) + path, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers ?? {})
      }
    });

    if (!response.ok) {
      let message = "请求失败：" + response.status;
      try {
        const body = await response.clone().json();
        const detail = typeof body?.detail === "string" ? body.detail : typeof body?.message === "string" ? body.message : undefined;
        if (detail) {
          message = detail;
        }
      } catch {
        // fall back to status-only message
      }
      throw new ApiError(message, response.status);
    }

    return readJson<T>(response);
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(error instanceof Error ? error.message : "网络请求失败");
  }
}

async function requestFirstAvailable<T>(baseUrl: string, paths: string[], options: RequestInit = {}): Promise<T> {
  let lastError: unknown;
  for (const path of paths) {
    try {
      return await request<T>(baseUrl, path, options);
    } catch (error) {
      lastError = error;
      if (error instanceof ApiError && error.status && error.status !== 404 && error.status !== 405) {
        throw error;
      }
    }
  }
  throw lastError instanceof Error ? lastError : new ApiError("请求失败");
}

export function createApiClient(baseUrl: string) {
  return {
    health: () => request<ApiHealth>(baseUrl, "/api/health"),
    bootstrap: () => requestFirstAvailable<ApiBootstrapResponse>(baseUrl, ["/api/auth/bootstrap", "/api/bootstrap"]),
    listFolders: () => requestFirstAvailable<{ items: ApiFolderEntry[] }>(baseUrl, ["/api/items/folders", "/api/folders"]),
    createFolder: (name: string) =>
      request<ApiCreateFolderResponse>(baseUrl, "/api/items/folders", {
        method: "POST",
        body: JSON.stringify({ name })
      }),
    listProviders: () => request<ApiListResponse<ApiProvider>>(baseUrl, "/api/providers"),
    getFeedPreview: (url: string, limit = 12) => {
      const params = new URLSearchParams({ url, limit: String(limit) });
      return request<ApiFeedPreviewResponse>(baseUrl, "/api/feeds/preview?" + params.toString());
    },
    listItems: (query?: { keyword?: string; folderId?: string; inboxOnly?: boolean; page?: number; pageSize?: number }) => {
      const params = new URLSearchParams();
      if (query?.keyword) {
        params.set("keyword", query.keyword);
      }
      if (query?.folderId) {
        params.set("folder_id", query.folderId);
      }
      if (typeof query?.inboxOnly === "boolean") {
        params.set("inbox_only", String(query.inboxOnly));
      }
      if (query?.page) {
        params.set("page", String(query.page));
      }
      if (query?.pageSize) {
        params.set("page_size", String(query.pageSize));
      }
      const suffix = params.toString() ? "?" + params.toString() : "";
      return request<ApiListResponse<ApiItemSummary>>(baseUrl, "/api/items" + suffix);
    },
    getItem: (itemId: string) => request<ApiItemDetail>(baseUrl, "/api/items/" + itemId),

    getBilibiliIntegration: () => request<ApiBilibiliIntegrationSettings>(baseUrl, "/api/settings/integrations/bilibili"),
    updateBilibiliIntegration: (payload: {
      is_enabled: boolean;
      cookie_header?: string;
      sessdata?: string;
      bili_jct?: string;
      buvid3?: string;
    }) =>
      request<ApiBilibiliIntegrationSettings>(baseUrl, "/api/settings/integrations/bilibili", {
        method: "PUT",
        body: JSON.stringify(payload)
      }),
    parseBilibiliCookie: (cookieHeader: string) =>
      request<ApiBilibiliCookieParseResponse>(baseUrl, "/api/settings/integrations/bilibili/parse-cookie", {
        method: "POST",
        body: JSON.stringify({ cookie_header: cookieHeader })
      }),
    importItem: (url: string, sourceHint?: string) =>
      request<ApiImportResponse>(baseUrl, "/api/items/import", {
        method: "POST",
        body: JSON.stringify({
          url,
          ...(sourceHint ? { source_hint: sourceHint } : {})
        })
      }),
    moveItem: (itemId: string, folderId: string) =>
      request<ApiMoveItemResponse>(baseUrl, "/api/items/" + itemId + "/move", {
        method: "POST",
        body: JSON.stringify({ folder_id: folderId })
      })
  };
}

