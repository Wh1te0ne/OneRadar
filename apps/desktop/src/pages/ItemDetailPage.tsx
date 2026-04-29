import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ApiError, createApiClient } from "../api";
import type { ApiHighlight, ApiItemDetail, ApiReadingState, ApiTaskEntry, ApiTranscriptSegment } from "../api";
import { useAppState } from "../state/appState";
import { displayFolderName } from "../utils/display";

function statusLabel(status?: ApiItemDetail["status"]) {
  switch (status) {
    case "processing": return "处理中";
    case "completed": return "已完成";
    case "failed": return "失败";
    default: return "待处理";
  }
}

function statusChipClass(status?: ApiItemDetail["status"]) {
  switch (status) {
    case "processing": return "chip chip-status-processing";
    case "completed": return "chip chip-status-completed";
    case "failed": return "chip chip-status-failed";
    default: return "chip chip-status-pending";
  }
}

function taskTypeLabel(taskType: string, contentType?: ApiItemDetail["content_type"]) {
  switch (taskType) {
    case "fetch_meta":
      if (contentType === "podcast_episode") return "正在下载音频并准备解析";
      if (contentType === "bilibili_video") return "正在获取视频信息和字幕";
      return "正在抓取和解析内容";
    case "generate_summary": return "正在生成 AI 摘要";
    case "reprocess_item": return "正在重新处理条目";
    case "transcribe_audio": return "正在转写音频";
    default: return "正在处理";
  }
}

function taskStatusLabel(status: ApiTaskEntry["status"]) {
  switch (status) {
    case "pending": return "排队中";
    case "running": return "处理中";
    case "retrying": return "重试中";
    case "success": return "已完成";
    case "failed": return "失败";
    case "canceled": return "已取消";
    default: return status;
  }
}

function taskIsActive(task: ApiTaskEntry) {
  return task.status === "pending" || task.status === "running" || task.status === "retrying";
}

function formatTranscriptTime(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function splitParagraphs(value?: string | null) {
  return value ? value.split(/\n+/).filter(Boolean) : [];
}

function formatReadingTime(value?: string | null) {
  if (!value) return "暂无";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDisplayDate(value?: string | null) {
  if (!value) return "未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function clampProgress(progress: number) {
  if (!Number.isFinite(progress)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(progress)));
}

function readingStatusLabel(progress: number) {
  if (progress >= 100) return "已读";
  if (progress > 0) return "阅读中";
  return "未读";
}

function getReaderScrollHost() {
  return document.querySelector<HTMLElement>(".workspace-frame");
}

type ReaderSelectionPopover = {
  quoteText: string;
  x: number;
  y: number;
};

type ReaderNotePopover = {
  quoteText: string | null;
  highlightId: string | null;
  noteId?: string | null;
  mode: "view" | "edit";
  x: number;
  y: number;
};

type HighlightActionPopover = {
  highlight: ApiHighlight;
  x: number;
  y: number;
};

type ReaderContentTab = "source" | "ai";

function appendRenderedNode(nodes: ReactNode[], value: ReactNode | ReactNode[]) {
  if (Array.isArray(value)) {
    nodes.push(...value);
    return;
  }
  nodes.push(value);
}

function renderInlineMarkdown(text: string, renderText: (value: string) => ReactNode | ReactNode[] = (value) => value): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      appendRenderedNode(nodes, renderText(text.slice(cursor, match.index)));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`${match.index}-strong`}>{renderText(token.slice(2, -2))}</strong>);
    } else {
      nodes.push(<code key={`${match.index}-code`}>{token.slice(1, -1)}</code>);
    }
    cursor = match.index + token.length;
  }

  if (cursor < text.length) {
    appendRenderedNode(nodes, renderText(text.slice(cursor)));
  }
  return nodes;
}

function renderMarkdown(content: string, renderInline: (value: string) => ReactNode[] = renderInlineMarkdown) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const nodes: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    const heading = /^(#{2,4})\s+(.+)$/.exec(line);
    if (heading) {
      const text = heading[2].trim();
      nodes.push(<p key={index} className="markdown-section-label">{renderInline(text)}</p>);
      index += 1;
      continue;
    }

    const boldSection = /^\*\*([^*]+)\*\*$/.exec(line);
    if (boldSection) {
      nodes.push(<p key={index} className="markdown-section-label">{renderInline(boldSection[1].trim())}</p>);
      index += 1;
      continue;
    }

    if (/^\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+[.)]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+[.)]\s+/, ""));
        index += 1;
      }
      nodes.push(
        <ol key={`ol-${index}`}>
          {items.map((item, itemIndex) => <li key={itemIndex}><span>{renderInline(item)}</span></li>)}
        </ol>,
      );
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      nodes.push(
        <ul key={`ul-${index}`}>
          {items.map((item, itemIndex) => <li key={itemIndex}><span>{renderInline(item)}</span></li>)}
        </ul>,
      );
      continue;
    }

    const paragraph: string[] = [];
    while (
      index < lines.length
      && lines[index].trim()
      && !/^(#{2,4})\s+/.test(lines[index].trim())
      && !/^\d+[.)]\s+/.test(lines[index].trim())
      && !/^[-*]\s+/.test(lines[index].trim())
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    nodes.push(<p key={`p-${index}`}>{renderInline(paragraph.join(" "))}</p>);
  }

  return nodes;
}

