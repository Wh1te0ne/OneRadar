import { FormEvent, KeyboardEvent, MouseEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { createApiClient } from "../api";
import type { ApiPodcastEpisode, ApiPodcastSearchItem, ApiPodcastSubscription } from "../api/types";
import { useAppState } from "../state/appState";

type PodcastTab = "subscribed" | "search";

type SelectedPodcast = {
  id?: string | null;
  feed_url: string;
  title: string;
  author?: string | null;
  image_url?: string | null;
  page_url?: string | null;
  subscribed: boolean;
};

function formatDate(value?: string | null) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatDuration(seconds?: number | null) {
  if (!seconds) return null;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours} 小时 ${minutes} 分钟`;
  return `${minutes} 分钟`;
}

function hostOf(url?: string | null) {
  if (!url) return "";
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function PodcastsPage() {
  const { apiBaseUrl } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);

  const [tab, setTab] = useState<PodcastTab>("subscribed");
  const [subscriptions, setSubscriptions] = useState<ApiPodcastSubscription[]>([]);
  const [episodes, setEpisodes] = useState<ApiPodcastEpisode[]>([]);
  const [selectedSubscription, setSelectedSubscription] = useState<string>("all");
  const [selectedPodcast, setSelectedPodcast] = useState<SelectedPodcast | null>(null);
  const [detailEpisodes, setDetailEpisodes] = useState<ApiPodcastEpisode[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("凹凸电波");
  const [searchResults, setSearchResults] = useState<ApiPodcastSearchItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [importingEpisodeId, setImportingEpisodeId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refreshSubscriptions() {
    const next = await client.listPodcastSubscriptions();
    setSubscriptions(next.items);
  }

  async function refreshEpisodes() {
    const next = await client.listPodcastEpisodes(120);
    setEpisodes(next.items);
  }

  async function refreshAll() {
    setBusy(true);
    setError(null);
    try {
      await refreshSubscriptions();
      await refreshEpisodes();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "播客列表读取失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!feedback) return;
    const timer = window.setTimeout(() => setFeedback(null), 2600);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  const filteredEpisodes = useMemo(() => {
    if (selectedSubscription === "all") return episodes;
    return episodes.filter((episode) => episode.subscription_id === selectedSubscription);
  }, [episodes, selectedSubscription]);

  const subscriptionByFeedUrl = useMemo(() => {
    const map = new Map<string, ApiPodcastSubscription>();
    subscriptions.forEach((subscription) => map.set(subscription.feed_url, subscription));
    return map;
  }, [subscriptions]);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    const query = searchQuery.trim();
    if (!query) return;
    setBusy(true);
    setError(null);
    setFeedback(null);
    try {
      const response = await client.searchPodcasts(query, "US", 20);
      setSearchResults(response.items);
      setTab("search");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "播客搜索失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSubscribe(item: ApiPodcastSearchItem, stayInDetail = false) {
    if (!item.feed_url) return;
    setBusy(true);
    setError(null);
    try {
      const subscription = await client.createPodcastSubscription({
        feed_url: item.feed_url,
        title: item.title,
        author: item.author,
        image_url: item.image_url,
        itunes_id: item.itunes_id,
        page_url: item.page_url,
      });
      setFeedback(`已订阅「${item.title}」`);
      await refreshAll();
      if (stayInDetail) {
        setSelectedPodcast((current) =>
          current?.feed_url === item.feed_url
            ? { ...current, id: subscription.id, subscribed: true }
            : current
        );
      } else {
        setTab("subscribed");
        setSelectedSubscription(subscription.id);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "订阅失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleUnsubscribe(subscription: ApiPodcastSubscription) {
    setBusy(true);
    setError(null);
    try {
      await client.deletePodcastSubscription(subscription.id);
      setFeedback(`已取消订阅「${subscription.title}」`);
      await refreshAll();
      setSelectedSubscription("all");
      setSelectedPodcast((current) =>
        current?.feed_url === subscription.feed_url ? { ...current, id: null, subscribed: false } : current
      );
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "取消订阅失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleImportEpisode(episode: ApiPodcastEpisode) {
    setImportingEpisodeId(episode.id);
    setError(null);
    setFeedback(null);
    try {
      const result = await client.importPodcastEpisode(episode);
      setFeedback(result.is_duplicate ? `已在稍后阅读：${result.uid}` : `已加入稍后阅读：${result.uid}`);
      await refreshEpisodes();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "加入稍后阅读失败");
    } finally {
      setImportingEpisodeId(null);
    }
  }

  async function openPodcast(podcast: SelectedPodcast) {
    setSelectedPodcast(podcast);
    setDetailEpisodes([]);
    setDetailLoading(true);
    setError(null);
    try {
      const response = await client.listPodcastFeedEpisodes({
        feedUrl: podcast.feed_url,
        title: podcast.title,
        author: podcast.author,
        imageUrl: podcast.image_url,
        limit: 160,
      });
      setDetailEpisodes(response.items);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "播客单集读取失败");
    } finally {
      setDetailLoading(false);
    }
  }

  function openSearchResult(item: ApiPodcastSearchItem) {
    if (!item.feed_url) {
      setError("Apple 没有返回这个播客的 RSS 地址，暂时无法查看单集。");
      return;
    }
    const subscription = subscriptionByFeedUrl.get(item.feed_url);
    void openPodcast({
      id: subscription?.id,
      feed_url: item.feed_url,
      title: item.title,
      author: item.author,
      image_url: item.image_url,
      page_url: item.page_url,
      subscribed: Boolean(subscription),
    });
  }

  function selectSubscription(subscription: ApiPodcastSubscription) {
    setSelectedPodcast(null);
    setTab("subscribed");
    setSelectedSubscription(subscription.id);
  }

  function closePodcast() {
    setSelectedPodcast(null);
    setDetailEpisodes([]);
    setDetailLoading(false);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div style={{ padding: "22px 28px 16px", borderBottom: "1px solid rgba(var(--outline-rgb),0.14)", background: "var(--surface-lowest)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 20 }}>
          <div>
            <p className="page-eyebrow">播客</p>
            <h2 style={{ margin: "4px 0 6px", fontSize: 28, letterSpacing: 0 }}>订阅与单集入库</h2>
            <p style={{ margin: 0, color: "var(--on-surface-v)", fontSize: 13 }}>
              订阅只负责发现新集；只有加入稍后阅读的单集才会下载音频并进入处理队列。
            </p>
          </div>
          <form onSubmit={handleSearch} style={{ display: "flex", gap: 8, minWidth: 360 }}>
            <input
              className="input"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="搜索播客名称"
              style={{ flex: 1 }}
            />
            <button className="btn btn-primary" type="submit" disabled={busy}>
              <span className="icon icon-sm">search</span>
              搜索
            </button>
          </form>
        </div>

        {!selectedPodcast && <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 18 }}>
          {([
            ["subscribed", "已订阅", subscriptions.length],
            ["search", "搜索结果", searchResults.length],
          ] as [PodcastTab, string, number][]).map(([value, label, count]) => (
            <button
              key={value}
              type="button"
              className={`btn btn-sm ${tab === value ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setTab(value)}
            >
              {label} · {count}
            </button>
          ))}
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => void refreshAll()} disabled={busy}>
            <span className="icon icon-sm">sync</span>
            刷新
          </button>
        </div>}
      </div>

      {feedback && <div className="feedback feedback-success" style={{ margin: "12px 28px 0" }}>{feedback}</div>}
      {error && <div className="feedback feedback-error" style={{ margin: "12px 28px 0" }}>{error}</div>}

      {selectedPodcast ? (
        <PodcastDetail
          podcast={selectedPodcast}
          episodes={detailEpisodes}
          loading={detailLoading}
          importingEpisodeId={importingEpisodeId}
          onBack={closePodcast}
          onImport={(episode) => void handleImportEpisode(episode)}
          onSubscribe={() =>
            void handleSubscribe(
              {
                title: selectedPodcast.title,
                author: selectedPodcast.author,
                feed_url: selectedPodcast.feed_url,
                page_url: selectedPodcast.page_url,
                image_url: selectedPodcast.image_url,
                is_subscribable: true,
              },
              true,
            )
          }
          onUnsubscribe={() => {
            const subscription = selectedPodcast.id ? subscriptions.find((entry) => entry.id === selectedPodcast.id) : undefined;
            if (subscription) void handleUnsubscribe(subscription);
          }}
        />
      ) : tab === "subscribed" ? (
        <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", minHeight: 0, flex: 1 }}>
          <aside style={{ borderRight: "1px solid rgba(var(--outline-rgb),0.12)", padding: "18px 18px 24px 28px", overflowY: "auto" }}>
            <button
              type="button"
              className={`podcast-source ${selectedSubscription === "all" ? "active" : ""}`}
              onClick={() => setSelectedSubscription("all")}
            >
              <span className="icon icon-sm">dynamic_feed</span>
              <span>全部新集</span>
              <span>{episodes.length}</span>
            </button>
            {subscriptions.map((subscription) => (
              <div key={subscription.id} className={`podcast-source ${selectedSubscription === subscription.id ? "active" : ""}`}>
                <button type="button" onClick={() => selectSubscription(subscription)}>
                  {subscription.image_url ? <img src={subscription.image_url} alt="" /> : <span className="icon icon-sm">podcasts</span>}
                  <span>{subscription.title}</span>
                </button>
                <button type="button" title="取消订阅" onClick={() => void handleUnsubscribe(subscription)}>
                  <span className="icon icon-sm">close</span>
                </button>
              </div>
            ))}
          </aside>

          <main style={{ overflowY: "auto", padding: "8px 0" }}>
            {filteredEpisodes.length === 0 ? (
              <div className="empty-state" style={{ marginTop: 80 }}>
                <div className="empty-state-icon"><span className="icon icon-lg">podcasts</span></div>
                <h3>{subscriptions.length ? "暂时没有可显示的单集" : "还没有订阅播客"}</h3>
                <p>搜索节目并订阅后，这里会按最新发布时间显示所有 episode。</p>
              </div>
            ) : (
              filteredEpisodes.map((episode) => (
                <PodcastEpisodeRow
                  key={episode.id}
                  episode={episode}
                  importing={importingEpisodeId === episode.id}
                  onImport={() => void handleImportEpisode(episode)}
                />
              ))
            )}
          </main>
        </div>
      ) : (
        <div style={{ flex: 1, overflowY: "auto", padding: "10px 0" }}>
          {searchResults.length === 0 ? (
            <div className="empty-state" style={{ marginTop: 80 }}>
              <div className="empty-state-icon"><span className="icon icon-lg">search</span></div>
              <h3>搜索播客</h3>
              <p>使用 Apple iTunes Search API，能取得 RSS 的节目可以直接订阅。</p>
            </div>
          ) : (
            searchResults.map((item) => (
              <PodcastSearchRow
                key={`${item.itunes_id ?? item.feed_url ?? item.title}`}
                item={item}
                subscribed={subscriptions.some((subscription) => subscription.feed_url === item.feed_url)}
                onOpen={() => openSearchResult(item)}
                onSubscribe={() => void handleSubscribe(item)}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function PodcastDetail({
  podcast,
  episodes,
  loading,
  importingEpisodeId,
  onBack,
  onImport,
  onSubscribe,
  onUnsubscribe,
}: {
  podcast: SelectedPodcast;
  episodes: ApiPodcastEpisode[];
  loading: boolean;
  importingEpisodeId: string | null;
  onBack: () => void;
  onImport: (episode: ApiPodcastEpisode) => void;
  onSubscribe: () => void;
  onUnsubscribe: () => void;
}) {
  return (
    <main style={{ flex: 1, overflowY: "auto", padding: "18px 28px 40px" }}>
      <button className="btn btn-ghost btn-sm" type="button" onClick={onBack}>
        <span className="icon icon-sm">arrow_back</span>
        返回播客
      </button>

      <section className="podcast-detail-header">
        {podcast.image_url ? <img className="podcast-detail-cover" src={podcast.image_url} alt="" /> : <div className="podcast-detail-cover placeholder"><span className="icon">podcasts</span></div>}
        <div className="podcast-detail-main">
          <p className="page-eyebrow">播客节目</p>
          <h2>{podcast.title}</h2>
          <div className="podcast-row-meta">
            {podcast.author && <span>{podcast.author}</span>}
            <span>{hostOf(podcast.feed_url)}</span>
            <span>{episodes.length} 集</span>
          </div>
        </div>
        <div className="podcast-row-actions">
          {podcast.page_url && (
            <a className="topbar-icon-btn" href={podcast.page_url} target="_blank" rel="noreferrer" title="打开来源">
              <span className="icon icon-sm">open_in_new</span>
            </a>
          )}
          {podcast.subscribed ? (
            <button className="btn btn-ghost btn-sm" type="button" onClick={onUnsubscribe}>
              <span className="icon icon-sm">check</span>
              已订阅
            </button>
          ) : (
            <button className="btn btn-primary btn-sm" type="button" onClick={onSubscribe}>
              <span className="icon icon-sm">add</span>
              订阅
            </button>
          )}
        </div>
      </section>

      {loading ? (
        <div className="empty-state" style={{ marginTop: 70 }}>
          <div className="empty-state-icon"><span className="icon icon-lg">sync</span></div>
          <h3>正在读取单集</h3>
          <p>从播客 RSS 拉取最新 episode 列表。</p>
        </div>
      ) : episodes.length === 0 ? (
        <div className="empty-state" style={{ marginTop: 70 }}>
          <div className="empty-state-icon"><span className="icon icon-lg">podcasts</span></div>
          <h3>没有可显示的单集</h3>
          <p>这个 RSS 没有返回带音频地址的 episode。</p>
        </div>
      ) : (
        <div className="podcast-detail-list">
          {episodes.map((episode) => (
            <PodcastEpisodeRow
              key={episode.id}
              episode={episode}
              importing={importingEpisodeId === episode.id}
              onImport={() => onImport(episode)}
            />
          ))}
        </div>
      )}
    </main>
  );
}

function PodcastEpisodeRow({ episode, importing, onImport }: { episode: ApiPodcastEpisode; importing: boolean; onImport: () => void }) {
  const duration = formatDuration(episode.duration_seconds);
  return (
    <article className="podcast-row">
      {episode.image_url ? <img className="podcast-cover" src={episode.image_url} alt="" /> : <div className="podcast-cover placeholder"><span className="icon">podcasts</span></div>}
      <div className="podcast-row-main">
        <div className="podcast-row-meta">
          <span>{episode.podcast_title}</span>
          <span>{formatDate(episode.published_at)}</span>
          {duration && <span>{duration}</span>}
        </div>
        <h3>{episode.title}</h3>
        <p>{episode.summary ?? "该单集没有提供简介。"}</p>
        <div className="podcast-row-foot">
          <span>{hostOf(episode.enclosure_url)}</span>
          {episode.is_imported && episode.item_id ? <Link to={`/items/${episode.item_id}?from=podcasts`}>已加入稍后阅读</Link> : null}
        </div>
      </div>
      <div className="podcast-row-actions">
        {episode.link && (
          <a className="topbar-icon-btn" href={episode.link} target="_blank" rel="noreferrer" title="打开来源">
            <span className="icon icon-sm">open_in_new</span>
          </a>
        )}
        <button className="btn btn-primary btn-sm" type="button" disabled={episode.is_imported || importing} onClick={onImport}>
          <span className="icon icon-sm">{episode.is_imported ? "done" : "playlist_add"}</span>
          {episode.is_imported ? "已加入" : importing ? "加入中…" : "稍后阅读"}
        </button>
      </div>
    </article>
  );
}

function PodcastSearchRow({
  item,
  subscribed,
  onOpen,
  onSubscribe,
}: {
  item: ApiPodcastSearchItem;
  subscribed: boolean;
  onOpen: () => void;
  onSubscribe: () => void;
}) {
  function stopAction(event: MouseEvent<HTMLAnchorElement | HTMLButtonElement>) {
    event.stopPropagation();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onOpen();
    }
  }

  return (
    <article
      className={`podcast-row ${item.feed_url ? "clickable" : ""}`}
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={handleKeyDown}
    >
      {item.image_url ? <img className="podcast-cover" src={item.image_url} alt="" /> : <div className="podcast-cover placeholder"><span className="icon">podcasts</span></div>}
      <div className="podcast-row-main">
        <div className="podcast-row-meta">
          <span>{item.author ?? "未知作者"}</span>
          {item.genre && <span>{item.genre}</span>}
          {item.episode_count ? <span>{item.episode_count} 集</span> : null}
        </div>
        <h3>{item.title}</h3>
        <p>{item.feed_url ? hostOf(item.feed_url) : "Apple 没有返回 RSS 地址，暂时无法订阅。"}</p>
      </div>
      <div className="podcast-row-actions">
        {item.page_url && (
          <a className="topbar-icon-btn" href={item.page_url} target="_blank" rel="noreferrer" title="打开 Apple Podcasts" onClick={stopAction}>
            <span className="icon icon-sm">open_in_new</span>
          </a>
        )}
        <button
          className="btn btn-primary btn-sm"
          type="button"
          disabled={!item.is_subscribable || subscribed}
          onClick={(event) => {
            stopAction(event);
            onSubscribe();
          }}
        >
          <span className="icon icon-sm">{subscribed ? "done" : "add"}</span>
          {subscribed ? "已订阅" : "订阅"}
        </button>
      </div>
    </article>
  );
}
