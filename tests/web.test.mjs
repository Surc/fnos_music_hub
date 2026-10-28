import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { JSDOM } from "jsdom";
import { fixture, apiFixture, song, track } from "./web-fixture.mjs";

const action = (r, text) => {
  const b = [...r.d.querySelectorAll("button")].find(
    (b) => b.textContent === text && !b.disabled,
  );
  assert.ok(b, text);
  b.click();
};
const html = await readFile(
  new URL("../apps/web/index.html", import.meta.url),
  "utf8",
);
const script = await readFile(
  new URL("../apps/web/app.js", import.meta.url),
  "utf8",
);
const waitFor = async (predicate) => {
  for (let n = 0; n < 150; n++) {
    if (predicate()) return;
    await new Promise((r) => setTimeout(r, 5));
  }
  throw new Error("UI did not reach expected state");
};
const response = (result) => ({
  ok: result.status < 400,
  status: result.status,
  json: async () => structuredClone(result.body),
});
async function boot(options = {}) {
  const rig = fixture(options);
  const dom = new JSDOM(html, {
    url: "http://localhost/",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const intervals = [];
  dom.window.setInterval = (callback) => intervals.push(callback);
  dom.window.structuredClone = structuredClone;
  dom.window.fetch = async (path, opts) =>
    response(await apiFixture(rig, path, opts));
  dom.window.eval(script);
  const d = dom.window.document;
  const submit = (id) =>
    d
      .querySelector(id)
      .dispatchEvent(
        new dom.window.Event("submit", { bubbles: true, cancelable: true }),
      );
  const click = (s) => {
    const el = d.querySelector(s);
    assert.ok(el, s);
    el.click();
  };
  const search = async () => {
    d.querySelector("#query").value = "DAYBREAK'S BELL";
    submit("#search-form");
    await waitFor(() => d.querySelector(".song-card"));
  };
  if (rig.loggedIn) await waitFor(() => !d.querySelector("#shell").hidden);
  return {
    rig,
    dom,
    d,
    submit,
    click,
    search,
    calls: rig.calls,
    poll: () => intervals.forEach((callback) => callback()),
    close: () => dom.window.close(),
  };
}
test("untrusted metadata stays text; opening confirmation performs no download", async () => {
  const r = await boot({
    songs: [{ ...song, title: '<img src=x onerror="window.pwned=true">' }],
  });
  try {
    await r.search();
    assert.equal(r.d.querySelectorAll("img").length, 0);
    assert.equal(r.dom.window.pwned, undefined);
    assert.equal(
      r.d.querySelector(".song-card h3").textContent,
      r.rig.songs[0].title,
    );
    r.click(".song-card .primary");
    assert.ok(r.d.querySelector("#download-dialog").hasAttribute("open"));
    assert.equal(r.calls.filter((c) => c.method === "POST").length, 0);
    r.submit("#download-form");
    await waitFor(() =>
      r.calls.some((c) => c.path === "/api/tasks" && c.method === "POST"),
    );
    const manifest = r.calls.find((c) => c.path === "/api/manifests");
    assert.deepEqual(JSON.parse(manifest.body), { tracks: [track] });
    const task = r.calls.find(
      (c) => c.path === "/api/tasks" && c.method === "POST",
    );
    assert.equal(task.headers["X-CSRF-Token"], "synthetic-csrf");
    assert.ok(task.headers["Idempotency-Key"]);
    assert.deepEqual(JSON.parse(task.body), {
      manifest_id: "manifest-1",
      quality: "320kmp3",
      target_ref: "private",
    });
    await waitFor(
      () => !r.d.querySelector("#download-dialog").hasAttribute("open"),
    );
    assert.equal(r.d.querySelector("#page-title").textContent, "下载管理");
    assert.equal(r.dom.window.localStorage.length, 0);
  } finally {
    r.close();
  }
});
test("bulk selection preserves displayed order and duplicate occurrences", async () => {
  const other = { ...song, track: { ...track, id: "228908" }, title: "晴天" };
  const r = await boot({ songs: [song, other, song] });
  try {
    await r.search();
    const checks = r.d.querySelectorAll("[data-row]");
    checks[2].click();
    checks[0].click();
    checks[1].click();
    r.click("#download-selected");
    r.submit("#download-form");
    await waitFor(() => r.rig.manifests.length);
    assert.deepEqual(r.rig.manifests[0], [track, other.track, track]);
  } finally {
    r.close();
  }
});
test("quality list exposes source format and size without inventing unknown values", async () => {
  const r = await boot({
    songs: [
      {
        ...song,
        qualities: [
          ...song.qualities,
          { quality: "flac", filename: "lossless.flac", size: 30100000 },
          { quality: "hires", filename: "", size: 0 },
          {
            quality: '<img src=x onerror="window.pwned=true">',
            filename: "unknown.bin",
            size: -1,
          },
        ],
      },
    ],
  });
  try {
    await r.search();
    const row = r.d.querySelector(".song-card");
    assert.equal(
      row.closest('[role="table"]').getAttribute("aria-label"),
      "歌曲列表",
    );
    assert.match(
      row.querySelector('[data-quality="320kmp3"]').textContent,
      /MP3 · 10.1 MB/,
    );
    assert.match(
      row.querySelector('[data-quality="128kmp3"]').textContent,
      /大小未提供/,
    );
    assert.match(
      row.querySelector('[data-quality="flac"]').textContent,
      /SQ · 无损FLAC · 30.1 MB/,
    );
    assert.match(
      row.querySelector('[data-quality="hires"]').textContent,
      /格式未提供 · 大小未提供/,
    );
    assert.equal(row.querySelector(".song-duration").textContent, "4:12");
    assert.equal(r.d.querySelectorAll("img").length, 0);
    assert.equal(r.dom.window.pwned, undefined);
    assert.equal(r.calls.filter((c) => c.method === "POST").length, 0);
  } finally {
    r.close();
  }
});
test("quality sorting is stable, keeps unknown rows last and restores source duplicates", async () => {
  const flac = {
    ...song,
    title: "Lossless",
    qualities: [{ quality: "flac", filename: "a.flac", size: 12 }],
  };
  const low = {
    ...song,
    title: "Standard",
    qualities: [{ quality: "128kmp3" }],
  };
  const r = await boot({
    songs: [
      song,
      { title: "Unknown", track: null, qualities: [] },
      flac,
      low,
      song,
    ],
  });
  const titles = () =>
    [...r.d.querySelectorAll(".song-card h3")].map((e) => e.textContent);
  const sort = (value) => {
    const el = r.d.querySelector("#quality-sort");
    el.value = value;
    el.dispatchEvent(new r.dom.window.Event("change"));
  };
  try {
    await r.search();
    r.click("[data-row]");
    sort("high");
    assert.deepEqual(titles(), [
      "Lossless",
      song.title,
      song.title,
      "Standard",
      "Unknown",
    ]);
    assert.equal(r.d.querySelectorAll("[data-row]:checked").length, 1);
    sort("low");
    assert.deepEqual(titles(), [
      "Standard",
      song.title,
      song.title,
      "Lossless",
      "Unknown",
    ]);
    sort("source");
    assert.deepEqual(titles(), [
      song.title,
      "Unknown",
      "Lossless",
      "Standard",
      song.title,
    ]);
    assert.equal(
      r.calls.filter((c) => c.path.startsWith("/api/search")).length,
      1,
    );
  } finally {
    r.close();
  }
});
test("quality tags filter loaded results; hidden selections never enter the download", async () => {
  const lossless = {
    ...song,
    title: "Lossless",
    track: { ...track, id: "228908" },
    qualities: [{ quality: "flac", filename: "a.flac", size: 1000 }],
  };
  const r = await boot({ songs: [song, lossless, lossless], searchMore: true });
  try {
    await r.search();
    r.click("#select-all");
    r.click('[data-quality="flac"]');
    assert.equal(r.d.querySelector("#quality-filter").value, "flac");
    assert.equal(r.d.querySelectorAll(".song-card").length, 2);
    assert.match(
      r.d.querySelector("#song-result-count").textContent,
      /显示 2 \/ 已加载 3 首 · 可继续加载/,
    );
    assert.match(
      r.d.querySelector("#selection-hidden").textContent,
      /另有 1 首/,
    );
    assert.equal(
      r.d.querySelector("#selection-count").textContent,
      "已选 2 首",
    );
    const before = r.calls.length;
    r.dom.window.dispatchEvent(new r.dom.window.Event("resize"));
    assert.equal(r.d.querySelector("#quality-filter").value, "flac");
    assert.equal(r.calls.length, before);
    r.click("#download-selected");
    assert.equal(r.d.querySelector("#download-quality").value, "flac");
    r.submit("#download-form");
    await waitFor(() => r.rig.manifests.length);
    assert.deepEqual(r.rig.manifests[0], [lossless.track, lossless.track]);
    assert.equal(
      r.calls.filter((c) => c.path.startsWith("/api/search")).length,
      1,
    );
  } finally {
    r.close();
  }
});
test("quality filter survives new pages, reports no matches, and resets on logout", async () => {
  const r = await boot({ searchMore: true });
  try {
    await r.search();
    const filter = r.d.querySelector("#quality-filter");
    filter.value = "128kmp3";
    filter.dispatchEvent(new r.dom.window.Event("change"));
    r.rig.songs = [
      { ...song, title: "Other", qualities: [{ quality: "flac" }] },
    ];
    r.click("#next-page");
    await waitFor(() =>
      r.d
        .querySelector("#song-result-count")
        .textContent.includes("已加载 2 首"),
    );
    assert.equal(filter.value, "128kmp3");
    assert.equal(r.d.querySelectorAll(".song-card").length, 1);
    filter.value = "unknown";
    filter.dispatchEvent(new r.dom.window.Event("change"));
    assert.match(
      r.d.querySelector("#view-content").textContent,
      /没有符合品质的歌曲/,
    );
    assert.equal(r.d.querySelector("#pagination").hidden, false);
    r.click("#logout");
    await waitFor(() => !r.d.querySelector("#login").hidden);
    assert.equal(filter.value, "all");
    assert.equal(filter.options.length, 1);
  } finally {
    r.close();
  }
});
test("window resizing preserves selected tracks, modal fields and request count", async () => {
  const r = await boot();
  try {
    await r.search();
    r.click("[data-row]");
    r.click("#download-selected");
    const q = r.d.querySelector("#download-quality");
    q.value = "128kmp3";
    const before = r.calls.length;
    r.dom.window.innerWidth = 844;
    r.dom.window.innerHeight = 390;
    r.dom.window.dispatchEvent(new r.dom.window.Event("resize"));
    r.dom.window.innerWidth = 390;
    r.dom.window.innerHeight = 844;
    r.dom.window.dispatchEvent(new r.dom.window.Event("resize"));
    assert.equal(q.value, "128kmp3");
    assert.ok(r.d.querySelector("#download-dialog").hasAttribute("open"));
    assert.equal(
      r.d.querySelector("#selection-count").textContent,
      "已选 1 首",
    );
    assert.equal(r.calls.length, before);
    assert.equal(r.d.querySelector("#query").value, "DAYBREAK'S BELL");
  } finally {
    r.close();
  }
});
test("concurrent confirmations create only one manifest and one task", async () => {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const r = await boot({
    hook: async (path) => {
      if (path === "/api/manifests") await gate;
    },
  });
  try {
    await r.search();
    r.click(".song-card .primary");
    r.submit("#download-form");
    r.submit("#download-form");
    await waitFor(() => r.calls.some((c) => c.path === "/api/manifests"));
    release();
    await waitFor(() => r.rig.tasks.length === 1);
    assert.equal(r.calls.filter((c) => c.path === "/api/manifests").length, 1);
    assert.equal(
      r.calls.filter((c) => c.path === "/api/tasks" && c.method === "POST")
        .length,
      1,
    );
  } finally {
    release();
    r.close();
  }
});
test("uncertain task response reuses original body and key even after closing confirmation", async () => {
  let attempts = 0;
  const r = await boot({
    hook: (path, opts) => {
      if (path === "/api/tasks" && opts.method === "POST" && attempts++ === 0)
        throw new Error("lost acknowledgement");
    },
  });
  try {
    await r.search();
    r.click(".song-card .primary");
    r.d.querySelector("#download-quality").value = "128kmp3";
    r.submit("#download-form");
    await waitFor(() => !r.d.querySelector("#download-error").hidden);
    assert.ok(r.d.querySelector("#download-quality").disabled);
    r.click('[data-close="download-dialog"]');
    r.click(".song-card .primary");
    assert.equal(r.d.querySelector("#download-quality").value, "128kmp3");
    r.submit("#download-form");
    await waitFor(() => r.rig.tasks.length === 1);
    const posts = r.calls.filter(
      (c) => c.path === "/api/tasks" && c.method === "POST",
    );
    assert.equal(
      posts[0].headers["Idempotency-Key"],
      posts[1].headers["Idempotency-Key"],
    );
    assert.equal(posts[0].body, posts[1].body);
    assert.equal(r.rig.manifests.length, 1);
  } finally {
    r.close();
  }
});
test("logout clears private content, paths, fields, dialogs and local memory views", async () => {
  const r = await boot();
  try {
    await r.search();
    r.click(".song-card .primary");
    assert.ok(
      r.d.querySelector("#target-path").textContent.includes(r.rig.guid),
    );
    r.click('[data-close="download-dialog"]');
    r.click("#logout");
    await waitFor(() => !r.d.querySelector("#login").hidden);
    assert.equal(r.d.querySelector("#view-content").childNodes.length, 0);
    assert.equal(r.d.querySelector("#target-path").textContent, "");
    assert.equal(r.d.querySelector("#download-summary").textContent, "");
    assert.equal(r.d.querySelector("#query").value, "");
    assert.equal(r.d.querySelectorAll("dialog[open]").length, 0);
    assert.ok(!r.d.body.textContent.includes("/synthetic-music/"));
  } finally {
    r.close();
  }
});
test("a previous user's late 401 cannot log out the next user", async () => {
  let resolveSearch;
  const pending = new Promise((resolve) => {
    resolveSearch = resolve;
  });
  const r = await boot({
    hook: (path) => (path.startsWith("/api/search?") ? pending : undefined),
  });
  try {
    r.d.querySelector("#query").value = "old user query";
    r.submit("#search-form");
    await waitFor(() => r.calls.some((c) => c.path.startsWith("/api/search?")));
    r.click("#logout");
    await waitFor(() => !r.d.querySelector("#login").hidden);
    r.rig.guid = "test-user-b";
    r.d.querySelector('[name="username"]').value = "b";
    r.d.querySelector('[name="password"]').value = "password";
    r.submit("#login-form");
    await waitFor(
      () => r.d.querySelector("#user").textContent === "test-user-b",
    );
    resolveSearch({
      status: 401,
      body: { error: { message: "expired old session" } },
    });
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(r.d.querySelector("#shell").hidden, false);
    assert.equal(r.d.querySelector("#user").textContent, "test-user-b");
    assert.equal(r.d.querySelector("#query").value, "");
  } finally {
    resolveSearch?.({ status: 401, body: {} });
    r.close();
  }
});
test("regular users have no admin settings in My page or direct hidden navigation", async () => {
  const r = await boot({ isAdmin: false });
  try {
    assert.ok(r.d.querySelector("#admin-nav").hidden);
    r.click('[data-view="accounts"]');
    await waitFor(() =>
      r.d.querySelector("#page-title").textContent.includes("平台账号"),
    );
    assert.equal(
      [...r.d.querySelectorAll("#view-content button")].some(
        (b) => b.textContent === "飞牛注入",
      ),
      false,
    );
    r.click('[data-view="injection"]');
    assert.equal(
      r.calls.some((c) => c.path === "/api/admin/injection"),
      false,
    );
    assert.ok(r.d.querySelector("#toast").textContent.includes("管理员"));
  } finally {
    r.close();
  }
});
test("QQ and unknown metadata remain visible without enabled download", async () => {
  const r = await boot({
    songs: [song, { title: "来源中的未知条目", track: null, qualities: [] }],
  });
  try {
    r.click('[data-provider="qq"]');
    await r.search();
    assert.equal(r.d.querySelectorAll(".song-card").length, 2);
    assert.ok(r.d.querySelector(".song-card .primary").disabled);
    assert.equal(r.d.querySelectorAll("[data-row]").length, 0);
    assert.ok(r.d.querySelector('[data-provider="netease"]').disabled);
  } finally {
    r.close();
  }
});
test("no runtime authorization disables search and download without shared fallback", async () => {
  const r = await boot({ capabilities: { search: [], download: [] } });
  try {
    await r.search().catch(() => {});
    assert.equal(
      r.calls.some((c) => c.path.startsWith("/api/search?")),
      false,
    );
    assert.ok(
      [...r.d.querySelectorAll("[data-provider]")].every((b) => b.disabled),
    );
  } finally {
    r.close();
  }
});
test("task states, regional details and filters do not hide failed metadata", async () => {
  const r = await boot({
    tasks: [
      {
        id: "task-region",
        status: "failed",
        quality: "320kmp3",
        entries: [
          {
            ...song,
            status: "failed",
            error: { code: "region_restricted", message: "来源地区限制" },
          },
        ],
      },
      {
        id: "task-unknown",
        status: "attention",
        quality: "320kmp3",
        entries: [{ ...song, status: "outcome_unknown" }],
      },
    ],
  });
  try {
    r.click('[data-view="downloads"]');
    await waitFor(() => r.d.querySelectorAll(".task-card").length === 2);
    const filter = r.d.querySelector("#task-filter");
    filter.value = "failed";
    filter.dispatchEvent(new r.dom.window.Event("change"));
    assert.equal(r.d.querySelectorAll(".task-card").length, 1);
    assert.ok(r.d.querySelector(".task-card").textContent.includes("地区限制"));
    r.click(".task-card .song-actions button");
    assert.ok(
      r.d
        .querySelector("#detail-body")
        .textContent.includes("region_restricted"),
    );
  } finally {
    r.close();
  }
});
test("verified files distinguish stored audio from unsupported fnOS indexing", async () => {
  const r = await boot({
    assets: [
      {
        id: "asset-1",
        ...song,
        codec: "mp3",
        container: "mp3",
        duration_seconds: 252,
        bytes: 12000000,
        bitrate: 320000,
        validation: "full_decode",
        sha256: "a".repeat(64),
        index_status: "unsupported",
      },
    ],
  });
  try {
    r.click('[data-view="downloads"]');
    r.click("#assets-tab");
    await waitFor(() => r.d.querySelector(".asset-file-link"));
    assert.ok(
      r.d.querySelector("#view-content").textContent.includes("音频校验通过"),
    );
    assert.ok(
      r.d
        .querySelector("#view-content")
        .textContent.includes("飞牛入库尚未支持"),
    );
    assert.equal(
      r.d.querySelector(".asset-file-link").getAttribute("href"),
      "/api/assets/asset-1/file",
    );
    action(r, "文件详情");
    assert.ok(
      r.d.querySelector("#detail-body").textContent.includes("mp3 / mp3"),
    );
  } finally {
    r.close();
  }
});

test("QQ QR confirmation is separate from binding; rotation keeps the attempt", async () => {
  const r = await boot({ qqEnabled: true });
  try {
    r.click('[data-view="accounts"]');
    await waitFor(() => r.calls.some((c) => c.path === "/api/accounts"));
    action(r, "扫码登录 QQ");
    await waitFor(() => r.d.querySelector(".qq-login img"));
    assert.equal(r.calls.filter((c) => c.path.endsWith("/bind")).length, 0);
    const path = r.d.querySelector(".qq-login img").getAttribute("src");
    const before = r.calls.length;
    r.dom.window.dispatchEvent(new r.dom.window.Event("resize"));
    assert.equal(r.calls.length, before);
    assert.equal(r.d.querySelector(".qq-login img").getAttribute("src"), path);
    action(r, "检查扫码状态");
    await waitFor(() =>
      r.d.querySelector(".qq-login").textContent.includes("10001"),
    );
    assert.equal(r.calls.filter((c) => c.path.endsWith("/bind")).length, 0);
    action(r, "确认关联此 QQ 账号");
    await waitFor(
      () => !r.d.querySelector("#detail-dialog").hasAttribute("open"),
    );
    assert.match(
      r.d.querySelector(".account-grid").textContent,
      /已关联 · QQ 10001/,
    );
    const bind = r.calls.find((c) => c.path.endsWith("/bind"));
    assert.equal(bind.headers["X-CSRF-Token"], "synthetic-csrf");
    assert.ok(
      !r.calls.some((c) => c.path === "/api/tasks" && c.method === "POST"),
    );
    assert.equal(r.dom.window.localStorage.length, 0);
  } finally {
    r.close();
  }
});

test("QQ unbound recommendations fail visibly without anonymous fallback or fnOS logout", async () => {
  const r = await boot({ qqEnabled: true });
  try {
    r.click('[data-provider="qq"]');
    r.click('[data-discovery="playlists"]');
    await waitFor(() => !r.d.querySelector("#page-error").hidden);
    assert.match(
      r.d.querySelector("#page-error").textContent,
      /请先关联本人 QQ/,
    );
    assert.equal(r.d.querySelector("#shell").hidden, false);
    assert.equal(r.d.querySelectorAll(".song-card").length, 0);
    assert.ok(!r.calls.some((c) => /search|public|popular/.test(c.path)));
  } finally {
    r.close();
  }
});

test("QQ playlists and guess songs stay distinct; detail preserves page-only integrity", async () => {
  const r = await boot({
    qqEnabled: true,
    qqAccount: {
      provider: "qq",
      state: "bound",
      account_ref: "own",
      uin: "10001",
      binding_generation: 2,
      credential_revision: 1,
    },
  });
  try {
    r.click('[data-provider="qq"]');
    r.click('[data-discovery="playlists"]');
    await waitFor(
      () => r.d.querySelector(".song-card h3")?.textContent === "合成推荐歌单",
    );
    action(r, "查看歌单");
    await waitFor(() =>
      r.calls.some(
        (c) => c.path === "/api/catalog/qq/playlists/77?dirid=9&page=1",
      ),
    );
    await waitFor(
      () => r.d.querySelector(".song-card h3")?.textContent === song.title,
    );
    assert.match(
      r.d.querySelector("#view-content").textContent,
      /分页预览，未验证整单完整性/,
    );
    assert.equal(
      [...r.d.querySelectorAll(".song-card .primary")].every((b) => b.disabled),
      true,
    );
    action(r, "下一页歌曲");
    await waitFor(() => r.calls.some((c) => c.path.includes("dirid=9&page=2")));
    action(r, "收藏到本地");
    await waitFor(() =>
      r.calls.some((c) => c.path === "/api/favorites" && c.method === "POST"),
    );
    r.click('[data-view="discover"]');
    r.click('[data-discovery="songs"]');
    await waitFor(
      () => r.d.querySelector(".song-card h3")?.textContent === song.title,
    );
    assert.ok(
      r.calls.some((c) => c.path.includes("recommendations?kind=songs&page=1")),
    );
    assert.match(
      r.d.querySelector("#source-notice").textContent,
      /推荐歌单与猜你喜欢歌曲分开/,
    );
    assert.ok(
      !r.calls.some((c) => c.path === "/api/tasks" && c.method === "POST"),
    );
  } finally {
    r.close();
  }
});

test("unlink clears QQ content and revokes the visible generation explicitly", async () => {
  const r = await boot({
    qqEnabled: true,
    qqAccount: {
      provider: "qq",
      state: "bound",
      account_ref: "own",
      uin: "10001",
      binding_generation: 3,
      credential_revision: 2,
    },
  });
  try {
    r.click('[data-provider="qq"]');
    r.click('[data-discovery="playlists"]');
    await waitFor(() => r.d.querySelector(".song-card"));
    r.click('[data-view="accounts"]');
    await waitFor(() =>
      r.d
        .querySelector(".account-grid")
        .textContent.includes("已关联 · QQ 10001"),
    );
    action(r, "解除 QQ 关联");
    await waitFor(() => r.rig.qqAccount.state === "unbound");
    const request = r.calls.find((c) => c.path.endsWith("/unlink"));
    assert.deepEqual(JSON.parse(request.body), { binding_generation: 3 });
    r.click('[data-view="discover"]');
    await waitFor(() => !r.d.querySelector("#page-error").hidden);
    assert.equal(r.d.querySelectorAll(".song-card").length, 0);
    assert.ok(
      !r.d.querySelector("#view-content").textContent.includes("合成推荐歌单"),
    );
  } finally {
    r.close();
  }
});

test("late QR polling cannot replace a different details dialog", async () => {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const r = await boot({
    qqEnabled: true,
    hook: async (path) => {
      if (path === "/api/accounts/qq/login/synthetic-attempt") {
        await gate;
        return {
          status: 200,
          body: {
            id: "synthetic-attempt",
            status: "confirmed",
            uin: "10001",
            binding_generation: 1,
          },
        };
      }
    },
  });
  try {
    r.click('[data-view="accounts"]');
    await waitFor(() => r.calls.some((c) => c.path === "/api/accounts"));
    action(r, "扫码登录 QQ");
    await waitFor(() => r.d.querySelector(".qq-login img"));
    action(r, "检查扫码状态");
    r.click("#detail-dialog [data-close]");
    assert.equal(r.d.querySelector("#detail-body").textContent, "");
    release();
    await new Promise((resolve) => setTimeout(resolve, 15));
    assert.equal(r.d.querySelector("#detail-body").textContent, "");
    assert.equal(
      r.d.querySelector("#detail-dialog").hasAttribute("open"),
      false,
    );
  } finally {
    release();
    r.close();
  }
});

test("QQ recommendation continuation uses the server cursor", async () => {
  const r = await boot({
    qqEnabled: true,
    qqNextCursor: 35,
    qqAccount: {
      provider: "qq",
      state: "bound",
      account_ref: "own",
      uin: "10001",
      binding_generation: 1,
      credential_revision: 1,
    },
  });
  try {
    r.click('[data-provider="qq"]');
    r.click('[data-discovery="playlists"]');
    await waitFor(() => r.d.querySelector(".song-card"));
    r.click("#next-page");
    await waitFor(() =>
      r.calls.some((c) =>
        c.path.includes("recommendations?kind=playlists&page=2&cursor=35"),
      ),
    );
    assert.ok(!r.calls.some((c) => c.path.includes("cursor=20")));
  } finally {
    r.close();
  }
});

const boundQq = {
  provider: "qq",
  state: "bound",
  account_ref: "own",
  uin: "10001",
  binding_generation: 1,
  credential_revision: 1,
};
async function openQqPlaylist(r) {
  r.click('[data-provider="qq"]');
  r.click('[data-discovery="playlists"]');
  await waitFor(
    () => r.d.querySelector(".song-card h3")?.textContent === "合成推荐歌单",
  );
  action(r, "查看歌单");
  await waitFor(() =>
    [...r.d.querySelectorAll("button")].some(
      (b) => b.textContent === "生成完整快照",
    ),
  );
}
test("QQ capture preserves preview/rotation; immutable snapshot is read-only and recoverable", async () => {
  const r = await boot({ qqEnabled: true, qqAccount: boundQq });
  try {
    await openQqPlaylist(r);
    action(r, "生成完整快照");
    await waitFor(() => r.rig.captures[0]?.complete);
    await waitFor(() =>
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "查看快照曲目",
      ),
    );
    const calls = r.calls.length;
    r.dom.window.dispatchEvent(new r.dom.window.Event("resize"));
    assert.equal(r.calls.length, calls);
    assert.match(r.d.querySelector("#view-content").textContent, /分页预览/);
    action(r, "下一页歌曲");
    await waitFor(() => r.calls.some((c) => c.path.includes("page=2")));
    action(r, "查看快照曲目");
    await waitFor(() =>
      r.d.querySelector("#detail-dialog").hasAttribute("open"),
    );
    assert.match(
      r.d.querySelector("#detail-body").textContent,
      /QQ 下载尚未开放/,
    );
    r.click("#detail-dialog [data-close]");
    action(r, "返回 QQ 歌单");
    await waitFor(
      () => r.d.querySelector(".song-card h3")?.textContent === "合成推荐歌单",
    );
    action(r, "查看歌单");
    await waitFor(() =>
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "回读已保存快照",
      ),
    );
    action(r, "回读已保存快照");
    await waitFor(() =>
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "查看快照曲目",
      ),
    );
    assert.equal(r.calls.filter((c) => c.path.endsWith("/run")).length, 1);
    assert.equal(
      r.calls.filter((c) => c.path === "/api/tasks" && c.method === "POST")
        .length,
      0,
    );
  } finally {
    r.close();
  }
});

