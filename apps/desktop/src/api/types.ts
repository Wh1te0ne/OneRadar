export type ApiFeedPreviewItem = {
  id: string;
  title: string;
  link: string;
  summary?: string | null;
  author?: string | null;
  published_at?: string | null;
  tags: string[];
  is_saved?: boolean;
  saved_item_id?: string | null;
  saved_uid?: string | null;
};

export type ApiFeedPreviewResponse = {
  source_url: string;
  site_title: string;
  site_url?: string | null;
  description?: string | null;
  items: ApiFeedPreviewItem[];
  fetched_at: string;
};

export type ApiFeedArticlePreviewResponse = {
  source_url: string;
  final_url?: string | null;
  title: string;
  site_title?: string | null;
  author?: string | null;
  published_at?: string | null;
  summary?: string | null;
  plain_text: string;
  parser_name: string;
  parser_version: string;
  fetched_at: string;
  is_saved: boolean;
  saved_item_id?: string | null;
  saved_uid?: string | null;
  can_generate_ai: boolean;
};

export type ApiFeedSourceEntry = {
  source_url: string;
  site_title: string;
  site_url?: string | null;
  description?: string | null;
  last_loaded_at: string;
  last_refresh_status?: string | null;
  last_refresh_error?: string | null;
  last_refreshed_at?: string | null;
};

export type ApiFeedStateResponse = {
  sources: ApiFeedSourceEntry[];
  feeds: Record<string, ApiFeedPreviewResponse>;
  read_entries: string[];
};

export type ApiFeedRefreshResponse = {
  total: number;
  refreshed: number;
  failed: number;
  errors: Record<string, string>;
};

export type ApiDailyNewsEntry = {
  id: string;
  title: string;
  link: string;
  summary?: string | null;
  author?: string | null;
  published_at?: string | null;
  source_url: string;
  source_title: string;
};

export type ApiDailyNewsItem = {
  title: string;
  summary: string;
  entry_id?: string | null;
  entry?: ApiDailyNewsEntry | null;
};

export type ApiDailyNewsSection = {
  title: string;
  summary: string;
  items: ApiDailyNewsItem[];
};

export type ApiDailyNewsReportResponse = {
  report_date: string;
  status: "missing" | "ready" | "failed" | string;
  headline?: string | null;
  lead?: ApiDailyNewsItem | null;
  sections: ApiDailyNewsSection[];
  generated_at?: string | null;
  provider_name?: string | null;
  model_name?: string | null;
  entry_count: number;
  freshness_hours: number;
  error_message?: string | null;
};

export type ApiHealth = {
  status: "ok" | "degraded" | "down";
  version: string;
  time: string;
};

export type ApiBootstrapThemeMode = "system" | "light" | "dark";

export type ApiUser = {
  id: string;
  username: string;
  created_at?: string;
};

