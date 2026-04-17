export type ApiFeedPreviewItem = {
  id: string;
  title: string;
  link: string;
  summary?: string | null;
  author?: string | null;
  published_at?: string | null;
  tags: string[];
};

export type ApiFeedPreviewResponse = {
  source_url: string;
  site_title: string;
  site_url?: string | null;
  description?: string | null;
  items: ApiFeedPreviewItem[];
  fetched_at: string;
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
  base_url?: string | null;
  chat_model?: string | null;
  embedding_model?: string | null;
  transcription_model?: string | null;
  is_enabled: boolean;
  last_test_status?: string | null;
  last_tested_at?: string | null;
};

export type ApiItemSummary = {
  uid: string;
  id: string;
  title: string;
  content_type: "article" | "bilibili_video";
  source_url: string;
  status: "pending" | "processing" | "completed" | "failed";
  folder_id: string;
  folder_name: string;
  is_inbox: boolean;
  is_read: boolean;
  is_favorited: boolean;
  created_at: string;
  updated_at: string;
  summary?: string;
  tags?: string[];
};

export type ApiSummary = {
  summary_type: "one_line" | "short" | "outline" | "key_points";
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

export type ApiItemDetail = {
  uid: string;
  id: string;
  title: string;
  content_type: "article" | "bilibili_video";
  source_url: string;
  status: "pending" | "processing" | "completed" | "failed";
  folder_id: string;
  folder_name: string;
  is_inbox: boolean;
  metadata: {
    author_name?: string | null;
    published_at?: string | null;
    site_name?: string | null;
  };
  parsed_document: {
    plain_text: string;
    structured_blocks: Array<{ type: string; text?: string }>;
    parser_name?: string | null;
    parser_version?: string | null;
  } | null;
  transcript?: ApiTranscript | null;
  summaries: ApiSummary[];
  highlights: Array<{ id: string; quote_text?: string; text?: string; color?: string | null; note_id?: string | null }>;
  notes: Array<{ id: string; content?: string; text?: string; highlight_id?: string | null }>;
  tags: Array<{ name: string } | string>;
  collections: Array<{ id: string; name: string }>;
  reading_state: {
    progress_percent: number;
    last_read_at?: string | null;
    is_archived: boolean;
    is_favorited: boolean;
  };
};


export type ApiSecretStatus = {
  configured: boolean;
  preview?: string | null;
};

export type ApiBilibiliIntegrationSettings = {
  integration_key: string;
  display_name: string;
  is_enabled: boolean;
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

export type ApiImportResponse = {
  uid: string;
  item_id: string;
  existing_uid?: string | null;
  task_id?: string | null;
  status: string;
  content_type: "article" | "bilibili_video";
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

export type ApiCreateFolderResponse = ApiFolderEntry;

export type ApiListResponse<T> = {
  items: T[];
  page?: number;
  page_size?: number;
  total?: number;
};