test("capture lost run response can be read back without fetching twice", async () => {
  const r = await boot({
    qqEnabled: true,
    qqAccount: boundQq,
    hook: async (path, options, rig) => {
      if (path.endsWith("/run")) {
        Object.assign(rig.captures[0], {
          complete: true,
          status: "complete",
          fetched_count: 1,
          manifest_id: "qq-snapshot",
        });
        throw new Error("lost reply");
      }
    },
  });
  try {
    await openQqPlaylist(r);
    action(r, "生成完整快照");
    await waitFor(() => !r.d.querySelector("#page-error").hidden);
    action(r, "回读已保存快照");
    await waitFor(() =>
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "查看快照曲目",
      ),
    );
    assert.equal(r.calls.filter((c) => c.path.endsWith("/run")).length, 1);
    assert.equal(r.rig.captures.length, 1);
  } finally {
    r.close();
  }
});

test("capture drift remains incomplete and explicit retry reuses its saved handle", async () => {
  let fail = true;
  const r = await boot({
    qqEnabled: true,
    qqAccount: boundQq,
    hook: async (path, options, rig) => {
      if (path.endsWith("/run") && fail) {
        fail = false;
        const capture = {
          ...rig.captures[0],
          status: "incomplete",
          error: { code: "snapshot_changed", message: "歌单发生变化" },
        };
        rig.captures[0] = capture;
        return { status: 200, body: capture };
      }
    },
  });
  try {
    await openQqPlaylist(r);
    action(r, "生成完整快照");
    await waitFor(() =>
      r.d
        .querySelector("#view-content")
        .textContent.includes("尚未完成：歌单发生变化"),
    );
    assert.ok(
      !r.d.querySelector("#view-content").textContent.includes("查看快照曲目"),
    );
    action(r, "从头重试快照");
    await waitFor(() => r.rig.captures[0].complete);
    assert.equal(r.rig.captures.length, 1);
    assert.equal(r.calls.filter((c) => c.path.endsWith("/run")).length, 2);
  } finally {
    r.close();
  }
});

