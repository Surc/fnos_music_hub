import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { JSDOM } from "jsdom";
import { fixture, apiFixture, song, track } from "./web-fixture.mjs";
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
  });
  dom.window.setInterval = () => 0;
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
  } finally {
    r.close();
  }
});
