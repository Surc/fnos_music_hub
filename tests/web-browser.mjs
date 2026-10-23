// Real Chromium rendering against synthetic, same-origin API fixtures; no platform access.
import assert from "node:assert/strict";
import http from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { chromium } from "playwright";
import { fixture, apiFixture, song, track } from "./web-fixture.mjs";
const files = new Map();
for (const [url, path, type] of [
  ["/", "index.html", "text/html"],
  ["/static/app.js", "app.js", "text/javascript"],
  ["/static/style.css", "style.css", "text/css"],
])
  files.set(url, {
    data: await readFile(new URL("../apps/web/" + path, import.meta.url)),
    type,
  });
let current;
const server = http.createServer(async (req, res) => {
  try {
    if (files.has(req.url)) {
      const f = files.get(req.url);
      res.setHeader("Content-Type", f.type);
      res.setHeader(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
      );
      res.end(f.data);
      return;
    }
    if (req.url.startsWith("/api/")) {
      let body = "";
      for await (const chunk of req) body += chunk;
      const result = await apiFixture(current, req.url, {
        method: req.method,
        body: body || undefined,
        headers: {
          "Idempotency-Key": req.headers["idempotency-key"],
          "X-CSRF-Token": req.headers["x-csrf-token"],
        },
      });
      res.writeHead(result.status, {
        "Content-Type": result.type || "application/json",
      });
      res.end(result.raw || JSON.stringify(result.body));
      return;
    }
    res.writeHead(404);
    res.end();
  } catch (error) {
    res.writeHead(500, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: { message: String(error) } }));
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
await mkdir("test-results", { recursive: true });
const report = {
  scope:
    "real Chromium + synthetic same-origin HTTP API; no real fnOS/music platform/FPK acceptance",
  cases: [],
};
const browser = await chromium.launch({ headless: true });
const sizes = [
  ["pc-landscape", 1440, 900, false],
  ["pc-wide", 1920, 1080, false],
  ["pc-portrait", 900, 1440, false],
  ["pc-tall", 1080, 1920, false],
  ["pc-narrow", 720, 1000, false],
  ["mobile-small", 320, 568, true],
  ["mobile-portrait", 390, 844, true],
  ["mobile-large", 412, 915, true],
  ["mobile-landscape", 844, 390, true],
  ["mobile-landscape-small", 667, 375, true],
];
const layout = async (page) => {
  const result = await page.evaluate(() => ({
    width: innerWidth,
    overflow: document.documentElement.scrollWidth,
    outside: [...document.querySelectorAll("button,input,select")]
      .filter(
        (el) =>
          el.getClientRects().length &&
          !el.closest("dialog:not([open]),[hidden]"),
      )
      .map((el) => ({
        text: el.getAttribute("aria-label") || el.textContent,
        r: el.getBoundingClientRect(),
      }))
      .filter(({ r }) => r.left < -1 || r.right > innerWidth + 1)
      .map(({ text }) => text),
  }));
  assert.ok(
    result.overflow <= result.width + 1,
    `page overflow ${JSON.stringify(result)}`,
  );
  assert.deepEqual(
    result.outside,
    [],
    `control clipped ${JSON.stringify(result)}`,
  );
};
const dialogFits = async (
  page,
  selectors = [
    "#download-dialog",
    "#confirm-download",
    "#download-dialog .dialog-header [data-close]",
  ],
) => {
  const viewport = page.viewportSize();
  for (const selector of selectors) {
    const box = await page.locator(selector).boundingBox();
    assert.ok(box, "dialog element visible");
    assert.ok(
      box.x >= -1 && box.x + box.width <= viewport.width + 1,
      JSON.stringify(box),
    );
    assert.ok(
      box.y >= -1 && box.y + box.height <= viewport.height + 1,
      JSON.stringify({ box, viewport }),
    );
  }
};
try {
  for (const [name, width, height, mobile] of sizes) {
    current = fixture({
      loggedIn: false,
      qqEnabled: true,
      songs: [
        song,
        {
          ...song,
          title: "晴天",
          artist: "周杰伦",
          track: { ...track, id: "228908" },
        },
        { title: "来源中的未知条目", track: null, qualities: [] },
      ],
    });
    const context = await browser.newContext({
      viewport: { width, height },
      isMobile: mobile,
      hasTouch: mobile,
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(origin);
    await page.locator("#login-form").waitFor();
    await layout(page);
    await page.getByLabel("用户名", { exact: true }).fill("synthetic-user");
    await page.getByLabel("密码", { exact: true }).fill("synthetic-password");
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.locator("#shell:not([hidden])").waitFor();
    await layout(page);
    await page
      .getByRole("searchbox", { name: "搜索关键词", exact: true })
      .fill("DAYBREAK'S BELL");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.locator(".song-card").first().waitFor();
    assert.equal(await page.locator(".song-card").count(), 3);
    await layout(page);
    if (
      [
        "pc-landscape",
        "pc-portrait",
        "mobile-portrait",
        "mobile-landscape",
      ].includes(name)
    )
      await page.screenshot({
        path: `test-results/${name}.png`,
        fullPage: true,
      });
    await page.locator("#select-all").check();
    await page.getByRole("button", { name: "下载所选", exact: true }).click();
    await page.locator("#download-quality").selectOption("128kmp3");
    await dialogFits(page);
    await layout(page);
    const before = current.calls.length;
    if (mobile && name === "mobile-portrait") {
      for (const [w, h] of [
        [844, 390],
        [390, 844],
        [390, 360],
        [390, 844],
      ]) {
        await page.setViewportSize({ width: w, height: h });
        await dialogFits(page);
        assert.equal(
          await page.locator("#download-quality").inputValue(),
          "128kmp3",
        );
        assert.equal(
          await page.locator("#selection-count").textContent(),
          "已选 2 首",
        );
      }
      assert.equal(
        current.calls.length,
        before,
        "rotation must not authenticate, reload or submit",
      );
    }
    if (name === "mobile-landscape")
      await page.screenshot({
        path: "test-results/mobile-landscape-confirm.png",
      });
    await page.locator("#confirm-download").click();
    await page.locator(".task-card").waitFor();
    assert.equal(current.manifests.length, 1);
    assert.equal(current.tasks.length, 1);
    assert.equal(current.manifests[0].length, 2);
    await layout(page);
    current.tasks[0].status = "failed";
    current.tasks[0].entries[0].status = "failed";
    current.tasks[0].entries[0].error = {
      code: "region_restricted",
      message: "来源地区限制",
    };
    await page.getByRole("button", { name: "刷新列表", exact: true }).click();
    await page
      .getByText("来源地区限制：歌曲信息已保留，尚无已校验文件。", {
        exact: true,
      })
      .waitFor();
    await page.getByRole("button", { name: "任务详情", exact: true }).click();
    await page.getByText("region_restricted", { exact: true }).waitFor();
    await page.locator("#detail-dialog [data-close]").first().click();
    current.assets = [
      {
        ...song,
        id: "synthetic-asset",
        codec: "mp3",
        format: "mp3",
        bytes: 12000000,
        bitrate: 320000,
        duration_seconds: 252,
        sha256: "a".repeat(64),
        index_status: "unsupported",
        validation: "full_decode",
      },
    ];
    await page.getByRole("tab", { name: "已下载歌曲", exact: true }).click();
    await page.locator(".asset-file-link").waitFor();
    await layout(page);
    await page.getByRole("button", { name: "文件详情", exact: true }).click();
    await page.getByText("完整解码通过", { exact: true }).waitFor();
    await page.locator("#detail-dialog [data-close]").first().click();
    await page
      .getByRole("button", { name: "我的与平台账号", exact: true })
      .click();
    await page.locator("#view-content .account-grid").waitFor();
    await layout(page);
    await page
      .getByRole("button", { name: "扫码登录 QQ", exact: true })
      .click();
    await page.getByAltText("QQ 音乐登录二维码", { exact: true }).waitFor();
    await layout(page);
    const attemptId = current.qqAttempt.id;
    const loginMutations = () =>
      current.calls.filter(
        (c) => c.method === "POST" && c.path.startsWith("/api/accounts/"),
      ).length;
    const beforeRotation = loginMutations();
    if (name === "mobile-portrait") {
      await page.setViewportSize({ width: 844, height: 390 });
      await layout(page);
      await page.setViewportSize({ width, height });
      assert.equal(current.qqAttempt.id, attemptId);
      assert.equal(
        loginMutations(),
        beforeRotation,
        "QR rotation cannot create or bind a second attempt",
      );
    }
    // Periodic status polling may have completed; never recreate the attempt.
    if (
      await page
        .getByRole("button", { name: "检查扫码状态", exact: true })
        .count()
    )
      await page
        .getByRole("button", { name: "检查扫码状态", exact: true })
        .click();
    await page.getByText("待关联 QQ：10001", { exact: true }).waitFor();
    assert.equal(current.qqAccount.state, "unbound");
    await page
      .getByRole("button", { name: "确认关联此 QQ 账号", exact: true })
      .click();
    await page.getByText("已关联 · QQ 10001", { exact: true }).waitFor();
    await page.getByRole("button", { name: "发现", exact: true }).click();
    await page.getByRole("button", { name: "QQ 音乐", exact: true }).click();
    await page.getByRole("tab", { name: "账号推荐歌单", exact: true }).click();
    await page
      .getByRole("heading", { name: "合成推荐歌单", exact: true })
      .waitFor();
    await layout(page);
    if (
      [
        "pc-landscape",
        "pc-portrait",
        "mobile-portrait",
        "mobile-landscape",
      ].includes(name)
    )
      await page.screenshot({
        path: `test-results/qq-${name}.png`,
        fullPage: true,
      });
    await page.getByRole("button", { name: "查看歌单", exact: true }).click();
    await page.getByText(/当前为分页预览，未验证整单完整性/).waitFor();
    await page.locator(".song-card h3").waitFor();
    await layout(page);
    await page.getByRole("button", { name: "下一页歌曲", exact: true }).click();
    await page.getByText(/第 2 页 · 来源总数 205/).waitFor();
    assert.ok(current.calls.some((c) => c.path.includes("dirid=9&page=2")));
    current.snapshotSongs = Array.from({ length: 1000 }, (_, i) => ({
      ...current.qqSongs[0],
      title: `合成快照条目-${i}`,
    }));
    current.snapshotSongs[1] = { ...current.snapshotSongs[0] };
    current.snapshotSongs[2] = {
      track: null,
      title: "来源中的未知条目",
      artist: "",
    };
    current.snapshotSongs[3].title = "LongTitle".repeat(56);
    await page
      .getByRole("button", { name: "回读已保存快照", exact: true })
      .click();
    await page
      .getByRole("button", { name: "生成完整快照", exact: true })
      .click();
    await page
      .getByText("已保存 1000 项，两轮读取一致。", { exact: true })
      .waitFor();
    await layout(page);
    const captureRequests = current.calls.filter((c) =>
      c.path.endsWith("/run"),
    ).length;
    if (mobile && name === "mobile-portrait") {
      await page.setViewportSize({ width: 844, height: 390 });
      await layout(page);
      await page.setViewportSize({ width, height });
      assert.equal(
        current.calls.filter((c) => c.path.endsWith("/run")).length,
        captureRequests,
      );
    }
    await page
      .getByRole("button", { name: "回读已保存快照", exact: true })
      .click();
    await page
      .getByRole("button", { name: "查看快照曲目", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "已保存的完整歌单快照", exact: true })
      .waitFor();
    assert.equal(await page.locator("#detail-body li").count(), 1000);
    assert.ok(
      await page
        .locator("#detail-body")
        .evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
    );
    await page.locator("#detail-body li").last().scrollIntoViewIfNeeded();
    assert.match(
      await page.locator("#detail-body li").last().textContent(),
      /合成快照条目-999/,
    );
    await dialogFits(page, [
      "#detail-dialog",
      "#detail-dialog .dialog-header [data-close]",
      "#detail-dialog .dialog-footer [data-close]",
    ]);
    await layout(page);
    if (
      [
        "pc-landscape",
        "pc-portrait",
        "mobile-portrait",
        "mobile-landscape",
      ].includes(name)
    )
      await page.screenshot({
        path: `test-results/qq-snapshot-${name}.png`,
        fullPage: true,
      });
    await page.getByRole("button", { name: "关闭详情", exact: true }).click();
    assert.equal(
      current.calls.filter((c) => c.path.endsWith("/run")).length,
      1,
    );
    assert.equal(current.tasks.length, 1); // Only the prior Kuwo confirmation created a task.
    await page.getByRole("button", { name: "发现", exact: true }).click();
    await page.getByRole("tab", { name: "猜你喜欢歌曲", exact: true }).click();
    await page.locator(".song-card h3").waitFor();
    assert.equal(
      await page
        .getByRole("button", { name: "下载待接入", exact: true })
        .isDisabled(),
      true,
    );
    await layout(page);
    await page
      .getByRole("button", { name: "我的与平台账号", exact: true })
      .click();
    await page
      .getByRole("button", { name: "解除 QQ 关联", exact: true })
      .click();
    await page.getByText("尚未关联", { exact: true }).waitFor();
    assert.equal(current.qqAccount.state, "unbound");
    await page.getByRole("button", { name: "我的歌单", exact: true }).click();
    await page.getByRole("tab", { name: "已保存快照", exact: true }).click();
    await page
      .getByRole("button", { name: "查看快照曲目", exact: true })
      .click();
    await page.locator("#detail-body li").last().waitFor();
    assert.equal(await page.locator("#detail-body li").count(), 1000);
    await layout(page);
    await page.getByRole("button", { name: "关闭详情", exact: true }).click();
    await page.getByRole("button", { name: "删除记录", exact: true }).click();
    await page.getByRole("button", { name: "确认删除", exact: true }).click();
    await page.getByText("暂无读取记录", { exact: true }).waitFor();
    await page
      .getByRole("button", { name: "我的与平台账号", exact: true })
      .click();
    await page
      .locator("#view-content")
      .getByRole("button", { name: "下载与曲库", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "下载存储", exact: true })
      .waitFor();
    await layout(page);
    await page
      .getByRole("button", { name: "我的与平台账号", exact: true })
      .click();
    await page
      .locator("#view-content")
      .getByRole("button", { name: "飞牛注入", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "官方音乐注入：尚未启用", exact: true })
      .waitFor();
    await layout(page);
    await page.getByRole("button", { name: "我的歌单", exact: true }).click();
    await page.getByRole("tab", { name: "本地收藏", exact: true }).click();
    await page.getByText("还没有本地收藏", { exact: true }).waitFor();
    await layout(page);
    await page.getByRole("button", { name: "退出", exact: true }).click();
    await page.locator("#login:not([hidden])").waitFor();
    assert.equal(await page.locator("#view-content").textContent(), "");
    assert.equal(await page.locator("#target-path").textContent(), "");
    assert.deepEqual(errors, []);
    report.cases.push({
      name,
      width,
      height,
      touch: mobile,
      status: "passed",
      coverage:
        "login/search/unknown metadata/bulk/confirmation/tasks/region details/files/QQ QR confirmation and explicit binding/QQ recommendations and guess songs/QQ playlist page-only details/two-pass snapshot UI/1000 ordered snapshot entries/local snapshot history after unlink/confirmed local deletion/storage/injection/collections/logout/overflow",
    });
    console.log("PASS", name, `${width}x${height}`);
    await context.close();
  }
} finally {
  await writeFile(
    "test-results/browser-report.json",
    JSON.stringify(report, null, 2) + "\n",
  );
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