test("late capture response after logout cannot write private state into a new session", async () => {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const r = await boot({
    qqEnabled: true,
    qqAccount: boundQq,
    hook: async (path) => {
      if (path.endsWith("/run")) {
        await gate;
        return {
          status: 200,
          body: {
            complete: true,
            fetched_count: 987,
            manifest_id: "private-old",
          },
        };
      }
    },
  });
  try {
    await openQqPlaylist(r);
    action(r, "生成完整快照");
    await waitFor(() => r.calls.some((c) => c.path.endsWith("/run")));
    r.click("#logout");
    await waitFor(() => r.d.querySelector("#shell").hidden);
    release();
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(r.d.querySelector("#view-content").textContent, "");
    assert.equal(r.d.querySelector("#detail-body").textContent, "");
  } finally {
    release();
    r.close();
  }
});

test("newly completed snapshot remains visible after empty history read", async () => {
  const r = await boot({ qqEnabled: true, qqAccount: boundQq });
  try {
    await openQqPlaylist(r);
    action(r, "回读已保存快照");
    await new Promise((resolve) => setTimeout(resolve, 20));
    action(r, "生成完整快照");
    await waitFor(() =>
      r.d.querySelector("#view-content").textContent.includes("已保存 1 项"),
    );
    assert.ok(
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "查看快照曲目",
      ),
      "completed snapshot must have a view action",
    );
  } finally {
    r.close();
  }
});
test("saved local snapshot remains accessible when live QQ preview fails", async () => {
  const r = await boot({
    qqEnabled: true,
    qqAccount: boundQq,
    hook: (path) => {
      if (
        path.startsWith("/api/catalog/qq/playlists/77?") &&
        path.includes("page=2")
      )
        return {
          status: 503,
          body: {
            error: {
              code: "platform_unavailable",
              message: "synthetic QQ outage",
            },
          },
        };
    },
  });
  try {
    await openQqPlaylist(r);
    action(r, "生成完整快照");
    await waitFor(() =>
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "查看快照曲目",
      ),
    );
    action(r, "下一页歌曲");
    await waitFor(() => !r.d.querySelector("#page-error").hidden);
    await waitFor(() =>
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "下一页歌曲" && !b.disabled,
      ),
    );
    assert.equal(r.rig.captures[0].complete, true);
    assert.ok(
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "查看快照曲目",
      ),
      "local snapshot must remain available during QQ outage",
    );
  } finally {
    r.close();
  }
});

