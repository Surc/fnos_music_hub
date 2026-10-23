const $ = (s) => document.querySelector(s);
const providers = { netease: "网易云音乐", qq: "QQ 音乐", kuwo: "酷我音乐" };
const qualities = {
  "320kmp3": "MP3 · 320 kbps",
  "128kmp3": "MP3 · 128 kbps",
  flac: "FLAC · 无损",
  hires: "Hi-Res · 高解析",
};
const statusNames = {
  queued: "待提交",
  submitting: "正在接单",
  running: "下载中",
  paused: "已暂停",
  completed: "校验完成",
  failed: "失败",
  attention: "需要核对",
  outcome_unknown: "结果未知",
};
const titles = {
  discover: ["发现", "先找到喜欢的歌曲，再决定收藏与下载。"],
  collections: ["我的歌单", "本地收藏属于当前飞牛用户，平台歌单独立管理。"],
  downloads: ["下载管理", "任务、音频校验和飞牛入库各有自己的状态。"],
  accounts: ["我的与平台账号", "你的平台账号、下载目标与个人空间。"],
  storage: ["下载与曲库", "管理员设置 · 文件保存与音乐库索引分别管理。"],
  injection: ["飞牛注入", "管理员设置 · 独立于歌单与下载管理。"],
};
const state = {
  me: null,
  csrf: "",
  epoch: 0,
  load: 0,
  searchRequest: 0,
  view: "discover",
  downloadTab: "tasks",
  provider: "kuwo",
  search: "",
  page: 0,
  rows: [],
  hasMore: false,
  searched: false,
  searchBusy: false,
  favorites: [],
  tasks: [],
  assets: [],
  injection: null,
  qqAccount: null,
  qqLogin: null,
  qqBusy: false,
  qqDialog: false,
  discovery: "search",
  collectionTab: "local",
  personal: null,
  cloudPlaylists: null,
  playlist: null,
  selected: { discover: new Set(), collections: new Set() },
  drafts: new Map(),
  download: null,
  submitting: false,
  lastFocus: null,
};
class StaleRequest extends Error {}
const guard = (epoch) => {
  if (epoch !== state.epoch) throw new StaleRequest();
};
const key = (track) =>
  JSON.stringify([track.provider, track.id_type, track.id]);
const capability = (name, provider) =>
  Array.isArray(state.me?.capabilities?.[name]) &&
  state.me.capabilities[name].includes(provider);