function splitPodcastDescription(value?: string | null) {
  const normalized = (value ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (!normalized) return [];

  const explicitParagraphs = normalized.split(/\n{2,}/).map((entry) => entry.trim()).filter(Boolean);
  if (explicitParagraphs.length > 1) return explicitParagraphs;
  if (normalized.length <= 180) return [normalized];

  return normalized
    .replace(/\s*(BGM[:：])/i, "\n$1")
    .replace(/([。！？!?])\s*/g, "$1\n")
    .split(/\n+/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function ItemDetailPage() {
  const { itemId = "" } = useParams();
  const location = useLocation();
  const { apiBaseUrl, folders, loadFolders, workspace } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [item, setItem] = useState<ApiItemDetail | null>(null);
  const [liveReadingState, setLiveReadingState] = useState<ApiReadingState | null>(null);
  const [activeTranscriptStartMs, setActiveTranscriptStartMs] = useState<number | null>(null);
  const [annotationMessage, setAnnotationMessage] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [noteTargetHighlightId, setNoteTargetHighlightId] = useState<string | null>(null);
  const [selectionPopover, setSelectionPopover] = useState<ReaderSelectionPopover | null>(null);
  const [notePopover, setNotePopover] = useState<ReaderNotePopover | null>(null);
  const [highlightActionPopover, setHighlightActionPopover] = useState<HighlightActionPopover | null>(null);
  const [readerContentTab, setReaderContentTab] = useState<ReaderContentTab>("ai");
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [summaryMessage, setSummaryMessage] = useState<string | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [itemTasks, setItemTasks] = useState<ApiTaskEntry[]>([]);
  const [taskPollError, setTaskPollError] = useState<string | null>(null);
  const [podcastTranscriptExpanded, setPodcastTranscriptExpanded] = useState(false);
  const [savingAnnotation, setSavingAnnotation] = useState(false);
  const [tagDraft, setTagDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const saveTimerRef = useRef<number | null>(null);
  const restoreTimerRef = useRef<number | null>(null);
  const jumpTimerRef = useRef<number | null>(null);
  const podcastAudioRef = useRef<HTMLAudioElement | null>(null);
  const latestItemIdRef = useRef(itemId);
  const lastQueuedProgressRef = useRef<number | null>(null);
  const readingStateRef = useRef<ApiReadingState | null>(null);
  const restoredKeyRef = useRef<string | null>(null);
  const transcriptSegmentRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    latestItemIdRef.current = itemId;
  }, [itemId]);

  useEffect(() => {
    readingStateRef.current = liveReadingState;
  }, [liveReadingState]);

  useEffect(() => {
    return () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
      }
      if (restoreTimerRef.current !== null) {
        window.clearTimeout(restoreTimerRef.current);
      }
      if (jumpTimerRef.current !== null) {
        window.clearTimeout(jumpTimerRef.current);
      }
    };
  }, []);

  function syncReadingState(
    payload: {
      progress_percent?: number;
      last_read_at?: string | null;
      is_archived?: boolean;
      is_favorited?: boolean;
      last_position_type?: string;
      last_position_value?: string;
    },
    immediate = false,
  ) {
    if (!item) {
      return;
    }

    const currentState = readingStateRef.current ?? liveReadingState ?? item.reading_state;
    const nextProgress = clampProgress(payload.progress_percent ?? currentState.progress_percent);
    const nextLastReadAt = payload.last_read_at ?? new Date().toISOString();
    const nextState: ApiReadingState = {
      progress_percent: nextProgress,
      last_read_at: nextLastReadAt,
      is_archived: payload.is_archived ?? currentState.is_archived,
      is_favorited: payload.is_favorited ?? currentState.is_favorited,
    };

    readingStateRef.current = nextState;
    setLiveReadingState(nextState);
    lastQueuedProgressRef.current = nextProgress;

    const requestPayload = {
      progress_percent: nextProgress,
      last_read_at: nextLastReadAt,
      is_archived: payload.is_archived,
      is_favorited: payload.is_favorited,
      last_position_type: payload.last_position_type,
      last_position_value: payload.last_position_value,
    };

    const submit = () => {
      void client.updateReadingState(item.id, requestPayload).then((savedState) => {
        if (latestItemIdRef.current !== item.id) {
          return;
        }
        readingStateRef.current = savedState;
        setLiveReadingState(savedState);
      }).catch(() => {
        // Keep optimistic state; the next jump, scroll, or refresh can retry.
      });
    };

    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }

    if (immediate) {
      submit();
      return;
    }

    saveTimerRef.current = window.setTimeout(submit, 700);
  }

  function jumpToTranscriptSegment(segment: ApiTranscriptSegment) {
    if (isPodcast && podcastAudioRef.current) {
      podcastAudioRef.current.currentTime = Math.max(0, segment.start_ms / 1000);
      void podcastAudioRef.current.play().catch(() => {
        // Browsers may block autoplay; seeking still keeps the player at the right position.
      });
    }

    const scrollHost = getReaderScrollHost();
    const targetRow = transcriptSegmentRefs.current[String(segment.start_ms)];
    if (!scrollHost || !targetRow) {
      return;
    }

    setActiveTranscriptStartMs(segment.start_ms);
    targetRow.scrollIntoView({ behavior: "smooth", block: "center" });

    if (jumpTimerRef.current !== null) {
      window.clearTimeout(jumpTimerRef.current);
    }

    jumpTimerRef.current = window.setTimeout(() => {
      const maxScroll = scrollHost.scrollHeight - scrollHost.clientHeight;
      const nextProgress = maxScroll <= 0 ? 0 : clampProgress((scrollHost.scrollTop / maxScroll) * 100);
      syncReadingState(
        {
          progress_percent: nextProgress,
          last_read_at: new Date().toISOString(),
          last_position_type: "transcript_ms",
          last_position_value: String(segment.start_ms),
        },
        true,
      );
    }, 260);
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!itemId) {
        setItem(null);
        setLiveReadingState(null);
        setActiveTranscriptStartMs(null);
        readingStateRef.current = null;
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const response = await client.getItem(itemId);
        if (!cancelled) {
          setItem(response);
          setLiveReadingState(response.reading_state);
          setActiveTranscriptStartMs(null);
          setAnnotationMessage(null);
          setNoteDraft("");
          setNoteTargetHighlightId(null);
          setSelectionPopover(null);
          setNotePopover(null);
          setHighlightActionPopover(null);
          setReaderContentTab("ai");
          setSummaryMessage(null);
          setSummaryError(null);
          setTagDraft(response.tags.map((tag) => tag.name).join(", "));
          readingStateRef.current = response.reading_state;
          lastQueuedProgressRef.current = Math.round(response.reading_state.progress_percent);
          restoredKeyRef.current = null;
        }
      } catch (nextError) {
        if (!cancelled) {
          setItem(null);
          setLiveReadingState(null);
          setActiveTranscriptStartMs(null);
          readingStateRef.current = null;
          setError(nextError instanceof Error ? nextError.message : "读取条目失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [client, itemId]);

  useEffect(() => {
    if (!itemId) {
      setItemTasks([]);
      return;
    }

    let cancelled = false;
    let sawActiveTask = false;

    async function loadTasks() {
      try {
        const response = await client.listTasks(100);
        if (cancelled) return;
        const nextTasks = response.items
          .filter((task) => task.item_id === itemId)
          .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        const hasActiveTask = nextTasks.some(taskIsActive);
        setItemTasks(nextTasks);
        setTaskPollError(null);
        if (sawActiveTask && !hasActiveTask) {
          const refreshed = await client.getItem(itemId);
          if (!cancelled && latestItemIdRef.current === itemId) {
            setItem(refreshed);
            setLiveReadingState(refreshed.reading_state);
          }
        }
        sawActiveTask = hasActiveTask;
      } catch (error) {
        if (!cancelled) {
          setTaskPollError(error instanceof Error ? error.message : "读取处理状态失败");
        }
      }
    }

    void loadTasks();
    const interval = window.setInterval(() => {
      void loadTasks();
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [client, itemId]);

  useEffect(() => {
    if (!item) {
      return;
    }

    const restoreProgress = clampProgress((readingStateRef.current ?? item.reading_state).progress_percent);
    const restoreKey = `${item.id}:${restoreProgress}`;
    if (restoredKeyRef.current === restoreKey) {
      return;
    }
    restoredKeyRef.current = restoreKey;

    if (restoreTimerRef.current !== null) {
      window.clearTimeout(restoreTimerRef.current);
    }

    restoreTimerRef.current = window.setTimeout(() => {
      const scrollHost = getReaderScrollHost();
      if (!scrollHost) {
        return;
      }

      const maxScroll = scrollHost.scrollHeight - scrollHost.clientHeight;
      if (maxScroll <= 0) {
        scrollHost.scrollTo({ top: 0, behavior: "auto" });
        return;
      }

      const targetTop = restoreProgress <= 0 ? 0 : (maxScroll * restoreProgress) / 100;
      scrollHost.scrollTo({ top: targetTop, behavior: "auto" });
    }, 80);

    return () => {
      if (restoreTimerRef.current !== null) {
        window.clearTimeout(restoreTimerRef.current);
        restoreTimerRef.current = null;
      }
    };
  }, [item]);

  useEffect(() => {
    if (!item) {
      return;
    }

    const scrollHost = getReaderScrollHost();
    if (!scrollHost) {
      return;
    }

    function handleScroll() {
      const currentState = readingStateRef.current ?? item.reading_state;
      const maxScroll = scrollHost.scrollHeight - scrollHost.clientHeight;
      if (maxScroll <= 0) {
        return;
      }

      const nextProgress = clampProgress((scrollHost.scrollTop / maxScroll) * 100);
      if (lastQueuedProgressRef.current === nextProgress) {
        return;
      }

      syncReadingState(
        {
          progress_percent: nextProgress,
          last_read_at: new Date().toISOString(),
          is_archived: currentState.is_archived,
          is_favorited: currentState.is_favorited,
          last_position_type: "scroll_percent",
          last_position_value: String(nextProgress),
        },
        false,
      );
    }

    scrollHost.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      scrollHost.removeEventListener("scroll", handleScroll);
    };
  }, [item]);

  useEffect(() => {
    if (!item) {
      return;
    }

    function handleSelectionChange() {
      const activeElement = document.activeElement;
      if (activeElement instanceof HTMLTextAreaElement || activeElement instanceof HTMLInputElement) {
        return;
      }
      updateSelectionPopover();
    }

    document.addEventListener("selectionchange", handleSelectionChange);
    return () => {
      document.removeEventListener("selectionchange", handleSelectionChange);
    };
  }, [item, highlightActionPopover, notePopover]);

  useEffect(() => {
    if (!highlightActionPopover) return;
    const close = (event: Event) => {
      const target = event.target;
      if (target instanceof Element && target.closest(".reader-highlight-menu")) {
        return;
      }
      setHighlightActionPopover(null);
    };
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [highlightActionPopover]);

  useEffect(() => {
    if (!annotationMessage) return;
    const timeout = window.setTimeout(() => setAnnotationMessage(null), 3000);
    return () => window.clearTimeout(timeout);
  }, [annotationMessage]);

  const from = new URLSearchParams(location.search).get("from");
  const paragraphs = splitParagraphs(item?.parsed_document?.plain_text);
  const isVideo = item?.content_type === "bilibili_video";
  const isPodcast = item?.content_type === "podcast_episode";
  const hasTranscript = (item?.transcript?.segments?.length ?? 0) > 0 || Boolean(item?.transcript?.full_text?.trim());
  const hasArticleBody = paragraphs.length > 0;
  const podcastDescriptionParagraphs = isPodcast ? splitPodcastDescription(item?.parsed_document?.plain_text) : [];
  const aiSummaries = item?.summaries.filter((summary) => summary.model_name || summary.summary_type === "visual_context") ?? [];
  const uid = item?.uid ?? item?.id ?? itemId;
  const folderName = displayFolderName(item?.folder_name ?? workspace?.default_inbox_folder?.name, item?.is_inbox ?? !item);
  const sourceLabel = item?.metadata.podcast?.podcast_title ?? item?.metadata.site_name ?? item?.source_url ?? "未知来源";
  const transcriptSegments = item?.transcript?.segments ?? [];
  const readingState = liveReadingState ?? item?.reading_state ?? null;
  const progress = clampProgress(readingState?.progress_percent ?? 0);
  const activeTasks = itemTasks.filter(taskIsActive);
  const latestTask = itemTasks[0] ?? null;
  const visibleTask = activeTasks[0] ?? latestTask;
  const activeSummaryTask = activeTasks.find((task) => task.task_type === "generate_summary") ?? null;
  const hasActiveTask = activeTasks.length > 0 || item?.status === "pending" || item?.status === "processing";
  const taskBannerTone = visibleTask?.status === "failed" || item?.status === "failed" ? "failed" : hasActiveTask ? "active" : "idle";
  const highlightCount = item?.highlights.length ?? 0;
  const noteCount = item?.notes.length ?? 0;
  const inboxFolderId = workspace?.default_inbox_folder?.id ?? "inbox";
  const knowledgeFolders = folders.filter((folder) => folder.id !== inboxFolderId);
  const knowledgeLocationLabel = item?.is_inbox ? "稍后阅读" : folderName;
  const noteTargetHighlight = item?.highlights.find((highlight) => highlight.id === noteTargetHighlightId) ?? null;
  const notesByHighlightId = useMemo(() => {
    const next = new Map<string, string>();
    for (const note of item?.notes ?? []) {
      if (note.highlight_id && note.content.trim()) {
        next.set(note.highlight_id, note.content.trim());
      }
    }
    return next;
  }, [item?.notes]);

  const backHref = (() => {
    if (from === "feed") return "/feed";
    if (from === "podcasts") return "/podcasts";
    if (from === "inbox") return "/inbox";
    if (item?.folder_id && item.folder_id !== "inbox") return `/folders/${item.folder_id}`;
    if (item?.is_inbox) return "/inbox";
    return "/library";
  })();

  function renderTranscriptRows(jumpable: boolean) {
    return (
      <div className="transcript-list">
        {transcriptSegments.map((segment, index) => {
          const key = `${String(segment.start_ms)}-${String(index)}`;
          const isActive = activeTranscriptStartMs === segment.start_ms;
          const timeLabel = formatTranscriptTime(segment.start_ms);
          return (
            <div
              key={key}
              ref={(node) => {
                transcriptSegmentRefs.current[String(segment.start_ms)] = node;
              }}
              className={`transcript-row${jumpable ? " transcript-row-jumpable" : ""}${isActive ? " transcript-row-active" : ""}`}
            >
              {jumpable ? (
                <button
                  type="button"
                  className="transcript-time transcript-time-button"
                  onClick={() => jumpToTranscriptSegment(segment)}
                  title={`跳到 ${timeLabel}`}
                >
                  {timeLabel}
                </button>
              ) : (
                <div className="transcript-time">{timeLabel}</div>
              )}
              <div>
                <p className="transcript-speaker">{segment.speaker ?? "说话人"}</p>
                <p className="transcript-text">{renderAnnotatedText(segment.text)}</p>
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  function annotatedRangesForText(text: string) {
    const candidates = (item?.highlights ?? [])
      .map((highlight) => {
        const quote = highlight.quote_text.trim();
        if (!quote) return null;
        const start = text.toLowerCase().indexOf(quote.toLowerCase());
        if (start < 0) return null;
        return { start, end: start + quote.length, highlight };
      })
      .filter((range): range is { start: number; end: number; highlight: ApiHighlight } => Boolean(range))
      .sort((a, b) => (b.end - b.start) - (a.end - a.start));

    const selected: typeof candidates = [];
    for (const candidate of candidates) {
      if (selected.some((range) => candidate.start < range.end && candidate.end > range.start)) {
        continue;
      }
      selected.push(candidate);
    }
    return selected.sort((a, b) => a.start - b.start);
  }

  function renderAnnotatedText(text: string) {
    const ranges = annotatedRangesForText(text);
    if (!ranges.length) return text;

    const nodes: ReactNode[] = [];
    let cursor = 0;
    ranges.forEach((range, index) => {
      if (range.start > cursor) {
        nodes.push(text.slice(cursor, range.start));
      }
      const noteContent = notesByHighlightId.get(range.highlight.id);
      nodes.push(
        <mark
          key={`${range.highlight.id}-${index}`}
          className="reader-inline-highlight"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            window.getSelection()?.removeAllRanges();
            setSelectionPopover(null);
            openHighlightActions(range.highlight, event.clientX, event.clientY);
          }}
          onDoubleClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            window.getSelection()?.removeAllRanges();
            setSelectionPopover(null);
            openHighlightActions(range.highlight, event.clientX, event.clientY);
          }}
          onContextMenu={(event) => {
            event.preventDefault();
            event.stopPropagation();
            window.getSelection()?.removeAllRanges();
            setSelectionPopover(null);
            openHighlightActions(range.highlight, event.clientX, event.clientY);
          }}
          title="右键或双击管理高亮"
        >
          {text.slice(range.start, range.end)}
          {noteContent && (
            <button
              type="button"
              className="reader-inline-note-marker"
              title={noteContent}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                window.getSelection()?.removeAllRanges();
                openFloatingNote({
                  quoteText: range.highlight.quote_text,
                  highlightId: range.highlight.id,
                  noteId: range.highlight.note_id,
                  mode: "view",
                  x: Math.min(event.clientX, window.innerWidth - 360),
                  y: Math.min(event.clientY + 10, window.innerHeight - 220),
                });
              }}
            >
              <span className="icon icon-sm">sticky_note_2</span>
            </button>
          )}
        </mark>,
      );
      cursor = range.end;
    });
    if (cursor < text.length) {
      nodes.push(text.slice(cursor));
    }
    return nodes;
  }

  function findExistingHighlightForQuote(quoteText: string) {
    const normalizedQuote = quoteText.trim().toLowerCase();
    if (!normalizedQuote) return null;
    return [...(item?.highlights ?? [])]
      .sort((a, b) => {
        const aHasNote = a.note_id ? 1 : 0;
        const bHasNote = b.note_id ? 1 : 0;
        if (aHasNote !== bHasNote) return bHasNote - aHasNote;
        return b.quote_text.length - a.quote_text.length;
      })
      .find((highlight) => {
        const normalizedHighlight = highlight.quote_text.trim().toLowerCase();
        return (
          normalizedHighlight.includes(normalizedQuote)
          || normalizedQuote.includes(normalizedHighlight)
        );
      }) ?? null;
  }

  function handleToggleReadStatus() {
    if (!item || !readingState) return;
    const nextProgress = progress >= 100 ? 0 : 100;
    syncReadingState(
      {
        progress_percent: nextProgress,
        last_read_at: new Date().toISOString(),
        is_archived: readingState.is_archived,
        is_favorited: readingState.is_favorited,
        last_position_type: "manual_read_status",
        last_position_value: String(nextProgress),
      },
      true,
    );
  }

  function selectedReaderText() {
    return getReaderSelection()?.quoteText ?? "";
  }

  function getReaderSelection(): ReaderSelectionPopover | null {
    const selection = window.getSelection();
    const text = selection?.toString().trim() ?? "";
    if (!text) {
      return null;
    }
    const readerColumn = document.querySelector(".reader-column");
    if (!readerColumn || !selection?.rangeCount) {
      return null;
    }
    const range = selection.getRangeAt(0);
    if (!readerColumn.contains(range.commonAncestorContainer)) {
      return null;
    }
    const rect = range.getBoundingClientRect();
    const fallbackRect = range.getClientRects()[0];
    const targetRect = rect.width || rect.height ? rect : fallbackRect;
    if (!targetRect) {
      return null;
    }
    return {
      quoteText: text.slice(0, 1200),
      x: Math.min(Math.max(targetRect.left + targetRect.width / 2, 16), window.innerWidth - 240),
      y: Math.max(targetRect.top - 52, 12),
    };
  }

  function updateSelectionPopover() {
    window.setTimeout(() => {
      if (highlightActionPopover || notePopover) {
        setSelectionPopover(null);
        return;
      }
      const nextSelection = getReaderSelection();
      const existingHighlight = nextSelection ? findExistingHighlightForQuote(nextSelection.quoteText) : null;
      if (nextSelection && existingHighlight) {
        window.getSelection()?.removeAllRanges();
        setSelectionPopover(null);
        openHighlightActions(existingHighlight, nextSelection.x, nextSelection.y + 44);
        return;
      }
      setSelectionPopover(nextSelection);
    }, 0);
  }

  async function createHighlightFromQuote(quoteText: string) {
    if (!item) return null;
    if (!quoteText) {
      setAnnotationMessage("请先在正文或转写中选中一段文字。");
      return null;
    }
    const highlight = await client.createHighlight(item.id, {
      quote_text: quoteText,
      anchor_type: isVideo || isPodcast ? "transcript_segment" : "article_text",
      color: "yellow",
    });
    setItem({ ...item, highlights: [highlight, ...item.highlights] });
    setNoteTargetHighlightId(highlight.id);
    setAnnotationMessage("已创建高亮。");
    window.getSelection()?.removeAllRanges();
    return highlight;
  }

  async function handleCreateFloatingHighlight(quoteText: string) {
    if (!item || savingAnnotation) return;
    setSavingAnnotation(true);
    try {
      await createHighlightFromQuote(quoteText);
      setSelectionPopover(null);
    } catch (error) {
      setAnnotationMessage(error instanceof Error ? error.message : "创建高亮失败");
    } finally {
      setSavingAnnotation(false);
    }
  }

  function openFloatingNote(popover: ReaderNotePopover) {
    const existingNote = popover.noteId
      ? item?.notes.find((note) => note.id === popover.noteId)
      : popover.highlightId
        ? item?.notes.find((note) => note.highlight_id === popover.highlightId)
        : null;
    setNoteDraft(existingNote?.content ?? "");
    setNoteTargetHighlightId(popover.highlightId);
    setNotePopover(popover);
    setSelectionPopover(null);
    setHighlightActionPopover(null);
  }

  function currentPopoverNote() {
    if (!notePopover || !item) return null;
    if (notePopover.noteId) {
      return item.notes.find((note) => note.id === notePopover.noteId) ?? null;
    }
    if (notePopover.highlightId) {
      return item.notes.find((note) => note.highlight_id === notePopover.highlightId) ?? null;
    }
    return null;
  }

  async function handleDeleteNoteAndDefaultHighlight(noteId: string) {
    if (!item || savingAnnotation) return;
    const note = item.notes.find((entry) => entry.id === noteId);
    const boundHighlight = note?.highlight_id
      ? item.highlights.find((highlight) => highlight.id === note.highlight_id)
      : null;
    if (boundHighlight) {
      await handleDeleteHighlight(boundHighlight);
      setNotePopover(null);
      setAnnotationMessage("笔记已删除。");
      return;
    }
    await handleDeleteNote(noteId);
    setNotePopover(null);
  }

  function openHighlightActions(highlight: ApiHighlight, x: number, y: number) {
    setSelectionPopover(null);
    setNotePopover(null);
    setHighlightActionPopover({
      highlight,
      x: Math.min(x, window.innerWidth - 240),
      y: Math.min(y, window.innerHeight - 132),
    });
  }

  async function handleDeleteHighlight(highlight: ApiHighlight) {
    if (!item || savingAnnotation) return;
    setSavingAnnotation(true);
    try {
      await client.deleteHighlight(highlight.id);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 404) {
        setAnnotationMessage(error instanceof Error ? error.message : "取消高亮失败");
        setSavingAnnotation(false);
        return;
      }
    }

    try {
      setItem({
        ...item,
        highlights: item.highlights.filter((entry) => entry.id !== highlight.id),
        notes: item.notes.filter((note) => note.highlight_id !== highlight.id && note.id !== highlight.note_id),
      });
      setHighlightActionPopover(null);
      setAnnotationMessage(highlight.note_id ? "已取消高亮，并移除绑定笔记。" : "已取消高亮。");
    } finally {
      setSavingAnnotation(false);
    }
  }

  async function handleCreateNote(context?: { quoteText?: string | null; highlightId?: string | null; noteId?: string | null }) {
    if (!item || savingAnnotation) return;
    const content = noteDraft.trim();
    if (!content) {
      setAnnotationMessage("请先输入笔记内容。");
      return;
    }

    setSavingAnnotation(true);
    try {
      if (context?.noteId) {
        const updatedNote = await client.updateNote(context.noteId, content);
        setItem({
          ...item,
          notes: item.notes.map((note) => note.id === updatedNote.id ? updatedNote : note),
        });
        setNoteDraft("");
        setNoteTargetHighlightId(null);
        setNotePopover(null);
        setAnnotationMessage("笔记已更新。");
        return;
      }

      let targetHighlight: ApiHighlight | null = context?.highlightId
        ? item.highlights.find((highlight) => highlight.id === context.highlightId) ?? null
        : noteTargetHighlight;
      const quoteText = context?.quoteText ?? selectedReaderText();
      if (!targetHighlight && quoteText) {
        targetHighlight = await client.createHighlight(item.id, {
          quote_text: quoteText,
          anchor_type: isVideo || isPodcast ? "transcript_segment" : "article_text",
          color: "yellow",
        });
      }

      const note = await client.createNote(item.id, {
        content,
        highlight_id: targetHighlight?.id ?? null,
      });
      const nextHighlights = targetHighlight
        ? [targetHighlight, ...item.highlights.filter((highlight) => highlight.id !== targetHighlight.id)].map((highlight) =>
            highlight.id === targetHighlight?.id ? { ...highlight, note_id: note.id } : highlight
          )
        : item.highlights;
      setItem({ ...item, highlights: nextHighlights, notes: [note, ...item.notes] });
      setNoteDraft("");
      setNoteTargetHighlightId(null);
      setNotePopover(null);
      setAnnotationMessage(targetHighlight ? "已保存笔记并绑定高亮。" : "已保存独立笔记。");
      window.getSelection()?.removeAllRanges();
    } catch (error) {
      setAnnotationMessage(error instanceof Error ? error.message : "保存笔记失败");
    } finally {
      setSavingAnnotation(false);
    }
  }

  async function handleDeleteNote(noteId: string) {
    if (!item || savingAnnotation) return;
    setSavingAnnotation(true);
    try {
      await client.deleteNote(noteId);
      setItem({
        ...item,
        notes: item.notes.filter((note) => note.id !== noteId),
        highlights: item.highlights.map((highlight) => highlight.note_id === noteId ? { ...highlight, note_id: null } : highlight),
      });
      setAnnotationMessage("笔记已删除。");
    } catch (error) {
      setAnnotationMessage(error instanceof Error ? error.message : "删除笔记失败");
    } finally {
      setSavingAnnotation(false);
    }
  }

  async function handleSaveTags() {
    if (!item || savingAnnotation) return;
    const tags = tagDraft.split(/[，,]/).map((tag) => tag.trim()).filter(Boolean);
    setSavingAnnotation(true);
    try {
      const response = await client.setItemTags(item.id, tags);
      setItem({ ...item, tags: response.items });
      setTagDraft(response.items.map((tag) => tag.name).join(", "));
      setAnnotationMessage("标签已保存。");
    } catch (error) {
      setAnnotationMessage(error instanceof Error ? error.message : "保存标签失败");
    } finally {
      setSavingAnnotation(false);
    }
  }

  async function handleMoveToKnowledge(folderId: string) {
    if (!item || savingAnnotation) return;
    setSavingAnnotation(true);
    try {
      const result = await client.moveItem(item.id, folderId);
      setItem({
        ...item,
        folder_id: result.folder_id,
        folder_name: result.folder_name,
        is_inbox: result.is_inbox,
      });
      await loadFolders();
      setAnnotationMessage(result.is_inbox ? "已移回稍后阅读。" : `已收藏到知识库：${result.folder_name}`);
    } catch (error) {
      setAnnotationMessage(error instanceof Error ? error.message : "更新知识库位置失败");
    } finally {
      setSavingAnnotation(false);
    }
  }

  async function handleGenerateSummary() {
    if (!item || generatingSummary) return;
    if (activeSummaryTask) {
      setSummaryMessage(`摘要任务已在${taskStatusLabel(activeSummaryTask.status)}，无需重复提交。`);
      setSummaryError(null);
      return;
    }
    setGeneratingSummary(true);
    setSummaryMessage(null);
    setSummaryError(null);
    try {
      const task = await client.generateItemSummary(item.id);
      setSummaryMessage(`已提交摘要任务：${task.task_id}`);
      window.setTimeout(() => {
        void client.getItem(item.id).then((nextItem) => {
          if (latestItemIdRef.current === item.id) {
            setItem(nextItem);
            setLiveReadingState(nextItem.reading_state);
          }
        }).catch(() => {
          // The task may still be running; the user can refresh or trigger again later.
        });
      }, 3500);
    } catch (error) {
      setSummaryError(error instanceof Error ? error.message : "提交摘要任务失败");
    } finally {
      setGeneratingSummary(false);
    }
  }

  if (loading) {
    return (
      <div className="reader-page reader-page-feedback">
        <div style={{ textAlign: "center" }}>
          <span className="icon icon-lg" style={{ color: "var(--primary)", display: "block", marginBottom: 12, animation: "spin 1s linear infinite" }}>sync</span>
          <p className="text-meta">正在加载…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="reader-page reader-page-feedback">
        <div className="feedback feedback-error">{error}</div>
      </div>
    );
  }

  if (!item) {
    return (
      <div className="reader-page reader-page-feedback">
        <div className="feedback feedback-info">未找到该条目。</div>
      </div>
    );
  }

  return (
    <div className="reader-page">
      <div className="reader-shell">
        <div className="reader-toolbar">
          <div className="reader-toolbar-meta">
            <Link className="btn btn-ghost btn-sm" to={backHref}>
              <span className="icon icon-sm">arrow_back</span>
              返回
            </Link>
            <span className="chip chip-neutral">{folderName}</span>
            <span className="reader-toolbar-source">{sourceLabel}</span>
          </div>
          <div className="btn-group reader-toolbar-actions">
            {item.status === "completed" ? (
              <button type="button" className="btn btn-secondary btn-sm" onClick={handleToggleReadStatus}>
                <span className="icon icon-sm">{progress >= 100 ? "done_all" : "radio_button_unchecked"}</span>
                {readingStatusLabel(progress)}
              </button>
            ) : (
              <span className={statusChipClass(item.status)}>{statusLabel(item.status)}</span>
            )}
            <span className="chip chip-neutral">
              <span className="icon icon-sm">{isPodcast ? "podcasts" : isVideo ? "smart_display" : "article"}</span>
              {isPodcast ? "播客" : isVideo ? "视频" : "文章"}
            </span>
            {item.source_url && (
              <a className="btn btn-secondary btn-sm" href={item.source_url} target="_blank" rel="noreferrer">
                <span className="icon icon-sm">open_in_new</span>
                {isPodcast ? "来源" : "原文"}
              </a>
            )}
          </div>
        </div>

        <div className="reader-layout">
          <div className="reader-column" onMouseUp={updateSelectionPopover} onKeyUp={updateSelectionPopover}>
            {progress > 0 && (
              <div className="reading-progress-bar">
                <div className="reading-progress-fill" style={{ width: `${progress}%` }} />
              </div>
            )}

            <h1 className="article-title">{item.title}</h1>
            <div className="article-meta-row">
              <span className="chip chip-neutral">UID {uid}</span>
              {item.metadata.author_name && <span className="text-caption">{item.metadata.author_name}</span>}
              {item.metadata.published_at && <span className="text-caption">{formatDisplayDate(item.metadata.published_at)}</span>}
            </div>

            {(hasActiveTask || visibleTask?.status === "failed" || item.status === "failed" || taskPollError) && (
              <div className={`processing-banner processing-banner-${taskBannerTone}`}>
                <span className="processing-banner-icon icon icon-sm">
                  {taskBannerTone === "failed" ? "error" : "sync"}
                </span>
                <div>
                  <div className="processing-banner-title">
                    {taskBannerTone === "failed"
                      ? "处理失败"
                      : visibleTask
                        ? taskTypeLabel(visibleTask.task_type, item.content_type)
                        : "正在处理内容"}
                  </div>
                  <div className="processing-banner-text">
                    {taskPollError
                      ? `状态同步失败：${taskPollError}`
                      : visibleTask
                        ? `${taskStatusLabel(visibleTask.status)}${visibleTask.error_message ? `：${visibleTask.error_message}` : ""}`
                        : "后台正在处理，完成后会自动刷新这里。"}
                  </div>
                </div>
              </div>
            )}

            <div className="reader-content-tabs" role="tablist" aria-label="阅读内容">
              <button
                type="button"
                role="tab"
                aria-selected={readerContentTab === "ai"}
                className={`reader-content-tab ${readerContentTab === "ai" ? "active" : ""}`}
                onClick={() => setReaderContentTab("ai")}
              >
                <span className="icon icon-sm">auto_awesome</span>
                AI
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={readerContentTab === "source"}
                className={`reader-content-tab ${readerContentTab === "source" ? "active" : ""}`}
                onClick={() => setReaderContentTab("source")}
              >
                <span className="icon icon-sm">{isPodcast ? "podcasts" : isVideo ? "subtitles" : "article"}</span>
                原文
              </button>
            </div>

            {readerContentTab === "source" ? (
              <>
                {isPodcast && (
                  <div className="article-section">
                    <div className="article-section-title">音频</div>
                    <div className="podcast-player-panel">
                      {item.metadata.podcast?.enclosure_url ? (
                        <audio ref={podcastAudioRef} controls preload="metadata" src={item.metadata.podcast.enclosure_url} style={{ width: "100%" }} />
                      ) : (
                        <p className="text-meta">暂未保存音频来源。</p>
                      )}
                    </div>
                  </div>
                )}

                {isPodcast && podcastDescriptionParagraphs.length > 0 && (
                  <div className="article-section">
                    <div className="article-section-title">节目简介</div>
                    <div className="podcast-description prose">
                      {podcastDescriptionParagraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                    </div>
                  </div>
                )}

                {isVideo && (
                  <div className="article-section">
                    <div className="article-section-title">转写参考</div>
                    {transcriptSegments.length ? (
                      <>
                        <p className="text-meta" style={{ marginBottom: 14 }}>
                          点击左侧时间戳可直接跳到对应片段。
                        </p>
                        {renderTranscriptRows(true)}
                      </>
                    ) : item.transcript?.full_text ? (
                      <p className="prose">{item.transcript.full_text}</p>
                    ) : (
                      <p className="text-meta">暂未生成转写。</p>
                    )}
                  </div>
                )}

                {!isVideo && !isPodcast && (
                  <div className="article-section">
                    <div className="article-section-title">正文</div>
                    <div className="prose">
                      {hasArticleBody ? paragraphs.map((paragraph) => <p key={paragraph}>{renderAnnotatedText(paragraph)}</p>) : <p className="text-meta">暂未生成可读正文。</p>}
                    </div>
                  </div>
                )}

                {isVideo && hasArticleBody && (
                  <div className="article-section">
                    <div className="article-section-title">整理稿</div>
                    <div className="prose">
                      {paragraphs.map((paragraph) => <p key={paragraph}>{renderAnnotatedText(paragraph)}</p>)}
                    </div>
                  </div>
                )}

                {isPodcast && hasTranscript && (
                  <div className="article-section">
                    <div className="transcript-collapsed-header">
                      <div className="article-section-title" style={{ marginBottom: 0 }}>转写参考</div>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setPodcastTranscriptExpanded((current) => !current)}
                      >
                        <span className="icon icon-sm">{podcastTranscriptExpanded ? "expand_less" : "expand_more"}</span>
                        {podcastTranscriptExpanded ? "收起转写" : "展开转写"}
                      </button>
                    </div>
                    {podcastTranscriptExpanded && (
                      transcriptSegments.length ? (
                        renderTranscriptRows(true)
                      ) : (
                        <p className="text-meta">{item.transcript?.full_text ?? "暂无转写参考。"}</p>
                      )
                    )}
                  </div>
                )}

                {!isVideo && !isPodcast && hasTranscript && (
                  <div className="article-section">
                    <div className="article-section-title">转写参考</div>
                    {transcriptSegments.length ? (
                      renderTranscriptRows(false)
                    ) : (
                      <p className="text-meta">{item.transcript?.full_text ?? "暂无转写参考。"}</p>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="article-section">
                <div className="summary-section-header">
                  <div className="article-section-title">AI 摘要</div>
                  <button type="button" className="btn btn-secondary btn-xs" onClick={() => void handleGenerateSummary()} disabled={generatingSummary || Boolean(activeSummaryTask)}>
                    <span className="icon icon-sm">auto_awesome</span>
                    {generatingSummary ? "提交中…" : activeSummaryTask ? "生成中" : "重新生成"}
                  </button>
                </div>
                {summaryMessage && <div className="feedback feedback-success" style={{ marginBottom: 12 }}>{summaryMessage}</div>}
                {summaryError && <div className="feedback feedback-error" style={{ marginBottom: 12 }}>{summaryError}</div>}
                {hasActiveTask && visibleTask && (
                  <div className="ai-generating-row">
                    <span className="icon icon-sm">sync</span>
                    <span>{taskTypeLabel(visibleTask.task_type, item.content_type)}，完成后会自动刷新摘要。</span>
                  </div>
                )}
                {aiSummaries.length ? (
                  <ul className="summary-list">
                    {aiSummaries.map((summary) => (
                      <li key={`${summary.summary_type}-${String(summary.version ?? 0)}`} className="summary-item">
                        <div className="summary-content markdown-body">{renderMarkdown(summary.content, (text) => renderInlineMarkdown(text, renderAnnotatedText))}</div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-meta">暂无摘要。</p>
                )}
              </div>
            )}

          </div>

          <div className="card detail-rail reader-rail" style={{ padding: 0, overflow: "hidden" }}>
            <div className="card-header" style={{ padding: "16px 20px", borderBottom: "1px solid rgba(var(--outline-rgb),0.15)" }}>
              <span className="card-title">条目信息</span>
              <span className="card-meta">已同步</span>
            </div>

            <div style={{ padding: "16px 20px" }}>
              <div className="reader-context-panel" aria-label="阅读进度">
                <div className="reader-context-kicker">阅读进度</div>
                <div className="reader-context-origin">{progress}%</div>
                <div className="progress-bar" style={{ marginBottom: 14 }}>
                  <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
                </div>
                <div className="reader-context-stats">
                  <div>
                    <span>{highlightCount}</span>
                    <small>高亮</small>
                  </div>
                  <div>
                    <span>{noteCount}</span>
                    <small>笔记</small>
                  </div>
                </div>
              </div>
              <div className="info-list">
                {[
                  { label: "UID", value: uid },
                  { label: "位置", value: folderName },
                  { label: "来源", value: sourceLabel },
                  { label: "发布时间", value: formatDisplayDate(item.metadata.published_at) },
                  { label: "作者", value: item.metadata.author_name ?? "未署名" },
                ].map((row) => (
                  <div key={row.label} className="info-row">
                    <span className="info-row-label">{row.label}</span>
                    <span className="info-row-value">{row.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ padding: "0 20px 16px", borderTop: "1px solid rgba(var(--outline-rgb),0.12)" }}>
              <div className="rail-section-title" style={{ marginTop: 16 }}>分类</div>
              <label className="text-caption" style={{ display: "block", marginBottom: 6 }}>标签</label>
              {item.tags.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                  {item.tags.map((tag, index) => (
                    <span key={index} className="chip chip-secondary">
                      {tag.name}
                    </span>
                  ))}
                </div>
              )}
              <input
                className="input"
                value={tagDraft}
                onChange={(event) => setTagDraft(event.target.value)}
                placeholder="用逗号分隔标签"
                style={{ marginBottom: 8 }}
              />
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => void handleSaveTags()} disabled={savingAnnotation}>
                <span className="icon icon-sm">sell</span>
                保存标签
              </button>

              <div className="rail-section-title" style={{ marginTop: 16 }}>知识库位置</div>
              <div className="btn-group" style={{ marginBottom: 8, alignItems: "stretch" }}>
                <select
                  className="input"
                  value={item.is_inbox ? inboxFolderId : item.folder_id}
                  onChange={(event) => void handleMoveToKnowledge(event.target.value)}
                  disabled={savingAnnotation}
                  style={{ minWidth: 0 }}
                >
                  <option value={inboxFolderId}>稍后阅读</option>
                  {knowledgeFolders.map((folder) => (
                    <option key={folder.id} value={folder.id}>{folder.name}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>

      {annotationMessage && (
        <div className="reader-toast" role="status">
          {annotationMessage}
        </div>
      )}

      {selectionPopover && !notePopover && (
        <div className="reader-selection-popover" style={{ left: selectionPopover.x, top: selectionPopover.y }}>
          <button type="button" className="selection-popover-button" onMouseDown={(event) => { event.preventDefault(); event.stopPropagation(); }} onClick={() => void handleCreateFloatingHighlight(selectionPopover.quoteText)}>
            <span className="icon icon-sm">border_color</span>
            高亮
          </button>
          <button
            type="button"
            className="selection-popover-button"
            onMouseDown={(event) => { event.preventDefault(); event.stopPropagation(); }}
            onClick={() => openFloatingNote({
              quoteText: selectionPopover.quoteText,
              highlightId: null,
              mode: "edit",
              x: Math.min(selectionPopover.x - 120, window.innerWidth - 360),
              y: Math.min(selectionPopover.y + 44, window.innerHeight - 220),
            })}
          >
            <span className="icon icon-sm">sticky_note_2</span>
            笔记
          </button>
        </div>
      )}

      {highlightActionPopover && !notePopover && (
        <div
          className="reader-highlight-menu"
          style={{ left: highlightActionPopover.x, top: highlightActionPopover.y }}
          onPointerDown={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            className="context-menu-item"
            onClick={() => openFloatingNote({
              quoteText: highlightActionPopover.highlight.quote_text,
              highlightId: highlightActionPopover.highlight.id,
              noteId: highlightActionPopover.highlight.note_id,
              mode: highlightActionPopover.highlight.note_id ? "view" : "edit",
              x: Math.min(highlightActionPopover.x, window.innerWidth - 360),
              y: Math.min(highlightActionPopover.y + 42, window.innerHeight - 220),
            })}
          >
            <span className="icon icon-sm">sticky_note_2</span>
            {highlightActionPopover.highlight.note_id ? "查看笔记" : "写笔记"}
          </button>
          <button
            type="button"
            className="context-menu-item context-menu-danger"
            onClick={() => {
              const noteId = highlightActionPopover.highlight.note_id;
              if (noteId) {
                void handleDeleteNoteAndDefaultHighlight(noteId);
                return;
              }
              void handleDeleteHighlight(highlightActionPopover.highlight);
            }}
            disabled={savingAnnotation}
          >
            <span className="icon icon-sm">{highlightActionPopover.highlight.note_id ? "delete" : "format_color_reset"}</span>
            {highlightActionPopover.highlight.note_id ? "删除笔记" : "取消高亮"}
          </button>
        </div>
      )}

      {notePopover && (
        <div className="reader-note-popover" style={{ left: notePopover.x, top: notePopover.y }}>
          {notePopover.quoteText && (
            <div className="reader-note-quote">
              {notePopover.quoteText.slice(0, 160)}
            </div>
          )}
          {notePopover.mode === "view" ? (
            <div className="reader-note-content">
              {currentPopoverNote()?.content ?? noteDraft}
            </div>
          ) : (
            <textarea
              className="input"
              value={noteDraft}
              onChange={(event) => setNoteDraft(event.target.value)}
              placeholder="写一条笔记"
              rows={4}
              autoFocus
            />
          )}
          <div className="btn-group" style={{ justifyContent: "flex-end", marginTop: 10 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setNotePopover(null);
                setNoteDraft("");
                setNoteTargetHighlightId(null);
              }}
            >
              取消
            </button>
            {notePopover.mode === "view" ? (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => setNotePopover({ ...notePopover, mode: "edit" })}
              >
                <span className="icon icon-sm">edit_note</span>
                编辑
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => void handleCreateNote({
                  quoteText: notePopover.quoteText,
                  highlightId: notePopover.highlightId,
                  noteId: notePopover.noteId,
                })}
                disabled={savingAnnotation}
              >
                <span className="icon icon-sm">add_comment</span>
                保存笔记
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