test("local history pages and deletes snapshots while QQ is disabled", async () => {
  const captures = Array.from({ length: 26 }, (_, i) => ({
    id: `saved-${i}`,
    source: { provider: "qq", id: "77", dirid: "9" },
    status: "complete",
    complete: true,
    fetched_count: 1000,
    created_at: "2026-10-23T12:00:00Z",
    manifest_id: "qq-snapshot",
  }));
  const snapshotSongs = Array.from({ length: 1000 }, (_, i) => ({
    ...song,
    title: `原序-${i}`,
  }));
  snapshotSongs[1] = { ...snapshotSongs[0] };
  snapshotSongs[2] = { track: null, title: "来源中的未知条目", artist: "" };
  const r = await boot({ captures, snapshotSongs });
  try {
    r.click('[data-view="collections"]');
    r.click("#snapshot-collection-tab");
    await waitFor(
      () => r.d.querySelectorAll("#view-content .panel").length === 20,
    );
    action(r, "更早的快照");
    await waitFor(
      () => r.d.querySelectorAll("#view-content .panel").length === 26,
    );
    action(r, "查看快照曲目");
    await waitFor(
      () => r.d.querySelectorAll("#detail-body li").length === 1000,
    );
    const rows = [...r.d.querySelectorAll("#detail-body li")];
    assert.equal(rows[0].textContent, rows[1].textContent);
    assert.match(rows[2].textContent, /未知条目/);
    assert.match(rows.at(-1).textContent, /原序-999/);
    r.click("#detail-dialog [data-close]");
    action(r, "删除记录");
    assert.equal(r.calls.filter((c) => c.method === "DELETE").length, 0);
    action(r, "确认删除");
    await waitFor(
      () => r.d.querySelectorAll("#view-content .panel").length === 25,
    );
    assert.equal(r.calls.filter((c) => c.method === "DELETE").length, 1);
    assert.ok(
      !r.calls.some(
        (c) =>
          c.path.startsWith("/api/catalog/qq/") ||
          c.path.endsWith("/run") ||
          c.path === "/api/tasks",
      ),
    );
  } finally {
    r.close();
  }
});