const targetName = (id) => (id === "private" ? "我的下载 · 私有目录" : id);
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("#toast").hidden = true), 5500);
}
function report(error) {
  if (!(error instanceof StaleRequest))
    toast(error.message || "请求失败，请稍后重试");
}
function button(text, action, className = "quiet") {
  const el = node("button", text, className);
  el.type = "button";
  el.addEventListener("click", async () => {
    if (el.disabled) return;
    el.disabled = true;
    try {
      await action();
    } catch (e) {
      report(e);
    } finally {
      el.disabled = false;
    }
  });
  return el;
}
function empty(title, description) {
  const el = node("div", undefined, "empty");
  el.append(node("strong", title), node("span", description));
  return el;
}
function badge(text, warning = false) {
  return node("span", text, warning ? "pill warning" : "pill");
}
function details(entries) {
  const dl = node("dl", undefined, "detail-grid");
  for (const [label, value] of entries)
    dl.append(node("dt", label), node("dd", String(value ?? "未知")));
  return dl;
}
function panel(title, description) {
  const el = node("section", undefined, "panel");
  el.append(node("h2", title));
  if (description) el.append(node("p", description, "small muted"));
  return el;
}
function closeDialog(id, force = false) {
  if (id === "download-dialog" && state.submitting && !force) return;
  const el = $("#" + id);
  if (typeof el.close === "function") el.close();
  else el.removeAttribute("open");
  if (id === "download-dialog") {
    state.download = null;
    $("#download-tracks").replaceChildren();
    $("#download-error").textContent = "";
  }
  if (id === "detail-dialog") {
    state.qqDialog = false;
    $("#detail-body").replaceChildren();
  }
  if (state.lastFocus?.isConnected && !force) state.lastFocus.focus();
}
function showDialog(id) {
  state.lastFocus = document.activeElement;
  const el = $("#" + id);
  if (typeof el.showModal === "function") el.showModal();
  else el.setAttribute("open", "");
}
function showDetails(title, body) {
  state.qqDialog = false;
  $("#detail-title").textContent = title;
  $("#detail-body").replaceChildren(body);
  showDialog("detail-dialog");
}
function signedOut() {
  state.epoch++;
  state.load++;
  state.searchRequest++;
  state.me = null;
  state.csrf = "";
  state.rows = [];
  state.favorites = [];
  state.tasks = [];
  state.assets = [];
  state.injection = null;
  state.qqAccount = null;
  state.qqLogin = null;
  state.qqBusy = false;
  state.qqDialog = false;
  state.personal = null;
  state.cloudPlaylists = null;
  state.playlist = null;
  state.discovery = "search";
  state.collectionTab = "local";
  state.selected.discover.clear();
  state.selected.collections.clear();
  state.drafts.clear();
  state.submitting = false;
  state.searchBusy = false;
  state.search = "";
  state.page = 0;
  state.searched = false;
  state.hasMore = false;
  closeDialog("download-dialog", true);
  closeDialog("detail-dialog", true);
  $("#shell").hidden = true;
  $("#login").hidden = false;
  $("#admin-nav").hidden = true;
  $("#view-content").replaceChildren();
  $("#user").textContent = "";
  $("#query").value = "";
  $("#asset-filter").value = "";
  $("#task-filter").value = "all";
  $("#download-summary").textContent = "";
  $("#target-path").textContent = "";
  $("#download-quality").replaceChildren();
  $("#download-target").replaceChildren();
  $("#page-error span").textContent = "";
  $("#page-status").textContent = "";
  $("#toast").textContent = "";
  state.lastFocus = null;
  $("#page-status").hidden = true;
  $("#page-error").hidden = true;
  $("#toast").hidden = true;
  $("#login-form").elements.password.value = "";
}
async function api(path, options = {}) {
  const epoch = state.epoch;
  let response;
  try {
    response = await fetch(path, {
      ...options,
      credentials: "same-origin",
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(state.csrf ? { "X-CSRF-Token": state.csrf } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    guard(epoch);
    throw new Error("连接失败，请检查服务后重试");
  }
  let data;
  try {
    data = await response.json();
  } catch {
    guard(epoch);
    throw new Error("服务返回了无法识别的结果，请稍后核对");
  }
  guard(epoch);
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") {
      signedOut();
      $("#login-error").textContent = "会话已失效，请重新登录";
      $("#login-error").hidden = false;
      throw new StaleRequest();
    }
    const error = new Error(data.error?.message || "请求失败，请稍后重试");
    error.code = data.error?.code;
    throw error;
  }
  return data;
}
function qualityList(song) {
  return Object.keys(qualities).filter((q) =>
    (song.qualities || []).some((item) => item.quality === q),
  );
}
function downloadable(song) {
  return Boolean(
    song.track &&
      capability("download", song.track.provider) &&
      qualityList(song).length &&
      Number(song.duration_seconds) > 0 &&
      (state.me?.targets || []).some((t) => t.id === "private"),
  );
}
function visibleRows() {
  if (state.view === "collections") {
    const songs =
      state.collectionTab === "qq"
        ? state.playlist?.data?.items || []
        : state.favorites;
    return songs.map((song, i) => ({ id: "collection:" + i, song }));
  }
  if (state.discovery === "songs")
    return (state.personal?.items || []).map((song, i) => ({
      id: "recommend:" + i,
      song,
    }));
  return state.discovery === "search" ? state.rows : [];
}
function selection() {
  return state.selected[state.view];
}
function updateSelection() {
  const rows = ["discover", "collections"].includes(state.view)
    ? visibleRows()
    : [];
  const eligible = rows.filter((r) => downloadable(r.song));
  const selected = selection();
  const count = selected
    ? eligible.filter((r) => selected.has(r.id)).length
    : 0;
  $("#selection-bar").hidden = !eligible.length;
  $("#selection-count").textContent = `已选 ${count} 首`;
  $("#download-selected").disabled = !count;
  $("#select-all").checked = Boolean(
    eligible.length && count === eligible.length,
  );
  $("#select-all").indeterminate = count > 0 && count < eligible.length;
}
function songCards(rows) {
  const grid = node("div", undefined, "results");
  for (const { song, id } of rows) {
    const card = node("article", undefined, "song-card");
    const head = node("div", undefined, "song-heading");
    head.append(
      node(
        "span",
        providers[song.track?.provider] || "来源未知",
        "song-source",
      ),
    );
    if (downloadable(song)) {
      const label = node("label", undefined, "select-song");
      const check = node("input");
      check.type = "checkbox";
      check.dataset.row = id;
      check.checked = selection()?.has(id) || false;
      check.setAttribute("aria-label", `选择 ${song.title}`);
      const selected = selection();
      check.addEventListener("change", () => {
        if (check.checked) selected.add(id);
        else selected.delete(id);
        updateSelection();
      });
      label.append(node("span", "选择"), check);
      head.append(label);
    }
    card.append(
      head,
      node("h3", song.title || "来源中的未知条目"),
      node("p", song.artist || "歌手信息未知"),
      node(
        "p",
        [
          song.album,
          song.duration_seconds
            ? `${Math.round(song.duration_seconds)} 秒`
            : "时长未知",
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
      state.favorites.some((s) => s.track && key(s.track) === key(song.track))
        ? "取消本地收藏"
        : "收藏到本地",
      async () => {
        const enabled = !state.favorites.some(
          (s) => s.track && key(s.track) === key(song.track),
        );
        await api("/api/favorites", {
          method: "POST",
          body: JSON.stringify({ track: song.track, enabled }),
        });
        if (enabled) state.favorites.push(song);
        else
          state.favorites = state.favorites.filter(
            (s) => !s.track || key(s.track) !== key(song.track),
          );
        // A changed collection changes its row positions; clear only that explicit edit's selection.
        state.selected.collections.clear();
        render();
      },
    );
    const download = button(
      capability("download", song.track.provider) ? "下载" : "下载待接入",
      () => openDownload([song]),
      "primary",
    );
    download.disabled = !downloadable(song);
    actions.append(favorite, download);
    card.append(actions);
    if (!qualityList(song).length)
      card.append(
        node("p", "暂未提供可用音质，仍可浏览和本地收藏。", "small muted"),
      );
    grid.append(card);
  }
  return grid;
}
function taskCards() {
  const rows = state.tasks.filter(
    (t) =>
      $("#task-filter").value === "all" || t.status === $("#task-filter").value,
  );
  if (!rows.length)
    return empty(
      "没有符合条件的任务",
      "搜索歌曲后选择音质与保存位置，任务会保存在服务端。",
    );
  const list = node("div");
  for (const task of rows) {
    const c = node("article", undefined, "task-card");
    const head = node("div", undefined, "task-heading");
    const label = node("div");
    label.append(
      node(
        "h3",
        task.entries.length === 1
          ? task.entries[0].title
          : `${task.entries.length} 首歌曲`,
      ),
      node("p", `${qualities[task.quality] || task.quality} · 我的下载`),
    );
    head.append(
      label,
      badge(
        statusNames[task.status] || task.status,
        ["failed", "attention"].includes(task.status),
      ),
    );
    c.append(head);
    for (const entry of task.entries) {
      const row = node("div", undefined, "task-entry");
      row.append(
        node("span", entry.title),
        node("span", statusNames[entry.status] || entry.status, "muted"),
      );
      c.append(row);
      if (entry.error)
        c.append(
          node(
            "p",
            entry.error.code === "region_restricted"
              ? "来源地区限制：歌曲信息已保留，尚无已校验文件。"
              : entry.error.message,
            "error",
          ),
        );
    }
    if (task.last_error) c.append(node("p", task.last_error.message, "error"));
    const actions = node("div", undefined, "song-actions");
    actions.append(
      button("任务详情", () => {
        const body = node("div");
        body.append(
          details([
            ["任务 ID", task.id],
            ["任务状态", statusNames[task.status] || task.status],
            ["请求音质", qualities[task.quality] || task.quality],
            ["创建时间", task.created_at || "未知"],
          ]),
        );
        for (const entry of task.entries) {
          const p = panel(entry.title);
          p.append(
            details([
              ["来源", providers[entry.track?.provider] || "未知"],
              [
                "曲目 ID",
                entry.track
                  ? `${entry.track.id_type}: ${entry.track.id}`
                  : "未知",
              ],
              ["条目状态", statusNames[entry.status] || entry.status],
              ["失败分类", entry.error?.code || "无"],
              ["说明", entry.error?.message || "无"],
            ]),
          );
          body.append(p);
        }
        showDetails("任务详情", body);
      }),
    );
    for (const [action, label, expected] of [
      ["pause", "暂停", "running"],
      ["resume", "继续下载", "paused"],
      ["retry", "重试", "failed"],
    ]) {
      if (task.status === expected)
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
    if (task.status === "attention")
      c.append(
        node(
          "p",
          "接单结果需要核对，系统会回读已有任务；请勿重复创建。",
          "notice",
        ),
      );
    c.append(actions);
    list.append(c);
  }
  return list;
}
const indexNames = {
  unsupported: "飞牛入库尚未支持",
  pending: "等待飞牛入库",
  indexed: "已入库",
  failed: "飞牛入库失败",
};
function assetCards() {
  const query = $("#asset-filter").value.trim().toLocaleLowerCase();
  const items = state.assets.filter((a) =>
    `${a.title} ${a.artist}`.toLocaleLowerCase().includes(query),
  );
  if (!items.length)
    return empty(
      "还没有符合条件的文件",
      "这里只登记已经通过完整音频校验的文件，下载和入库分别显示。",
    );
  const grid = node("div", undefined, "results");
  for (const asset of items) {
    const c = node("article", undefined, "song-card");
    c.append(
      node(
        "div",
        providers[asset.track?.provider] || "来源未知",
        "song-source",
      ),
      node("h3", asset.title),
      node("p", asset.artist || "歌手信息未知"),
      node(
        "p",
        `${String(asset.codec || "未知").toUpperCase()} · ${Math.round(asset.duration_seconds || 0)} 秒 · ${((asset.bytes || 0) / 1048576).toFixed(1)} MB`,
      ),
    );
    const statuses = node("div", undefined, "status-list");
    statuses.append(
      badge("下载完成"),
      badge("音频校验通过"),
      badge(
        indexNames[asset.index_status] || "入库状态未知",
        asset.index_status !== "indexed",
      ),
    );
    c.append(statuses);
    const actions = node("div", undefined, "song-actions");
    const link = node("a", "下载文件", "asset-file-link");
    link.href = `/api/assets/${encodeURIComponent(asset.id)}/file`;
    actions.append(
      link,
      button("文件详情", () =>
        showDetails(
          "文件详情",
          details([
            ["歌曲", asset.title],
            ["歌手", asset.artist],
            ["实际来源", providers[asset.track?.provider] || "未知"],
            [
              "格式 / 编码",
              `${asset.format || "未知"} / ${asset.codec || "未知"}`,
            ],
            ["时长", `${asset.duration_seconds} 秒`],
            [
              "码率",
              asset.bitrate
                ? `${Math.round(asset.bitrate / 1000)} kbps`
                : "未知",
            ],
            ["字节", asset.bytes],
            ["SHA256", asset.sha256],
            ["保存目标", targetName("private")],
            [
              "音频校验",
              asset.validation === "full_decode"
                ? "完整解码通过"
                : asset.validation || "通过",
            ],
            ["飞牛入库", indexNames[asset.index_status] || "未知"],
          ]),
        ),
      ),
    );
    c.append(actions);
    grid.append(c);
  }
  return grid;
}
function accountsPage() {
  const result = node("div");
  const identity = panel("当前飞牛用户", state.me.principal.user_guid);
  identity.append(
    node(
      "p",
      "本地收藏和下载属于当前用户；平台账号绑定后再读取本人的私人内容。",
      "small muted",
    ),
  );
  result.append(identity);
  const grid = node("div", undefined, "account-grid");
  for (const [provider, name] of Object.entries(providers)) {
    const p = panel(name);
    const caps = node("div", undefined, "capability-list");
    caps.append(
      badge(capability("search", provider) ? "公共搜索" : "搜索待接入"),
      badge(capability("download", provider) ? "下载已接入" : "下载待接入"),
    );
    p.append(
      caps,
      node(
        "p",
        provider === "kuwo"
          ? "公共模式；私人账号、歌单推荐尚未开放。"
          : provider === "qq" && capability("cloud_accounts", "qq")
            ? "本人创建歌单、账号推荐歌单和猜你喜欢可读取；下载与云端写入尚未开放。"
            : "本人账号绑定、私人歌单和推荐尚未开放。",
        "small muted",
      ),
    );
    if (provider === "qq" && capability("cloud_accounts", "qq")) {
      const account = state.qqAccount;
      const names = {
        bound: "已关联",
        expired: "平台登录已失效",
        binding_changed: "Hot 账号已变化，请重新关联",
        unbound: "尚未关联",
      };
      p.append(
        node(
          "p",
          `${names[account?.state] || "正在读取账号状态"}${account?.uin ? " · QQ " + account.uin : ""}`,
          "break-text",
        ),
      );
      p.append(
        node(
          "p",
          "扫码完成后核对 QQ 账号，再确认关联。解除关联会撤销本中心的私人读取授权。",
          "small muted",
        ),
      );
      if (account?.state === "bound") {
        p.append(
          button("解除 QQ 关联", unlinkQq),
          button("查看 QQ 歌单", async () => {
            state.collectionTab = "qq";
            state.playlist = null;
            await navigate("collections");
          }),
        );
      } else {
        p.append(
          button(
            state.qqLogin ? "继续 QQ 登录" : "扫码登录 QQ",
            async () => {
              if (state.qqLogin) {
                state.qqDialog = true;
                renderQqLogin();
                showDialog("detail-dialog");
              } else await startQqLogin("qr");
            },
            "primary",
          ),
        );
        p.append(button("关联已有 Hot 登录", () => startQqLogin("existing")));
        if (account?.binding_generation > 0)
          p.append(button("重置登录尝试", unlinkQq));
      }
    } else {
      const bind = node("button", "绑定账号 · 待接入");
      bind.disabled = true;
      p.append(bind);
    }
    grid.append(p);
  }
  result.append(grid);
  const preferences = panel("我的下载与反馈");
  preferences.append(
    node(
      "p",
      "本地收藏不会自动写入云平台；自动播放反馈保持关闭。",
      "small muted",
    ),
  );
  for (const target of state.me.targets || [])
    preferences.append(
      node(
        "p",
        `${targetName(target.id)}：${target.path}`,
        "small muted break-text",
      ),
    );
  if (!(state.me.targets || []).length)
    preferences.append(
      node("p", "尚未配置本人的下载目标，请联系管理员。", "small muted"),
    );
  if (state.me.is_admin) {
    const actions = node("div", undefined, "settings-links");
    actions.append(
      button("下载与曲库", () => navigate("storage")),
      button("飞牛注入", () => navigate("injection")),
    );
    preferences.append(actions);
  }
  preferences.append(button("退出当前飞牛账号", logout));
  result.append(preferences);
  return result;
}

function clearQqContent() {
  state.personal = null;
  state.cloudPlaylists = null;
  state.playlist = null;
}
async function loadAccounts() {
  const data = await api("/api/accounts");
  const next = data.items?.find((a) => a.provider === "qq") || null;
  if (
    state.qqAccount &&
    (next?.account_ref !== state.qqAccount.account_ref ||
      next?.binding_generation !== state.qqAccount.binding_generation)
  )
    clearQqContent();
  state.qqAccount = next;
}
async function unlinkQq() {
  if (!state.qqAccount) return;
  const result = await api("/api/accounts/qq/unlink", {
    method: "POST",
    body: JSON.stringify({
      binding_generation: state.qqAccount.binding_generation,
    }),
  });
  state.qqAccount = result;
  state.qqLogin = null;
  clearQqContent();
  state.load++;
  closeDialog("detail-dialog");
  render();
  if (
    (state.view === "discover" && state.discovery !== "search") ||
    (state.view === "collections" && state.collectionTab === "qq")
  )
    pageError("QQ 关联已解除，请先重新关联本人账号。");
}
async function startQqLogin(kind) {
  state.qqLogin = await api("/api/accounts/qq/login", {
    method: "POST",
    body: JSON.stringify({ kind }),
  });
  await loadAccounts();
  state.qqDialog = true;
  renderQqLogin();
  showDialog("detail-dialog");
  render();
}
function renderQqLogin(message) {
  const attempt = state.qqLogin;
  if (!attempt || !state.qqDialog) return;
  const result = node("div", undefined, "qq-login");
  const labels = {
    waiting: "请用 QQ 音乐扫码",
    scanned: "已扫码，请在手机上确认",
    confirmed: "扫码已确认，请核对账号",
    bound: "关联完成",
    expired: "二维码已过期",
    canceled: "已取消扫码",
    error: "扫码结果无法确认，请重新开始",
  };
  result.append(node("p", labels[attempt.status] || "正在确认登录"));
  if (["waiting", "scanned"].includes(attempt.status) && attempt.qr_path) {
    const image = node("img");
    image.src = attempt.qr_path;
    image.alt = "QQ 音乐登录二维码";
    image.width = 220;
    image.height = 220;
    result.append(image);
  }
  if (attempt.uin)
    result.append(node("p", "待关联 QQ：" + attempt.uin, "break-text"));
  result.append(
    node("p", "只有点击确认关联后，本中心才读取该账号的歌单和推荐。", "notice"),
  );
  if (message) result.append(node("p", message, "error"));
  if (["waiting", "scanned"].includes(attempt.status))
    result.append(button("检查扫码状态", pollQqLogin));
  if (attempt.status === "confirmed")
    result.append(
      button(
        "确认关联此 QQ 账号",
        async () => {
          const current = state.qqLogin;
          state.qqAccount = await api(
            `/api/accounts/qq/login/${encodeURIComponent(current.id)}/bind`,
            { method: "POST" },
          );
          state.qqLogin = null;
          clearQqContent();
          closeDialog("detail-dialog");
          render();
          toast("QQ 账号已关联，可读取本人歌单和账号推荐。");
        },
        "primary",
      ),
    );
  result.append(button("取消本次关联", unlinkQq));
  $("#detail-title").textContent = "关联本人 QQ 账号";
  $("#detail-body").replaceChildren(result);
}
async function pollQqLogin() {
  if (!state.qqLogin || state.qqBusy) return;
  state.qqBusy = true;
  const epoch = state.epoch,
    id = state.qqLogin.id;
  try {
    const data = await api(`/api/accounts/qq/login/${encodeURIComponent(id)}`);
    if (state.qqLogin?.id !== id) return;
    state.qqLogin = data;
    renderQqLogin();
  } catch (error) {
    if (!(error instanceof StaleRequest) && state.qqLogin?.id === id)
      renderQqLogin(error.message);
  } finally {
    if (epoch === state.epoch) state.qqBusy = false;
  }
}
function playlistCards(data) {
  if (!data?.items?.length)
    return empty(
      "暂无歌单",
      "关联本人 QQ 后读取平台返回的歌单；不会改用公共热门。",
    );
  const grid = node("div", undefined, "results");
  for (const item of data.items) {
    const card = node("article", undefined, "song-card");
    card.append(
      badge("QQ · 本人账号请求"),
      node("h3", item.title || "未知歌单"),
    );
    if (item.playlist) {
      card.append(
        node(
          "p",
          `${item.creator || "创建者未知"} · ${item.song_count || 0} 首`,
        ),
      );
      card.append(
        button("查看歌单", async () => {
          state.playlist = {
            ref: item.playlist,
            title: item.title,
            page: 1,
            data: null,
          };
          state.collectionTab = "qq";
          await navigate("collections");
        }),
      );
    } else
      card.append(node("p", "来源条目无法识别，保留原位置。", "small muted"));
    grid.append(card);
  }
  return grid;
}
function capturePath(current) {
  return `/api/catalog/qq/playlists/${encodeURIComponent(current.ref.id)}/snapshots?dirid=${encodeURIComponent(current.ref.dirid)}`;
}
async function capturePlaylist(current) {
  if (current.captureBusy) return;
  const epoch = state.epoch;
  current.captureBusy = true;
  if (current.capture?.complete) {
    current.capture = null;
    current.captureKey = null;
  }
  current.captureKey ||= crypto.randomUUID();
  render();
  try {
    if (!current.capture) {
      const capture = await api(capturePath(current), {
        method: "POST",
        headers: { "Idempotency-Key": current.captureKey },
      });
      guard(epoch);
      if (state.playlist !== current) return;
      current.capture = capture;
    }
    const capture = await api(
      `/api/playlist-captures/${current.capture.id}/run`,
      { method: "POST" },
    );
    guard(epoch);
    if (state.playlist === current) current.capture = capture;
  } catch (e) {
    if (
      !(e instanceof StaleRequest) &&
      state.playlist === current &&
      epoch === state.epoch
    ) {
      if (["binding_changed", "platform_auth_required"].includes(e.code))
        clearQqContent();
      pageError(e.message + "；可回读已保存快照状态，不会触发下载。");
    }
  } finally {
    if (epoch === state.epoch && state.playlist === current) {
      current.captureBusy = false;
      render();
    }
  }
}
async function captureHistory(current) {
  const data = await api(capturePath(current));
  if (state.playlist !== current) return;
  current.captures = data.items;
  if (current.capture)
    current.capture =
      data.items.find((c) => c.id === current.capture.id) || current.capture;
  render();
}
async function showSnapshot(current, capture) {
  const manifest = await api(
    `/api/manifests/${encodeURIComponent(capture.manifest_id)}`,
  );
  if (state.playlist !== current || state.view !== "collections") return;
  const box = node("div");
  box.append(
    node(
      "p",
      `${manifest.fetched_count} 项 · ${manifest.captured_at}。两轮读取一致；平台未提供原子快照保证。QQ 下载尚未开放。`,
      "notice",
    ),
  );
  const rows = node("ol");
  for (const entry of manifest.ordered_entries)
    rows.append(
      node(
        "li",
        `${entry.song.title || "未知条目"} · ${entry.song.artist || "歌手未知"}`,
      ),
    );
  box.append(rows);
  showDetails("已保存的完整歌单快照", box);
}
function capturePanel(current) {
  const box = node("section", undefined, "notice");
  box.append(
    node(
      "p",
      "完整快照最多 1000 项；顺序、重复和未知条目均保留。读取两轮核对后保存，不会开始下载。",
    ),
  );
  const actions = node("div", undefined, "song-actions");
  const create = button(
    current.capture?.complete
      ? "重新生成快照"
      : current.capture
        ? "从头重试快照"
        : "生成完整快照",
    () => capturePlaylist(current),
  );
  create.disabled = Boolean(
    current.captureBusy ||
      current.capture?.status === "reading" ||
      (current.capture?.retry_at || 0) * 1000 > Date.now(),
  );
  actions.append(
    create,
    button("回读已保存快照", () => captureHistory(current)),
  );
  box.append(actions);
  if (current.captureBusy)
    box.append(
      node("p", "正在核对两轮完整歌单… 可继续翻页，刷新后可回读状态。"),
    );
  else if (current.capture)
    box.append(
      node(
        "p",
        current.capture.complete
          ? `已保存 ${current.capture.fetched_count} 项，两轮读取一致。`
          : `尚未完成：${current.capture.error?.message || current.capture.status}。${current.capture.retry_at > Date.now() / 1000 ? "限流等待中，稍后回读状态再重试。" : ""}`,
      ),
    );
  for (const capture of current.captures ||
    (current.capture?.complete ? [current.capture] : [])) {
    const row = node("div", undefined, "song-actions");
    row.append(
      node(
        "span",
        `${capture.created_at} · ${capture.complete ? "完整快照" : "未完成"} · ${capture.fetched_count} 项`,
      ),
    );
    row.append(
      button(capture.complete ? "查看快照曲目" : "选择此记录", () => {
        if (capture.complete) return showSnapshot(current, capture);
        current.capture = capture;
        render();
      }),
    );
    box.append(row);
  }
  return box;
}
function qqCollectionPage() {
  if (!state.playlist) {
    const box = node("div");
    box.append(
      node("p", "QQ 本人创建的歌单；云端收藏/订阅另行接入。", "notice"),
      playlistCards(state.cloudPlaylists),
    );
    return box;
  }
  const current = state.playlist;
  const box = node("div");
  box.append(
    button("返回 QQ 歌单", async () => {
      state.playlist = null;
      render();
      await loadView();
    }),
    node("h2", current.title),
  );
  box.append(
    node(
      "p",
      `第 ${current.page} 页 · 来源总数 ${current.data?.source_total ?? "待读取"}。当前为分页预览，未验证整单完整性。`,
      "notice",
    ),
  );
  box.append(capturePanel(current));
  box.append(
    current.data?.items?.length
      ? songCards(visibleRows())
      : empty("当前页暂无歌曲", "未知条目保留，歌曲下载不会在读取歌单时触发。"),
  );
  const actions = node("div", undefined, "song-actions");
  if (current.page > 1)
    actions.append(
      button("上一页歌曲", async () => {
        current.page--;
        await loadView();
      }),
    );
  if (current.data?.has_more)
    actions.append(
      button("下一页歌曲", async () => {
        current.page++;
        await loadView();
      }),
    );
  box.append(actions);
  return box;
}
function storagePage() {
  const result = node("div");
  const storage = panel(
    "下载存储",
    "当前只读展示本人的授权目标，目录变更由部署配置管理。",
  );
  for (const target of state.me.targets || [])
    storage.append(
      details([
        ["授权目标", targetName(target.id)],
        ["保存目录", target.path],
        ["所属用户", state.me.principal.user_guid],
      ]),
    );
  if (!(state.me.targets || []).length)
    storage.append(node("p", "当前用户尚无下载目标。", "muted"));
  const library = panel(
    "飞牛音乐库",
    "音乐库是独立的索引目标，下载到目录不代表已经入库。",
  );
  library.append(badge("自动入库尚未支持", true));
  result.append(storage, library);
  return result;
}
function injectionPage() {
  const p = panel(
    "官方音乐注入：尚未启用",
    state.injection?.reason || "当前尚未开放官方音乐注入。",
  );
  p.append(
    badge("未接管 Socket"),
    node("p", "注入关闭时，独立音乐中心仍可认证、搜索和管理下载。", "notice"),
  );
  const b = node("button", "启用注入 · 待实现", "primary");
  b.disabled = true;
  p.append(b);
  return p;
}
function render() {
  if (!state.me) return;
  const view = state.view;
  const content = $("#view-content");
  let result;
  for (const b of document.querySelectorAll("[data-view]")) {
    if (
      b.dataset.view === view ||
      (["storage", "injection"].includes(view) && b.dataset.view === "accounts")
    )
      b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  }
  $("#page-title").textContent = titles[view][0];
  $("#page-description").textContent = titles[view][1];
  $("#discover-controls").hidden = view !== "discover";
  $("#collection-tabs").hidden = view !== "collections";
  $("#qq-collection-tab").disabled = !capability("account_playlists", "qq");
  $("#qq-collection-tab").setAttribute(
    "aria-selected",
    String(state.collectionTab === "qq"),
  );
  $("#local-collection-tab").setAttribute(
    "aria-selected",
    String(state.collectionTab === "local"),
  );
  $("#discovery-tabs").hidden =
    state.provider !== "qq" || !capability("recommendations", "qq");
  for (const b of document.querySelectorAll("[data-discovery]"))
    b.setAttribute(
      "aria-selected",
      String(b.dataset.discovery === state.discovery),
    );
  $("#download-tabs").hidden = view !== "downloads";
  $("#download-filters").hidden = view !== "downloads";
  $("#task-filter-label").hidden = state.downloadTab !== "tasks";
  $("#asset-filter-label").hidden = state.downloadTab !== "assets";
  for (const b of document.querySelectorAll("[data-download-tab]"))
    b.setAttribute(
      "aria-selected",
      String(b.dataset.downloadTab === state.downloadTab),
    );
  for (const b of document.querySelectorAll("[data-provider]")) {
    b.disabled = !capability("search", b.dataset.provider);
    b.setAttribute(
      "aria-pressed",
      String(b.dataset.provider === state.provider),
    );
  }
  for (const opt of $("#provider").options)
    opt.disabled = !capability("search", opt.value);
  $("#provider").value = state.provider;
  $("#source-notice").textContent = capability("search", state.provider)
    ? state.discovery === "search"
      ? `${providers[state.provider]} · 公共歌曲搜索。本地收藏可独立使用；平台私人内容需要本人账号关联。`
      : "QQ · 本人账号请求。推荐歌单与猜你喜欢歌曲分开显示；个性化效果待与来源客户端对照。不会自动上报播放反馈。"
    : "当前用户尚未配置可用的搜索引擎，请联系管理员。";
  $("#pagination").hidden =
    view !== "discover" ||
    !(state.discovery === "search" ? state.hasMore : state.personal?.has_more);
  $("#view-content").removeAttribute("role");
  $("#view-content").removeAttribute("aria-labelledby");
  if (view === "discover")
    result = state.rows.length
      ? songCards(state.rows)
      : empty(
          state.searched ? "没有找到歌曲" : "从一首喜欢的歌开始",
          state.searched
            ? "可以调整关键词或切换来源；下载失败不会使已经找到的元数据消失。"
            : "搜索酷我或 QQ 的歌曲，选择收藏与下载。个人推荐和歌单功能将在后续接入。",
        );
  if (view === "collections") {
    result =
      state.collectionTab === "qq"
        ? qqCollectionPage()
        : state.favorites.length
          ? songCards(visibleRows())
          : empty(
              "还没有本地收藏",
              "在搜索结果中收藏歌曲，这里仅保存当前用户的记录。",
            );
    content.setAttribute("role", "tabpanel");
    content.setAttribute(
      "aria-labelledby",
      state.collectionTab === "qq"
        ? "qq-collection-tab"
        : "local-collection-tab",
    );
  }
  if (view === "discover" && state.discovery !== "search")
    result =
      state.discovery === "playlists"
        ? playlistCards(state.personal)
        : state.personal?.items?.length
          ? songCards(visibleRows())
          : empty(
              "暂无猜你喜欢歌曲",
              "先关联本人 QQ 账号，再读取本次推荐。此入口不是每日推荐歌曲。",
            );
  if (view === "downloads") {
    result = state.downloadTab === "tasks" ? taskCards() : assetCards();
    content.setAttribute("role", "tabpanel");
    content.setAttribute("aria-labelledby", state.downloadTab + "-tab");
  }
  if (view === "accounts") result = accountsPage();
  if (view === "storage") result = storagePage();
  if (view === "injection") result = injectionPage();
  content.replaceChildren(result);
  updateSelection();
}
function pageError(message) {
  $("#page-error span").textContent = message;
  $("#page-error").hidden = false;
}
async function navigate(view) {
  if (!titles[view] || !state.me) return;
  if (["storage", "injection"].includes(view) && !state.me.is_admin) {
    toast("只有管理员可以访问此设置");
    return;
  }
  state.view = view;
  state.load++;
  $("#page-error").hidden = true;
  $("#page-status").hidden = true;
  render();
  await loadView();
}
async function loadView(quiet = false) {
  if (!state.me) return;
  const view = state.view,
    tab = state.downloadTab,
    seq = ++state.load,
    epoch = state.epoch;
  const currentPlaylist = state.playlist;
  const path =
    view === "discover" && state.discovery !== "search"
      ? `/api/catalog/qq/recommendations?kind=${state.discovery}&page=${state.personal?.page || 1}&cursor=${state.personal?.cursor || 0}`
      : view === "accounts" && capability("cloud_accounts", "qq")
        ? "/api/accounts"
        : view === "collections"
          ? state.collectionTab === "local"
            ? "/api/favorites"
            : currentPlaylist
              ? `/api/catalog/qq/playlists/${encodeURIComponent(currentPlaylist.ref.id)}?dirid=${encodeURIComponent(currentPlaylist.ref.dirid)}&page=${currentPlaylist.page}`
              : "/api/catalog/qq/playlists"
          : view === "downloads"
            ? "/api/" + tab
            : view === "injection"
              ? "/api/admin/injection"
              : null;
  if (!path) return;
  if (!quiet) {
    $("#page-status").textContent = "正在刷新…";
    $("#page-status").hidden = false;
  }
  try {
    const data = await api(path);
    guard(epoch);
    if (seq !== state.load || view !== state.view || tab !== state.downloadTab)
      return;
    if (view === "accounts") {
      const next = data.items?.find((a) => a.provider === "qq") || null;
      if (
        state.qqAccount &&
        (next?.account_ref !== state.qqAccount.account_ref ||
          next?.binding_generation !== state.qqAccount.binding_generation)
      )
        clearQqContent();
      state.qqAccount = next;
    } else if (view === "discover") state.personal = data;
    else if (view === "collections" && state.collectionTab === "qq") {
      if (currentPlaylist) currentPlaylist.data = data;
      else state.cloudPlaylists = data;
    } else if (view === "collections") {
      state.favorites = data.items;
      state.selected.collections.clear();
    } else if (view === "downloads") state[tab] = data.items;
    else state.injection = data;
    $("#page-error").hidden = true;
    render();
  } catch (e) {
    if (
      !(e instanceof StaleRequest) &&
      epoch === state.epoch &&
      seq === state.load
    ) {
      if (path.startsWith("/api/catalog/qq/")) {
        clearQqContent();
        render();
      }
      pageError(e.message);
    }
  } finally {
    if (epoch === state.epoch && seq === state.load)
      $("#page-status").hidden = true;
  }
}
function openDownload(songs) {
  if (state.download || !songs.length || songs.some((s) => !downloadable(s)))
    return;
  const available = Object.keys(qualities).filter((q) =>
    songs.every((song) => qualityList(song).includes(q)),
  );
  if (!available.length) {
    toast("所选歌曲没有共同可用音质，请分别下载");
    return;
  }
  state.download = { songs: structuredClone(songs), epoch: state.epoch };
  $("#download-summary").textContent =
    `${songs.length} 首歌曲 · ${[...new Set(songs.map((s) => providers[s.track.provider]))].join("、")}`;
  $("#download-tracks").replaceChildren(
    ...songs
      .slice(0, 5)
      .map((s) => node("p", `${s.title} · ${s.artist || "歌手未知"}`)),
  );
  if (songs.length > 5)
    $("#download-tracks").append(
      node("p", `另有 ${songs.length - 5} 首，按当前选择顺序下载`),
    );
  $("#download-quality").replaceChildren(
    ...available.map((q) => {
      const option = node("option", qualities[q]);
      option.value = q;
      return option;
    }),
  );
  $("#download-target").replaceChildren(
    ...state.me.targets
      .filter((t) => t.id === "private")
      .map((t) => {
        const option = node("option", targetName(t.id));
        option.value = t.id;
        return option;
      }),
  );
  $("#target-path").textContent =
    `保存目录：${state.me.targets.find((t) => t.id === $("#download-target").value)?.path || "未知"}`;
  $("#download-error").hidden = true;
  $("#confirm-download").textContent = "创建下载任务";
  const pending = state.drafts.get(JSON.stringify(songs.map((s) => s.track)));
  for (const el of $("#download-form").querySelectorAll("button,select"))
    el.disabled = false;
  if (pending) {
    if (!available.includes(pending.quality)) {
      const option = node("option", qualities[pending.quality]);
      option.value = pending.quality;
      $("#download-quality").append(option);
    }
    $("#download-quality").value = pending.quality;
    $("#download-target").value = pending.target;
    $("#download-quality").disabled = true;
    $("#download-target").disabled = true;
    $("#download-error").textContent =
      "上次接单结果尚未确认，将核对原音质与原任务。";
    $("#download-error").hidden = false;
    $("#confirm-download").textContent = "核对并继续";
  }
  showDialog("download-dialog");
}
async function submitDownload(event) {
  event.preventDefault();
  if (!state.download || state.submitting) return;
  const snapshot = state.download;
  const epoch = snapshot.epoch;
  const quality = $("#download-quality").value;
  const target = $("#download-target").value;
  const tracks = snapshot.songs.map((s) => s.track);
  const draftKey = JSON.stringify(tracks);
  let draft = state.drafts.get(draftKey);
  if (!draft) {
    draft = { idem: crypto.randomUUID(), manifest_id: null, quality, target };
    state.drafts.set(draftKey, draft);
  }
  state.submitting = true;
  for (const el of $("#download-form").querySelectorAll("button,select"))
    el.disabled = true;
  $("#download-error").hidden = true;
  try {
    guard(epoch);
    if (!draft.manifest_id) {
      const manifest = await api("/api/manifests", {
        method: "POST",
        body: JSON.stringify({ tracks }),
      });
      guard(epoch);
      draft.manifest_id = manifest.id;
    }
    const task = await api("/api/tasks", {
      method: "POST",
      headers: { "Idempotency-Key": draft.idem },
      body: JSON.stringify({
        manifest_id: draft.manifest_id,
        quality: draft.quality,
        target_ref: draft.target,
      }),
    });
    guard(epoch);
    state.drafts.delete(draftKey);
    state.selected.discover.clear();
    state.selected.collections.clear();
    state.submitting = false;
    closeDialog("download-dialog");
    state.downloadTab = "tasks";
    await navigate("downloads");
    guard(epoch);
    toast(`下载任务已保存：${task.entries?.length || tracks.length} 首`);
  } catch (e) {
    if (!(e instanceof StaleRequest) && epoch === state.epoch) {
      $("#download-error").textContent =
        e.message + "。再次确认将使用同一接单标识核对任务。";
      $("#download-error").hidden = false;
      $("#confirm-download").textContent = "核对并继续";
    }
  } finally {
    if (epoch === state.epoch) {
      state.submitting = false;
      for (const el of $("#download-form").querySelectorAll("button,select"))
        el.disabled = false;
      if (state.drafts.has(draftKey)) {
        $("#download-quality").disabled = true;
        $("#download-target").disabled = true;
      }
    }
  }
}
async function search(append = false) {
  if (state.searchBusy || !capability("search", state.provider)) return;
  const epoch = state.epoch,
    request = ++state.searchRequest,
    provider = state.provider,
    query = state.search,
    page = append ? state.page + 1 : 1;
  state.searchBusy = true;
  $("#search-submit").disabled = true;
  $("#next-page").disabled = true;
  $("#page-error").hidden = true;
  $("#page-status").textContent = "正在搜索歌曲…";
  $("#page-status").hidden = false;
  try {
    const data = await api(
      `/api/search?provider=${encodeURIComponent(provider)}&q=${encodeURIComponent(query)}&page=${page}`,
    );
    guard(epoch);
    if (request !== state.searchRequest || provider !== state.provider) return;
    if (!append) {
      state.rows = [];
      state.selected.discover.clear();
    }
    const offset = state.rows.length;
    state.rows.push(
      ...data.items.map((song, i) => ({
        song,
        id: `${request}:${offset + i}`,
      })),
    );
    state.hasMore = data.has_more === true;
    state.page = page;
    state.searched = true;
    if (state.view === "discover") render();
  } catch (e) {
    if (
      !(e instanceof StaleRequest) &&
      epoch === state.epoch &&
      request === state.searchRequest
    )
      pageError(e.message);
  } finally {
    if (epoch === state.epoch && request === state.searchRequest) {
      state.searchBusy = false;
      $("#search-submit").disabled = false;
      $("#next-page").disabled = false;
      $("#page-status").hidden = true;
    }
  }
}
function chooseProvider(provider) {
  if (!capability("search", provider) || provider === state.provider) return;
  state.provider = provider;
  state.discovery = "search";
  state.personal = null;
  state.load++;
  state.searchRequest++;
  state.searchBusy = false;
  state.rows = [];
  state.page = 0;
  state.hasMore = false;
  state.searched = false;
  state.selected.discover.clear();
  $("#search-submit").disabled = false;
  $("#next-page").disabled = false;
  $("#page-status").hidden = true;
  $("#page-error").hidden = true;
  render();
}
async function restore() {
  const epoch = ++state.epoch;
  try {
    const me = await api("/api/me");
    guard(epoch);
    state.me = me;
    state.csrf = me.csrf_token;
    state.provider = me.capabilities?.search?.[0] || "kuwo";
    const favorites = await api("/api/favorites");
    guard(epoch);
    state.favorites = favorites.items;
    $("#login").hidden = true;
    $("#shell").hidden = false;
    $("#admin-nav").hidden = !me.is_admin;
    $("#user").textContent = me.principal.user_guid;
    $("#login-error").hidden = true;
    await navigate("discover");
  } catch (e) {
    if (!(e instanceof StaleRequest) && epoch === state.epoch) {
      signedOut();
      $("#login-error").textContent = e.message;
      $("#login-error").hidden = false;
    }
  }
}
async function logout() {
  await api("/api/auth/logout", { method: "POST", body: "{}" });
  signedOut();
}
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget,
    b = form.querySelector("button");
  b.disabled = true;
  $("#login-error").hidden = true;
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
    if (!(e instanceof StaleRequest)) {
      $("#login-error").textContent = e.message;
      $("#login-error").hidden = false;
    }
  } finally {
    b.disabled = false;
  }
});
$("#logout").addEventListener("click", async () => {
  const b = $("#logout");
  b.disabled = true;
  try {
    await logout();
  } catch (e) {
    report(e);
  } finally {
    b.disabled = false;
  }
});
for (const b of document.querySelectorAll("[data-view]"))
  b.addEventListener("click", () => navigate(b.dataset.view).catch(report));
for (const b of document.querySelectorAll("[data-provider]"))
  b.addEventListener("click", () => chooseProvider(b.dataset.provider));
$("#provider").addEventListener("change", (event) =>
  chooseProvider(event.target.value),
);
$("#search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.searchBusy) return;
  state.search = $("#query").value.trim();
  if (!state.search) return;
  state.discovery = "search";
  state.personal = null;
  await navigate("discover");
  await search();
});
$("#next-page").addEventListener("click", () => {
  if (state.discovery === "search") search(true);
  else {
    state.personal = {
      ...state.personal,
      page: (state.personal?.page || 1) + 1,
      cursor: state.personal.next_cursor,
    };
    loadView();
  }
});
for (const b of document.querySelectorAll("[data-discovery]"))
  b.addEventListener("click", async () => {
    if (b.dataset.discovery === state.discovery) return;
    state.discovery = b.dataset.discovery;
    state.personal = null;
    state.selected.discover.clear();
    render();
    await loadView();
  });
