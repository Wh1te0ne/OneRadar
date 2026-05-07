import type {
  ApiBilibiliCookieParseResponse,
  ApiBilibiliIntegrationSettings,
  ApiBilibiliPreviewResponse,
  ApiBilibiliQrcodeGenerateResponse,
  ApiBilibiliQrcodePollResponse,
  ApiBootstrapResponse,
  ApiCollection,
  ApiCreateFolderResponse,
  ApiDailyNewsReportResponse,
  ApiFeedArticlePreviewResponse,
  ApiFeedPreviewResponse,
  ApiFeedRefreshResponse,
  ApiFeedStateResponse,
  ApiFolderEntry,
  ApiHealth,
  ApiHighlight,
  ApiImportResponse,
  ApiItemDetail,
  ApiItemSummary,
  ApiListResponse,
  ApiMoveItemResponse,
  ApiNote,
  ApiPodcastEpisode,
  ApiPodcastSearchItem,
  ApiPodcastSubscription,
  ApiProvider,
  ApiProviderPayload,
  ApiProviderTestResponse,
  ApiReadingState,
  ApiReadingStateUpdatePayload,
  ApiTag,
  ApiItemTaskResponse,
  ApiTaskEntry
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
    updateFolder: (folderId: string, name: string) =>
      request<ApiCreateFolderResponse>(baseUrl, "/api/items/folders/" + folderId, {
        method: "PATCH",
        body: JSON.stringify({ name })
      }),
    deleteFolder: (folderId: string) =>
      request<{ id: string; deleted: boolean; moved_item_count: number }>(baseUrl, "/api/items/folders/" + folderId, {
        method: "DELETE"
      }),
    listProviders: () => request<ApiListResponse<ApiProvider>>(baseUrl, "/api/providers"),
    createProvider: (payload: ApiProviderPayload) =>
      request<ApiProvider>(baseUrl, "/api/providers", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    updateProvider: (providerId: string, payload: ApiProviderPayload) =>
      request<ApiProvider>(baseUrl, "/api/providers/" + providerId, {
        method: "PUT",
        body: JSON.stringify(payload)
      }),
    deleteProvider: (providerId: string) =>
      request<{ id: string; deleted: boolean }>(baseUrl, "/api/providers/" + providerId, {
        method: "DELETE"
      }),
    testProvider: (providerId: string) =>
      request<ApiProviderTestResponse>(baseUrl, "/api/providers/" + providerId + "/test", {
        method: "POST"
      }),
    getFeedPreview: (url: string, limit = 0) => {
      const params = new URLSearchParams({ url, limit: String(limit) });
      return request<ApiFeedPreviewResponse>(baseUrl, "/api/feeds/preview?" + params.toString());
    },
    getFeedState: () => request<ApiFeedStateResponse>(baseUrl, "/api/feeds/state"),
    cacheFeedPreview: (feed: ApiFeedPreviewResponse) =>
      request<ApiFeedStateResponse>(baseUrl, "/api/feeds/cache", {
        method: "POST",
        body: JSON.stringify({ feed })
      }),
    markFeedEntryRead: (entryKey: string) =>
      request<ApiFeedStateResponse>(baseUrl, "/api/feeds/read", {
        method: "POST",
        body: JSON.stringify({ entry_key: entryKey })
      }),
    markFeedSourceError: (sourceUrl: string, errorMessage: string, siteTitle?: string | null) =>
      request<ApiFeedStateResponse>(baseUrl, "/api/feeds/sources/error", {
        method: "POST",
        body: JSON.stringify({ source_url: sourceUrl, site_title: siteTitle, error_message: errorMessage })
      }),
    refreshFeeds: () =>
      request<ApiFeedRefreshResponse>(baseUrl, "/api/feeds/refresh", {
        method: "POST"
      }),
    getDailyNews: (date?: string | null) => {
      const params = new URLSearchParams();
      if (date) params.set("date", date);
      const suffix = params.toString() ? "?" + params.toString() : "";
      return request<ApiDailyNewsReportResponse>(baseUrl, "/api/daily-news" + suffix);
    },
    generateDailyNews: (date: string, force = false) =>
      request<ApiDailyNewsReportResponse>(baseUrl, "/api/daily-news/generate", {
        method: "POST",
        body: JSON.stringify({ date, force })
      }),
    deleteFeedSource: (url: string) => {
      const params = new URLSearchParams({ url });
      return request<{ source_url: string; deleted: boolean }>(baseUrl, "/api/feeds/sources?" + params.toString(), {
        method: "DELETE"
      });
    },
    getFeedArticlePreview: (query: {
      url: string;
      title?: string | null;
      sourceTitle?: string | null;
      author?: string | null;
      publishedAt?: string | null;
      summary?: string | null;
    }) => {
      const params = new URLSearchParams({ url: query.url });
      if (query.title) params.set("title", query.title);
      if (query.sourceTitle) params.set("source_title", query.sourceTitle);
      if (query.author) params.set("author", query.author);
      if (query.publishedAt) params.set("published_at", query.publishedAt);
      if (query.summary) params.set("summary", query.summary);
      return request<ApiFeedArticlePreviewResponse>(baseUrl, "/api/feeds/article-preview?" + params.toString());
    },
    searchPodcasts: (query: string, country = "US", limit = 12) => {
      const params = new URLSearchParams({ q: query, country, limit: String(limit) });
      return request<{ items: ApiPodcastSearchItem[] }>(baseUrl, "/api/podcasts/search?" + params.toString());
    },
    listPodcastSubscriptions: () =>
      request<{ items: ApiPodcastSubscription[] }>(baseUrl, "/api/podcasts/subscriptions"),
    createPodcastSubscription: (payload: {
      feed_url: string;
      title: string;
      author?: string | null;
      image_url?: string | null;
      itunes_id?: string | null;
      page_url?: string | null;
    }) =>
      request<ApiPodcastSubscription>(baseUrl, "/api/podcasts/subscriptions", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    deletePodcastSubscription: (subscriptionId: string) =>
      request<{ id: string; deleted: boolean }>(baseUrl, "/api/podcasts/subscriptions/" + subscriptionId, {
        method: "DELETE"
      }),
    listPodcastEpisodes: (limit = 80) =>
      request<{ items: ApiPodcastEpisode[] }>(baseUrl, "/api/podcasts/episodes?limit=" + String(limit)),
    listPodcastFeedEpisodes: (query: {
      feedUrl: string;
      title?: string | null;
      author?: string | null;
      imageUrl?: string | null;
      limit?: number;
    }) => {
      const params = new URLSearchParams({
        feed_url: query.feedUrl,
        limit: String(query.limit ?? 120)
      });
      if (query.title) params.set("title", query.title);
      if (query.author) params.set("author", query.author);
      if (query.imageUrl) params.set("image_url", query.imageUrl);
      return request<{ items: ApiPodcastEpisode[] }>(baseUrl, "/api/podcasts/feed-episodes?" + params.toString());
    },
    importPodcastEpisode: (episode: ApiPodcastEpisode) =>
      request<ApiImportResponse>(baseUrl, "/api/podcasts/episodes/import", {
        method: "POST",
        body: JSON.stringify({
          feed_url: episode.feed_url,
          podcast_title: episode.podcast_title,
          title: episode.title,
          guid: episode.guid,
          link: episode.link,
          summary: episode.summary,
          author: episode.author,
          published_at: episode.published_at,
          duration_seconds: episode.duration_seconds,
          enclosure_url: episode.enclosure_url,
          enclosure_type: episode.enclosure_type,
          enclosure_length: episode.enclosure_length,
          image_url: episode.image_url
        })
      }),
    listItems: (query?: {
      keyword?: string;
      folderId?: string;
      inboxOnly?: boolean;
      tag?: string;
      collectionId?: string;
      page?: number;
      pageSize?: number;
    }) => {
      const params = new URLSearchParams();
      if (query?.keyword) {
        params.set("keyword", query.keyword);
      }
      if (query?.folderId) {
        params.set("folder_id", query.folderId);
      }
      if (query?.tag) {
        params.set("tag", query.tag);
      }
      if (query?.collectionId) {
        params.set("collection_id", query.collectionId);
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
    listDeletedItems: (pageSize = 100) =>
      request<ApiListResponse<ApiItemSummary>>(baseUrl, "/api/items/trash?page_size=" + String(pageSize)),
    restoreItem: (itemId: string) =>
      request<{ id?: string; uid: string; deleted: boolean }>(baseUrl, "/api/items/trash/" + itemId + "/restore", {
        method: "POST"
      }),
    purgeItem: (itemId: string) =>
      request<{ id?: string; uid: string; deleted: boolean }>(baseUrl, "/api/items/trash/" + itemId + "/purge", {
        method: "DELETE"
      }),
    deleteItem: (itemId: string) =>
      request<{ id?: string; uid: string; deleted: boolean }>(baseUrl, "/api/items/" + itemId, {
        method: "DELETE"
      }),
    generateItemSummary: (itemId: string) =>
      request<ApiItemTaskResponse>(baseUrl, "/api/items/" + itemId + "/summaries/generate", {
        method: "POST"
      }),
    listTasks: (pageSize = 100) =>
      request<ApiListResponse<ApiTaskEntry>>(baseUrl, "/api/tasks?page_size=" + String(pageSize)),
    setItemTags: (itemId: string, tags: string[]) =>
      request<{ items: ApiTag[] }>(baseUrl, "/api/items/" + itemId + "/tags", {
        method: "POST",
        body: JSON.stringify({ tags })
      }),
    listCollections: () => request<{ items: ApiCollection[] }>(baseUrl, "/api/collections"),
    createCollection: (payload: { name: string; description?: string | null }) =>
      request<ApiCollection>(baseUrl, "/api/collections", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    addItemToCollection: (collectionId: string, itemId: string) =>
      request<ApiCollection>(baseUrl, "/api/collections/" + collectionId + "/items", {
        method: "POST",
        body: JSON.stringify({ item_id: itemId })
      }),
    removeItemFromCollection: (collectionId: string, itemId: string) =>
      request<ApiCollection>(baseUrl, "/api/collections/" + collectionId + "/items/" + itemId, {
        method: "DELETE"
      }),
    createHighlight: (itemId: string, payload: {
      quote_text: string;
      anchor_type?: string;
      start_anchor?: string | null;
      end_anchor?: string | null;
      start_offset?: number | null;
      end_offset?: number | null;
      segment_index?: number | null;
      color?: string | null;
    }) =>
      request<ApiHighlight>(baseUrl, "/api/items/" + itemId + "/highlights", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    deleteHighlight: (highlightId: string) =>
      request<{ id: string; deleted: boolean }>(baseUrl, "/api/highlights/" + highlightId, {
        method: "DELETE"
      }),
    createNote: (itemId: string, payload: { content: string; highlight_id?: string | null }) =>
      request<ApiNote>(baseUrl, "/api/items/" + itemId + "/notes", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    updateNote: (noteId: string, content: string) =>
      request<ApiNote>(baseUrl, "/api/notes/" + noteId, {
        method: "PUT",
        body: JSON.stringify({ content })
      }),
    deleteNote: (noteId: string) =>
      request<{ id: string; deleted: boolean }>(baseUrl, "/api/notes/" + noteId, {
        method: "DELETE"
      }),
    updateReadingState: (itemId: string, payload: ApiReadingStateUpdatePayload) =>
      request<ApiReadingState>(baseUrl, "/api/items/" + itemId + "/reading-state", {
        method: "PUT",
        body: JSON.stringify(payload)
      }),

    getBilibiliIntegration: () => request<ApiBilibiliIntegrationSettings>(baseUrl, "/api/settings/integrations/bilibili"),
    updateBilibiliIntegration: (payload: {
      is_enabled: boolean;
      visual_enhancement_enabled?: boolean;
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
    createBilibiliQrcode: () =>
      request<ApiBilibiliQrcodeGenerateResponse>(baseUrl, "/api/settings/integrations/bilibili/qrcode", {
        method: "POST"
      }),
    pollBilibiliQrcode: (qrcodeKey: string) =>
      request<ApiBilibiliQrcodePollResponse>(baseUrl, "/api/settings/integrations/bilibili/qrcode/poll", {
        method: "POST",
        body: JSON.stringify({ qrcode_key: qrcodeKey })
      }),
    previewBilibiliVideo: (url: string) =>
      request<ApiBilibiliPreviewResponse>(baseUrl, "/api/items/bilibili/preview", {
        method: "POST",
        body: JSON.stringify({ url })
      }),
    importItem: (url: string, sourceHint?: string, options?: {
      title?: string | null;
      siteTitle?: string | null;
      author?: string | null;
      publishedAt?: string | null;
      summary?: string | null;
      parsedText?: string | null;
      parserName?: string | null;
      parserVersion?: string | null;
      generateSummary?: boolean;
      allowDuplicate?: boolean;
    }) =>
      request<ApiImportResponse>(baseUrl, "/api/items/import", {
        method: "POST",
        body: JSON.stringify({
          url,
          ...(sourceHint ? { source_hint: sourceHint } : {}),
          ...(options?.title ? { title: options.title } : {}),
          ...(options?.siteTitle ? { site_title: options.siteTitle } : {}),
          ...(options?.author ? { author: options.author } : {}),
          ...(options?.publishedAt ? { published_at: options.publishedAt } : {}),
          ...(options?.summary ? { summary: options.summary } : {}),
          ...(options?.parsedText ? { parsed_text: options.parsedText } : {}),
          ...(options?.parserName ? { parser_name: options.parserName } : {}),
          ...(options?.parserVersion ? { parser_version: options.parserVersion } : {}),
          ...(options?.generateSummary ? { generate_summary: true } : {}),
          ...(options?.allowDuplicate ? { allow_duplicate: true } : {})
        })
      }),
    moveItem: (itemId: string, folderId: string) =>
      request<ApiMoveItemResponse>(baseUrl, "/api/items/" + itemId + "/move", {
        method: "POST",
        body: JSON.stringify({ folder_id: folderId })
      })
  };
}