test("late reading history cannot overwrite a completed capture", async () => {
  let finishRun, finishHistory;
  const runGate = new Promise((resolve) => {
    finishRun = resolve;
  });
  const historyGate = new Promise((resolve) => {
    finishHistory = resolve;
  });
  const r = await boot({
    qqEnabled: true,
    qqAccount: boundQq,
    hook: async (path, options, rig) => {
      if (path.endsWith("/run")) {
        rig.captures[0].status = "reading";
        await runGate;
      }
      if (path.includes("/snapshots?") && options.method !== "POST") {
        const items = structuredClone(rig.captures);
        await historyGate;
        return { status: 200, body: { items, next_cursor: null } };
      }
    },
  });
  try {
    await openQqPlaylist(r);
    action(r, "生成完整快照");
    await waitFor(() => r.rig.captures[0]?.status === "reading");
    action(r, "回读已保存快照");
    await waitFor(() =>
      r.calls.some(
        (c) => c.path.includes("/snapshots?") && c.method !== "POST",
      ),
    );
    finishRun();
    await waitFor(() =>
      r.d.querySelector("#view-content").textContent.includes("已保存 1 项"),
    );
    finishHistory();
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.match(r.d.querySelector("#view-content").textContent, /已保存 1 项/);
    assert.ok(
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "重新生成快照" && !b.disabled,
      ),
    );
    assert.equal(r.calls.filter((c) => c.path.endsWith("/run")).length, 1);
  } finally {
    finishRun();
    finishHistory();
    r.close();
  }
});