export type ApiFolderEntry = {
  id: string;
  name: string;
  is_builtin: boolean;
  item_count: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ApiBootstrapResponse = {
  workspace_name: string;
  single_user_mode: boolean;
  ui_locale: string;
  theme_mode: ApiBootstrapThemeMode;
  supported_theme_modes: ApiBootstrapThemeMode[];
  default_inbox_folder: ApiFolderEntry;
  primary_user: ApiUser;
  requires_login: boolean;
  capabilities: string[];
};

export type ApiProvider = {
  id: string;
  provider_name: string;
  provider_type: string;
  capability?: "llm" | "asr";
  base_url?: string | null;
  api_key_configured?: boolean;
  chat_model?: string | null;
  embedding_model?: string | null;
  transcription_model?: string | null;
  transcription_app_id?: string | null;
  transcription_access_token_configured?: boolean;
  transcription_secret_key_configured?: boolean;
  thinking_mode?: "default" | "enabled" | "disabled";
  is_enabled: boolean;
  last_test_status?: string | null;
  last_tested_at?: string | null;
};

export type ApiProviderPayload = {
  provider_name: string;
  provider_type: "openai_compatible" | "doubao" | "deepseek" | "custom";
  capability?: "llm" | "asr";
  base_url?: string | null;
  api_key?: string | null;
  chat_model?: string | null;
  embedding_model?: string | null;
  transcription_model?: string | null;
  transcription_app_id?: string | null;
  transcription_access_token?: string | null;
  transcription_secret_key?: string | null;
  thinking_mode?: "default" | "enabled" | "disabled" | null;
  is_enabled: boolean;
};

export type ApiProviderTestResponse = {
  provider_id: string;
  ok: boolean;
  latency_ms: number;
  message?: string | null;
};

export type ApiReadingState = {
  progress_percent: number;
  is_read?: boolean;
  last_read_at?: string | null;
  is_archived: boolean;
  is_favorited: boolean;
};

export type ApiReadingStateUpdatePayload = {
  progress_percent?: number;
  is_read?: boolean;
  last_read_at?: string | null;
  is_archived?: boolean;
  is_favorited?: boolean;
  last_position_type?: string;
  last_position_value?: string;
};

export type ApiItemSummary = {
  uid: string;
  id: string;
  title: string;
  content_type: "article" | "bilibili_video" | "podcast_episode";
  source_url: string;
  status: "pending" | "processing" | "completed" | "failed";
  folder_id: string;
  folder_name: string;
  is_inbox: boolean;
  is_read: boolean;
  is_favorited: boolean;
  progress_percent: number;
  last_read_at?: string | null;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
  delete_expires_at?: string | null;
  summary?: string;
  tags?: string[];
};

export type ApiTag = {
  id: string;
  name: string;
};

export type ApiCollection = {
  id: string;
  name: string;
  description?: string | null;
  is_favorite: boolean;
  item_count: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ApiSummary = {
  summary_type: "one_line" | "short" | "outline" | "key_points" | "visual_context";
  content: string;
  model_name?: string | null;
  version?: number;
};

export type ApiTranscriptSegment = {
  start_ms: number;
  end_ms: number;
  speaker?: string | null;
  text: string;
};

export type ApiTranscript = {
  id?: string;
  transcript_type: "subtitle" | "asr" | "refined_asr";
  language?: string | null;
  full_text: string;
  segments: ApiTranscriptSegment[];
  provider_name?: string | null;
  model_name?: string | null;
};

export type ApiHighlight = {
  id: string;
  item_id: string;
  quote_text: string;
  anchor_type: "article_text" | "transcript_segment" | string;
  start_anchor?: string | null;
  end_anchor?: string | null;
  start_offset?: number | null;
  end_offset?: number | null;
  segment_index?: number | null;
  color?: string | null;
  note_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ApiNote = {
  id: string;
  item_id: string;
  content: string;
  highlight_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ApiItemDetail = {
  uid: string;
  id: string;
  title: string;
  content_type: "article" | "bilibili_video" | "podcast_episode";
  source_url: string;
  status: "pending" | "processing" | "completed" | "failed";
  folder_id: string;
  folder_name: string;
  is_inbox: boolean;
  metadata: {
    author_name?: string | null;
    published_at?: string | null;
    site_name?: string | null;
    podcast?: {
      feed_url?: string | null;
      podcast_title?: string | null;
      episode_link?: string | null;
      enclosure_url?: string | null;
      enclosure_type?: string | null;
      audio_storage_path?: string | null;
    };
  };
  parsed_document: {
    plain_text: string;
    structured_blocks: Array<{ type: string; text?: string; order?: number; data?: { level?: number; [key: string]: unknown } }>;
    parser_name?: string | null;
    parser_version?: string | null;
  } | null;
  transcript?: ApiTranscript | null;
  summaries: ApiSummary[];
  highlights: ApiHighlight[];
  notes: ApiNote[];
  tags: ApiTag[];
  collections: ApiCollection[];
  reading_state: ApiReadingState;
};

export type ApiSecretStatus = {
  configured: boolean;
  preview?: string | null;
};

export type ApiBilibiliIntegrationSettings = {
  integration_key: string;
  display_name: string;
  is_enabled: boolean;
  visual_enhancement_enabled: boolean;
  has_cookie_values: boolean;
  ready_for_authenticated_fetch: boolean;
  sessdata_configured: boolean;
  sessdata_preview?: string | null;
  bili_jct_configured: boolean;
  bili_jct_preview?: string | null;
  buvid3_configured: boolean;
  buvid3_preview?: string | null;
  updated_at?: string | null;
};

export type ApiBilibiliCookieParseResponse = {
  extracted: {
    sessdata: ApiSecretStatus;
    bili_jct: ApiSecretStatus;
    buvid3: ApiSecretStatus;
  };
  extracted_count: number;
};

export type ApiBilibiliQrcodeGenerateResponse = {
  url: string;
  qrcode_key: string;
  expires_in_seconds: number;
};

export type ApiBilibiliQrcodePollResponse = {
  code: number;
  state: "waiting" | "scanned" | "confirmed" | "expired" | "failed";
  message: string;
  saved_cookie?: ApiBilibiliIntegrationSettings | null;
};

export type ApiBilibiliPreviewResponse = {
  content_type: "bilibili_video";
  source_url: string;
  normalized_url: string;
  title: string;
  owner_name?: string | null;
  owner_id?: number | null;
  cover_url?: string | null;
  description?: string | null;
  duration_seconds?: number | null;
  duration_text?: string | null;
  published_at?: string | null;
  bvid?: string | null;
  aid?: number | null;
  cid?: number | null;
  page_count?: number | null;
  page_title?: string | null;
  subtitle_status: string;
};

export type ApiImportResponse = {
  uid: string;
  item_id: string;
  existing_uid?: string | null;
  task_id?: string | null;
  status: string;
  content_type: "article" | "bilibili_video" | "podcast_episode";
  folder_id: string;
  folder_name: string;
  is_duplicate: boolean;
};

export type ApiMoveItemResponse = {
  uid: string;
  folder_id: string;
  folder_name: string;
  is_inbox: boolean;
};

export type ApiItemTaskResponse = {
  item_id: string;
  task_id: string;
  status: string;
};

export type ApiTaskEntry = {
  id: string;
  item_id: string;
  task_type: string;
  status: "pending" | "running" | "retrying" | "success" | "failed" | "canceled";
  attempt_count: number;
  error_message?: string | null;
  stage_label?: string | null;
  stage_detail?: string | null;
  progress_percent?: number | null;
  created_at: string;
};

export type ApiCreateFolderResponse = ApiFolderEntry;

export type ApiListResponse<T> = {
  items: T[];
  page?: number;
  page_size?: number;
  total?: number;
};

export type ApiPodcastSearchItem = {
  itunes_id?: string | null;
  title: string;
  author?: string | null;
  feed_url?: string | null;
  page_url?: string | null;
  image_url?: string | null;
  genre?: string | null;
  episode_count?: number | null;
  is_subscribable: boolean;
};

export type ApiPodcastSubscription = {
  id: string;
  feed_url: string;
  title: string;
  author?: string | null;
  image_url?: string | null;
  itunes_id?: string | null;
  page_url?: string | null;
  created_at: string;
  updated_at: string;
};

export type ApiPodcastEpisode = {
  id: string;
  subscription_id?: string | null;
  feed_url: string;
  podcast_title: string;
  title: string;
  guid?: string | null;
  link?: string | null;
  summary?: string | null;
  author?: string | null;
  published_at?: string | null;
  duration_seconds?: number | null;
  enclosure_url: string;
  enclosure_type?: string | null;
  enclosure_length?: number | null;
  image_url?: string | null;
  is_imported: boolean;
  item_id?: string | null;
};