for (const [id, collectionTab] of [
  ["local-collection-tab", "local"],
  ["qq-collection-tab", "qq"],
])
  $("#" + id).addEventListener("click", async () => {
    state.collectionTab = collectionTab;
    state.playlist = null;
    state.selected.collections.clear();
    render();
    await loadView();
  });
$("#select-all").addEventListener("change", (event) => {
  const set = selection();
  for (const row of visibleRows().filter((r) => downloadable(r.song))) {
    if (event.target.checked) set.add(row.id);
    else set.delete(row.id);
  }
  for (const check of document.querySelectorAll("[data-row]"))
    check.checked = set.has(check.dataset.row);
  updateSelection();
});
$("#download-selected").addEventListener("click", () =>
  openDownload(
    visibleRows()
      .filter((r) => selection()?.has(r.id))
      .map((r) => r.song),
  ),
);
$("#download-form").addEventListener("submit", submitDownload);
for (const b of document.querySelectorAll("[data-close]"))
  b.addEventListener("click", () => closeDialog(b.dataset.close));
$("#download-dialog").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeDialog("download-dialog");
});
$("#detail-dialog").addEventListener("close", () => {
  if (!$("#detail-dialog").open) {
    state.qqDialog = false;
    $("#detail-body").replaceChildren();
  }
});
for (const id of ["collection-tabs", "discovery-tabs"])
  $("#" + id).addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const tabs = [...$("#" + id).querySelectorAll('[role="tab"]')].filter(
      (b) => !b.disabled,
    );
    if (!tabs.length) return;
    event.preventDefault();
    const index = tabs.indexOf(document.activeElement);
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (index + (event.key === "ArrowLeft" ? -1 : 1) + tabs.length) %
            tabs.length;
    tabs[next].focus();
    tabs[next].click();
  });