test("late local history after logout cannot reveal saved snapshots", async () => {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const r = await boot({
    hook: async (path) => {
      if (path === "/api/playlist-captures") {
        await gate;
        return {
          status: 200,
          body: {
            items: [
              {
                id: "private-history",
                source: { id: "secret" },
                complete: true,
              },
            ],
            next_cursor: null,
          },
        };
      }
    },
  });
  try {
    r.click('[data-view="collections"]');
    r.click("#snapshot-collection-tab");
    await waitFor(() =>
      r.calls.some((c) => c.path === "/api/playlist-captures"),
    );
    r.click("#logout");
    await waitFor(() => r.d.querySelector("#shell").hidden);
    release();
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(r.d.querySelector("#view-content").textContent, "");
  } finally {
    release();
    r.close();
  }
});

test("QQ failed next and previous pages preserve the displayed page and retry target", async () => {
  let failPage = 2;
  const r = await boot({
    qqEnabled: true,
    qqAccount: boundQq,
    hook: (path) => {
      if (
        path.includes("/api/catalog/qq/playlists/77?") &&
        path.endsWith(`page=${failPage}`)
      ) {
        failPage = -1;
        return {
          status: 503,
          body: {
            error: {
              code: "platform_unavailable",
              message: "synthetic page failure",
            },
          },
        };
      }
    },
  });
  try {
    await openQqPlaylist(r);
    await waitFor(() =>
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "下一页歌曲" && !b.disabled,
      ),
    );
    action(r, "下一页歌曲");
    await waitFor(() => !r.d.querySelector("#page-error").hidden);
    await waitFor(() =>
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "下一页歌曲" && !b.disabled,
      ),
    );
    assert.ok(
      r.d.querySelector("#view-content").textContent.includes("第 1 页"),
    );
    action(r, "下一页歌曲");
    await waitFor(() =>
      r.d.querySelector("#view-content").textContent.includes("第 2 页"),
    );
    failPage = 1;
    action(r, "上一页歌曲");
    await waitFor(() => !r.d.querySelector("#page-error").hidden);
    await waitFor(() =>
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "上一页歌曲" && !b.disabled,
      ),
    );
    assert.ok(
      r.d.querySelector("#view-content").textContent.includes("第 2 页"),
    );
    action(r, "上一页歌曲");
    await waitFor(() =>
      r.d.querySelector("#view-content").textContent.includes("第 1 页"),
    );
    const pages = r.calls
      .filter((c) => c.path.includes("/api/catalog/qq/playlists/77?"))
      .map((c) => new URL(c.path, "http://localhost").searchParams.get("page"));
    assert.deepEqual(pages, ["1", "2", "2", "1", "1"]);
  } finally {
    r.close();
  }
});

