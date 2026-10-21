import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { JSDOM } from "jsdom";

const html = await readFile(
  new URL("../apps/web/index.html", import.meta.url),
  "utf8",
);
const script = await readFile(
  new URL("../apps/web/app.js", import.meta.url),
  "utf8",
);
const track = { provider: "kuwo", id_type: "rid", id: "142276943" };
const song = {
  track,
  title: '<img src=x onerror="window.pwned=true">',
  artist: "Fixture artist",
  album: "Fixture",
  duration_seconds: 252,
  qualities: [{ quality: "320kmp3" }],
};
const waitFor = async (predicate) => {
  for (let n = 0; n < 100; n++) {
    if (predicate()) return;
    await new Promise((r) => setTimeout(r, 5));
  }
  throw new Error("UI did not reach expected state");
};

function boot({ isAdmin = true } = {}) {
  const dom = new JSDOM(html, {
    url: "http://localhost/",
    runScripts: "outside-only",
  });
  const calls = [];
  const tasks = [];
  dom.window.setInterval = () => 0;
  dom.window.fetch = async (path, opts = {}) => {
    calls.push({ path, ...opts });
    const value =
      path === "/api/me"
        ? {
            principal: { user_guid: "user-a" },
            csrf_token: "test-csrf",
            is_admin: isAdmin,
            targets: [],
          }
        : path === "/api/favorites"
          ? { items: [] }
          : path.startsWith("/api/search?")
            ? { items: [song], has_more: false }
            : path === "/api/manifests"
              ? { id: "manifest-1" }
              : path === "/api/tasks" && opts.method === "POST"
                ? (tasks.push({
                    id: "task-1",
                    entries: [{ title: "Fixture", status: "running" }],
                    status: "running",
                    quality: "320kmp3",
                  }),
                  tasks[0])
                : path === "/api/tasks"
                  ? { items: tasks }
                  : { ok: true };
    return { ok: true, status: 200, json: async () => structuredClone(value) };
  };
  dom.window.eval(script);
  return { dom, calls, tasks, document: dom.window.document };
}

test("search renders untrusted titles as text and submits only stable references", async () => {
  const rig = boot();
  const { dom, document: d, calls } = rig;
  try {
    await waitFor(() => !d.querySelector("#shell").hidden);
    d.querySelector("#query").value = "DAYBREAK'S BELL";
    d.querySelector("#search-form").dispatchEvent(
      new dom.window.Event("submit", { bubbles: true, cancelable: true }),
    );
    await waitFor(() => d.querySelector(".song-card"));
    assert.equal(d.querySelectorAll("img").length, 0);
    assert.equal(d.querySelector(".song-card h3").textContent, song.title);
    assert.equal(dom.window.pwned, undefined);
    d.querySelector(".song-card .primary").click();
    await waitFor(() =>
      calls.some((c) => c.path === "/api/tasks" && c.method === "POST"),
    );
    const manifest = calls.find((c) => c.path === "/api/manifests");
    assert.deepEqual(JSON.parse(manifest.body), { tracks: [track] });
    const submit = calls.find(
      (c) => c.path === "/api/tasks" && c.method === "POST",
    );
    assert.equal(submit.headers["X-CSRF-Token"], "test-csrf");
    assert.ok(submit.headers["Idempotency-Key"]);
    assert.deepEqual(JSON.parse(submit.body), {
      manifest_id: "manifest-1",
      quality: "320kmp3",
      target_ref: "private",
    });
    assert.equal(dom.window.localStorage.length, 0);
    await waitFor(
      () => d.querySelector("#page-title").textContent === "下载任务",
    );
    d.querySelector("#logout").click();
    await waitFor(() => !d.querySelector("#login").hidden);
    assert.equal(d.querySelector("#view-content").childNodes.length, 0);
  } finally {
    dom.window.close();
  }
});

test("regular users have no injection settings entry", async () => {
  const { dom, document: d } = boot({ isAdmin: false });
  try {
    await waitFor(() => !d.querySelector("#shell").hidden);
    assert.equal(d.querySelector("#admin-nav").hidden, true);
  } finally {
    dom.window.close();
  }
});
