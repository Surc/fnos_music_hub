const $ = (s) => document.querySelector(s);
const state = {
  me: null,
  csrf: "",
  view: "discover",
  page: 1,
  search: "",
  provider: "kuwo",
  songs: [],
  favorites: new Set(),
  epoch: 0,
  drafts: new Map(),
};
const titles = {
  discover: ["发现与搜索", "先找到歌曲，再决定如何收藏与下载。"],
  favorites: ["我的收藏", "只属于当前飞牛用户的本地收藏。"],
  tasks: ["下载任务", "引擎继续工作，关闭页面也不会丢失任务。"],
  assets: ["已下载歌曲", "只显示已经通过完整音频校验的文件。"],
  accounts: ["平台账号", "本地收藏与云平台账号联动分别管理。"],
  injection: ["注入设置", "独立设置，和歌单、下载管理分别启用。"],
};
const statusNames = {
  queued: "待提交",
  submitting: "正在接单",
  running: "下载中",
  paused: "等待恢复",
  completed: "已校验完成",
  failed: "失败",
  attention: "需要核对",
  outcome_unknown: "接单结果未知",
};
const key = (track) =>
  JSON.stringify([track.provider, track.id_type, track.id]);
function node(tag, text, className) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (className) e.className = className;
  return e;
}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("#toast").hidden = true), 5500);
}
function signedOut() {
  state.epoch++;
  state.me = null;
  state.csrf = "";
  state.songs = [];
  state.favorites.clear();
  state.drafts.clear();
  $("#shell").hidden = true;
  $("#login").hidden = false;
  $("#view-content").replaceChildren();
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(state.csrf ? { "X-CSRF-Token": state.csrf } : {}),
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") signedOut();
    throw new Error(data.error?.message || "请求失败，请稍后重试");
  }
  return data;
}
function empty(title, description) {
  const e = node("div", undefined, "empty");
  e.append(node("strong", title), node("span", description));
  return e;
}
function button(text, action, className = "quiet") {
  const b = node("button", text, className);
  b.type = "button";
  b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      await action();
    } catch (e) {
      toast(e.message);
    } finally {
      b.disabled = false;
    }
  });
  return b;
}
function cards(songs) {
  const grid = node("div", undefined, "results");
  for (const song of songs) {
    const card = node("article", undefined, "song-card");
    card.append(
      node(
        "div",
        song.track?.provider === "qq" ? "QQ MUSIC" : "KUWO MUSIC",
        "song-source",
      ),
      node("h3", song.title),
      node("p", song.artist || "歌手信息未知"),
      node(
        "p",
        [
          song.album,
          song.duration_seconds
            ? `${Math.round(song.duration_seconds)} 秒`
            : null,
        ]
          .filter(Boolean)
          .join(" · "),
      ),
    );
    if (!song.track) {
      card.append(node("p", "来源条目暂时无法识别，仍保留原位置。", "error"));
      grid.append(card);
      continue;
    }
    const actions = node("div", undefined, "song-actions");
    const favorite = button(
      state.favorites.has(key(song.track)) ? "取消收藏" : "收藏",
      async () => {
        const enabled = !state.favorites.has(key(song.track));
        await api("/api/favorites", {
          method: "POST",
          body: JSON.stringify({ track: song.track, enabled }),
        });
        if (enabled) state.favorites.add(key(song.track));
        else state.favorites.delete(key(song.track));
        favorite.textContent = enabled ? "取消收藏" : "收藏";
        if (state.view === "favorites") await loadView();
      },
    );
    actions.append(favorite);
    const quality = node("select");
    quality.setAttribute("aria-label", "下载音质");
    for (const q of song.qualities.filter((q) =>
      ["128kmp3", "320kmp3", "flac", "hires"].includes(q.quality),
    )) {
      const opt = node("option", q.quality);
      opt.value = q.quality;
      quality.append(opt);
    }
    if ([...quality.options].some((o) => o.value === "320kmp3"))
      quality.value = "320kmp3";
    const download = button(
      song.track.provider === "kuwo" ? "下载" : "下载待接入",
      () => downloadSong(song, quality.value),
      "primary",
    );
    download.disabled =
      song.track.provider !== "kuwo" ||
      !quality.options.length ||
      !song.duration_seconds;
    if (quality.options.length) actions.append(quality);
    actions.append(download);
    card.append(actions);
    if (!song.qualities.length)
      card.append(
        node("p", "暂未提供音质；元数据与收藏仍可使用。", "small muted"),
      );
    grid.append(card);
  }
  return grid;
}
async function downloadSong(song, quality) {
  const draftKey = key(song.track) + quality;
  let draft = state.drafts.get(draftKey);
  if (!draft) {
    const manifest = await api("/api/manifests", {
      method: "POST",
      body: JSON.stringify({ tracks: [song.track] }),
    });
    draft = {
      manifest_id: manifest.id,
      quality,
      target_ref: "private",
      idem: crypto.randomUUID(),
    };
    state.drafts.set(draftKey, draft);
  }
  const epoch = state.epoch;
  await api("/api/tasks", {
    method: "POST",
    headers: { "Idempotency-Key": draft.idem },
    body: JSON.stringify({
      manifest_id: draft.manifest_id,
      quality: draft.quality,
      target_ref: draft.target_ref,
    }),
  });
  if (epoch !== state.epoch) return;
  state.drafts.delete(draftKey);
  toast("下载任务已保存");
  await navigate("tasks");
}
async function navigate(view) {
  state.view = view;
  for (const b of document.querySelectorAll("nav button"))
    b.classList.toggle("active", b.dataset.view === view);
  $("#page-title").textContent = titles[view][0];
  $("#page-description").textContent = titles[view][1];
  $("#discover-controls").hidden = view !== "discover";
  $("#pagination").hidden = true;
  await loadView();
}
async function loadView() {
  if (!state.me) return;
  const view = state.view,
    epoch = state.epoch;
  const content = $("#view-content");
  let result;
  if (view === "discover") {
    result = state.songs.length
      ? cards(state.songs)
      : empty(
          "从一首喜欢的歌开始",
          "搜索酷我或 QQ 的歌曲；推荐歌单将在后续接入。",
        );
    $("#pagination").hidden = !state.hasMore;
  } else if (view === "favorites") {
    const data = await api("/api/favorites");
    result = data.items.length
      ? cards(data.items)
      : empty("还没有收藏", "在搜索结果中收藏歌曲，这里只保存当前用户的记录。");
  } else if (view === "tasks") {
    const data = await api("/api/tasks");
    result = node("div");
    if (!data.items.length)
      result = empty(
        "没有下载任务",
        "从搜索结果选择曲目和音质，任务会持久保存。",
      );
    for (const task of data.items) {
      const c = node("article", undefined, "task-card"),
        head = node("div", undefined, "task-heading");
      head.append(
        node("h3", `${task.entries.length} 首歌曲 · ${task.quality}`),
        node("span", statusNames[task.status] || task.status, "pill"),
      );
      c.append(head);
      for (const e of task.entries) {
        const row = node("div", undefined, "task-entry");
        row.append(
          node("span", e.title),
          node("span", statusNames[e.status] || e.status, "muted"),
        );
        c.append(row);
        if (e.error) c.append(node("p", e.error.message, "error"));
      }
      if (task.last_error)
        c.append(node("p", task.last_error.message, "error"));
      const actions = node("div", undefined, "song-actions");
      for (const [action, label] of [
        ["pause", "暂停"],
        ["resume", "恢复"],
        ["retry", "重试"],
      ]) {
        if (
          (action === "pause" && task.status === "running") ||
          (action === "resume" && task.status === "paused") ||
          (action === "retry" && task.status === "failed")
        )
          actions.append(
            button(label, async () => {
              await api(`/api/tasks/${encodeURIComponent(task.id)}/control`, {
                method: "POST",
                body: JSON.stringify({ action }),
              });
              await loadView();
            }),
          );
      }
      c.append(actions);
      result.append(c);
    }
  } else if (view === "assets") {
    const data = await api("/api/assets");
    result = node("div", undefined, "results");
    if (!data.items.length)
      result = empty(
        "还没有已校验的歌曲",
        "下载完成后会检查实际编码、时长与完整解码，再登记到这里。",
      );
    for (const a of data.items) {
      const c = node("article", undefined, "song-card");
      c.append(
        node("h3", a.title),
        node("p", a.artist),
        node(
          "p",
          `${a.codec.toUpperCase()} · ${Math.round(a.duration_seconds)} 秒 · ${(a.bytes / 1048576).toFixed(1)} MB`,
        ),
        node("p", "音频校验通过 · 飞牛入库尚未接入"),
      );
      const link = node("a", "下载文件");
      link.href = `/api/assets/${encodeURIComponent(a.id)}/file`;
      c.append(link);
      result.append(c);
    }
  } else if (view === "accounts") {
    result = node("div", undefined, "panel");
    result.append(
      node("h3", "平台账号联动待接入"),
      node(
        "p",
        "当前已使用飞牛音乐身份隔离本地收藏与下载。网易云、QQ 与酷我的私人账号推荐、云端收藏和真实收听反馈尚未开放。",
        "muted",
      ),
      node("p", "本地收藏不会自动写入任何云平台。"),
    );
  } else if (view === "injection") {
    const data = await api("/api/admin/injection");
    result = node("div", undefined, "panel");
    result.append(
      node("h3", "官方音乐注入：尚未启用"),
      node("p", data.reason, "muted"),
    );
  }
  if (epoch === state.epoch && view === state.view)
    content.replaceChildren(result);
}
async function restore() {
  try {
    const me = await api("/api/me");
    state.me = me;
    state.csrf = me.csrf_token;
    state.epoch++;
    const favorites = await api("/api/favorites");
    state.favorites = new Set(
      favorites.items.filter((s) => s.track).map((s) => key(s.track)),
    );
    $("#login").hidden = true;
    $("#shell").hidden = false;
    $("#admin-nav").hidden = !me.is_admin;
    $("#user").textContent = me.principal.user_guid;
    await navigate("discover");
  } catch (e) {
    signedOut();
  }
}
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget,
    b = form.querySelector("button");
  b.disabled = true;
  try {
    await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: form.elements.username.value,
        password: form.elements.password.value,
      }),
    });
    form.elements.password.value = "";
    await restore();
  } catch (e) {
    toast(e.message);
  } finally {
    b.disabled = false;
  }
});
$("#logout").addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
    signedOut();
  } catch (e) {
    toast(e.message);
  }
});
for (const b of document.querySelectorAll("nav button"))
  b.addEventListener("click", () =>
    navigate(b.dataset.view).catch((e) => toast(e.message)),
  );
async function search(append = false) {
  const epoch = state.epoch;
  const data = await api(
    `/api/search?provider=${encodeURIComponent(state.provider)}&q=${encodeURIComponent(state.search)}&page=${state.page}`,
  );
  if (epoch !== state.epoch) return;
  state.songs = append ? [...state.songs, ...data.items] : data.items;
  state.hasMore = data.has_more;
  await loadView();
}
$("#search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const b = event.currentTarget.querySelector("button");
  b.disabled = true;
  try {
    state.search = $("#query").value;
    state.provider = $("#provider").value;
    state.page = 1;
    await search();
  } catch (e) {
    toast(e.message);
  } finally {
    b.disabled = false;
  }
});
$("#next-page").addEventListener("click", async () => {
  const b = $("#next-page");
  b.disabled = true;
  state.page++;
  try {
    await search(true);
  } catch (e) {
    state.page--;
    toast(e.message);
  } finally {
    b.disabled = false;
  }
});
setInterval(() => {
  if (state.me && ["tasks", "assets"].includes(state.view))
    loadView().catch((e) => toast(e.message));
}, 5000);
restore();