test("QQ recommendation failure retries the same server continuation cursor", async () => {
  let failed = false;
  const r = await boot({
    qqEnabled: true,
    qqAccount: boundQq,
    qqNextCursor: 35,
    hook: (path) => {
      if (!failed && path.includes("recommendations?kind=playlists&page=2")) {
        failed = true;
        return {
          status: 503,
          body: {
            error: {
              code: "platform_unavailable",
              message: "synthetic recommendation failure",
            },
          },
        };
      }
    },
  });
  try {
    r.click('[data-provider="qq"]');
    r.click('[data-discovery="playlists"]');
    await waitFor(() => r.d.querySelector(".song-card"));
    r.click("#next-page");
    await waitFor(() => !r.d.querySelector("#page-error").hidden);
    r.click("#next-page");
    await waitFor(
      () =>
        r.calls.filter((c) =>
          c.path.includes("recommendations?kind=playlists&page=2&cursor=35"),
        ).length === 2,
    );
    assert.ok(
      !r.calls.some((c) =>
        c.path.includes("recommendations?kind=playlists&page=3"),
      ),
    );
  } finally {
    r.close();
  }
});

test("slow download refresh stays single-flight and publishes every completed poll", async () => {
  const pending = [];
  const r = await boot({
    tasks: [
      {
        id: "slow-task",
        status: "running",
        quality: "320kmp3",
        entries: [{ ...song, status: "running" }],
      },
    ],
    hook: (path) =>
      path === "/api/tasks"
        ? new Promise((resolve) => pending.push(resolve))
        : undefined,
  });
  try {
    r.click('[data-view="downloads"]');
    await waitFor(() => pending.length === 1);
    for (let n = 0; n < 5; n++) r.poll();
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(pending.length, 1);
    pending[0]();
    await waitFor(() => r.d.querySelectorAll(".task-card").length === 1);
    r.poll();
    await waitFor(() => pending.length === 2);
    r.poll();
    r.poll();
    assert.equal(pending.length, 2);
    pending[1]();
    await waitFor(
      () => r.calls.filter((c) => c.path === "/api/tasks").length === 2,
    );
  } finally {
    pending.forEach((resolve) => resolve());
    r.close();
  }
});

test("a slow task poll cannot replace a newly selected assets view", async () => {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const r = await boot({
    hook: async (path) => {
      if (path === "/api/tasks") await gate;
    },
  });
  try {
    r.click('[data-view="downloads"]');
    await waitFor(() => r.calls.some((c) => c.path === "/api/tasks"));
    r.click("#assets-tab");
    await waitFor(() => r.calls.some((c) => c.path === "/api/assets"));
    release();
    await new Promise((resolve) => setTimeout(resolve, 15));
    assert.equal(
      r.d.querySelector("#assets-tab").getAttribute("aria-selected"),
      "true",
    );
    assert.equal(r.d.querySelectorAll(".task-card").length, 0);
  } finally {
    release();
    r.close();
  }
});

async function bindNetease(r) {
  r.click('[data-view="accounts"]');
  await waitFor(() => r.d.body.textContent.includes("关联网易账号"));
  action(r, "关联网易账号");
  r.d.querySelector("#netease-cookie").value =
    "MUSIC_U=synthetic-private-cookie";
  action(r, "验证网易账号");
  await waitFor(() => r.d.body.textContent.includes("确认关联此网易账号"));
  assert.equal(
    r.d.body.textContent.includes("synthetic-private-cookie"),
    false,
  );
  assert.equal(r.rig.neAccount.state, "unbound");
  action(r, "确认关联此网易账号");
  await waitFor(() => r.d.body.textContent.includes("解除网易关联"));
}