for (const b of document.querySelectorAll("[data-download-tab]"))
  b.addEventListener("click", async () => {
    state.downloadTab = b.dataset.downloadTab;
    render();
    await loadView();
  });
$("#download-tabs").addEventListener("keydown", (event) => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const next =
    event.key === "Home"
      ? $("#tasks-tab")
      : event.key === "End"
        ? $("#assets-tab")
        : state.downloadTab === "tasks"
          ? $("#assets-tab")
          : $("#tasks-tab");
  next.focus();
  next.click();
});
$("#task-filter").addEventListener("change", render);
$("#asset-filter").addEventListener("input", render);
$("#retry-page").addEventListener("click", () =>
  state.view === "discover" && state.discovery === "search"
    ? search()
    : loadView(),
);
$("#refresh-list").addEventListener("click", () => loadView());
function viewportChanged() {
  const viewport = window.visualViewport;
  document.documentElement.style.setProperty(
    "--visual-height",
    `${viewport?.height || window.innerHeight}px`,
  );
  document.documentElement.style.setProperty(
    "--visual-top",
    `${viewport?.offsetTop || 0}px`,
  );
}
window.addEventListener("resize", viewportChanged);
window.visualViewport?.addEventListener("resize", viewportChanged);
window.visualViewport?.addEventListener("scroll", viewportChanged);
viewportChanged();
setInterval(() => {
  if (
    state.me &&
    state.qqDialog &&
    $("#detail-dialog").open &&
    !document.hidden &&
    ["waiting", "scanned"].includes(state.qqLogin?.status)
  )
    pollQqLogin();
  if (
    state.me &&
    state.view === "downloads" &&
    !document.hidden &&
    !document.querySelector("dialog[open]") &&
    !$("#view-content").contains(document.activeElement)
  )
    loadView(true);
}, 5000);
restore();