test("NetEase public catalog is available before binding; duplicate and unknown rows remain read-only", async () => {
  const r = await boot({ neteaseEnabled: true });
  try {
    r.click('[data-provider="netease"]');
    await waitFor(() => r.d.body.textContent.includes("合成网易歌单 1"));
    assert.equal(r.d.querySelector("#search-form").hidden, true);
    assert.equal(r.rig.neAccount.state, "unbound");
    action(r, "查看歌单");
    await waitFor(() => r.d.body.textContent.includes("合成网易歌曲"));
    assert.equal(r.d.querySelectorAll(".song-card").length, 3);
    assert.equal(
      r.d.querySelectorAll(".song-card h3")[0].textContent,
      r.d.querySelectorAll(".song-card h3")[2].textContent,
    );
    assert.ok(
      r.calls.some((c) =>
        c.path.includes("/netease/playlists/88?scope=public"),
      ),
    );
    assert.equal(
      r.calls.some((c) => c.path === "/api/tasks" && c.method === "POST"),
      false,
    );
    assert.equal(r.d.querySelector("#download-selected").disabled, true);
  } finally {
    r.close();
  }
});

test("NetEase binding requires UID confirmation; rotation preserves form and revokes private previews", async () => {
  const r = await boot({ neteaseEnabled: true, qqEnabled: true });
  try {
    await bindNetease(r);
    const original = { ...r.rig.neAccount };
    action(r, "更新网易凭据");
    const input = r.d.querySelector("#netease-cookie");
    input.value = "MUSIC_U=synthetic-new-cookie";
    r.dom.window.dispatchEvent(new r.dom.window.Event("resize"));
    assert.equal(input.value, "MUSIC_U=synthetic-new-cookie");
    action(r, "验证并更新同号凭据");
    await waitFor(() => !r.d.querySelector("#detail-dialog").open);
    assert.equal(
      r.rig.neAccount.binding_generation,
      original.binding_generation,
    );
    assert.equal(
      r.rig.neAccount.credential_revision,
      original.credential_revision + 1,
    );
    assert.equal(r.rig.qqAccount.state, "unbound");
    action(r, "查看网易歌单");
    await waitFor(() => r.d.body.textContent.includes("合成网易歌单 1"));
    assert.ok(
      r.calls.some((c) => c.path.includes("/netease/playlists?scope=account")),
    );
  } finally {
    r.close();
  }
});

test("NetEase failed directory and song pages retry the same page without hiding current content", async () => {
  let fail = true;
  const r = await boot({
    neteaseEnabled: true,
    hook: async (path) => {
      if (path.includes("/netease/playlists?scope=account&page=2") && fail) {
        fail = false;
        return {
          status: 503,
          body: {
            error: {
              code: "platform_unavailable",
              message: "synthetic page failure",
            },
          },
        };
      }
    },
  });
  try {
    await bindNetease(r);
    action(r, "查看网易歌单");
    await waitFor(() => r.d.body.textContent.includes("合成网易歌单 1"));
    action(r, "下一页歌单");
    await waitFor(() => !r.d.querySelector("#page-error").hidden);
    assert.ok(r.d.body.textContent.includes("合成网易歌单 1"));
    await waitFor(() =>
      [...r.d.querySelectorAll("button")].some(
        (b) => b.textContent === "下一页歌单" && !b.disabled,
      ),
    );
    action(r, "下一页歌单");
    await waitFor(() => r.d.body.textContent.includes("合成网易歌单 2"));
    assert.equal(
      r.calls.filter((c) => c.path.includes("scope=account&page=2")).length,
      2,
    );
    action(r, "查看歌单");
    await waitFor(() => r.d.body.textContent.includes("合成网易歌曲"));
    action(r, "下一页歌曲");
    await waitFor(() => r.d.body.textContent.includes("第 2 页"));
    assert.equal(r.d.querySelectorAll(".song-card").length, 3);
  } finally {
    r.close();
  }
});

test("NetEase late account recommendations after unlink cannot repopulate private state", async () => {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const r = await boot({
    neteaseEnabled: true,
    hook: async (path) => {
      if (path.includes("/netease/recommendations?kind=songs")) {
        await gate;
        return {
          status: 200,
          body: {
            provider: "netease",
            scope: "account",
            page: 1,
            items: [{ ...song, title: "forbidden late private song" }],
            has_more: false,
          },
        };
      }
    },
  });
  try {
    await bindNetease(r);
    r.click('[data-view="discover"]');
    r.click('[data-provider="netease"]');
    await waitFor(() => r.d.body.textContent.includes("合成网易歌单 1"));
    r.click('[data-discovery="songs"]');
    await waitFor(() =>
      r.calls.some((c) => c.path.includes("recommendations?kind=songs")),
    );
    r.click('[data-view="accounts"]');
    await waitFor(() => r.d.body.textContent.includes("解除网易关联"));
    action(r, "解除网易关联");
    await waitFor(() => r.rig.neAccount.state === "unbound");
    release();
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(
      r.d.body.textContent.includes("forbidden late private song"),
      false,
    );
    assert.equal(r.rig.neAccount.state, "unbound");
    assert.equal(
      r.calls.some((c) => c.path.includes("recommendations?kind=daily")),
      false,
    );
  } finally {
    release();
    r.close();
  }
});

test("NetEase expired account leaves fnOS signed in and never falls back to public recommendations", async () => {
  const r = await boot({ neteaseEnabled: true });
  try {
    r.click('[data-provider="netease"]');
    await waitFor(() => r.d.body.textContent.includes("合成网易歌单 1"));
    r.click('[data-discovery="playlists"]');
    await waitFor(() => !r.d.querySelector("#page-error").hidden);
    assert.equal(r.d.querySelector("#shell").hidden, false);
    assert.equal(r.d.body.textContent.includes("合成网易歌单 1"), false);
    assert.equal(
      r.calls.filter((c) => c.path.includes("netease/playlists?scope=public"))
        .length,
      1,
    );
  } finally {
    r.close();
  }
});

test("closing NetEase verification discards its late response without reopening details", async () => {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const r = await boot({
    neteaseEnabled: true,
    hook: async (path) => {
      if (path === "/api/accounts/netease/login") await gate;
    },
  });
  try {
    r.click('[data-view="accounts"]');
    await waitFor(() => r.d.body.textContent.includes("关联网易账号"));
    action(r, "关联网易账号");
    r.d.querySelector("#netease-cookie").value = "MUSIC_U=synthetic";
    action(r, "验证网易账号");
    await waitFor(() =>
      r.calls.some((c) => c.path === "/api/accounts/netease/login"),
    );
    r.click("#detail-dialog [data-close]");
    release();
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(r.d.querySelector("#detail-dialog").open, false);
    assert.equal(r.d.body.textContent.includes("确认关联此网易账号"), false);
  } finally {
    release();
    r.close();
  }
});
