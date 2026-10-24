// Synthetic API boundary for frontend tests. Never included in the application.
export const track = { provider: "kuwo", id_type: "rid", id: "142276943" };
export const song = {
  track,
  title: "DAYBREAK'S BELL",
  artist: "L’Arc〜en〜Ciel",
  album: "KISS",
  duration_seconds: 252,
  qualities: [{ quality: "320kmp3" }, { quality: "128kmp3" }],
};
export function fixture(options = {}) {
  const result = {
    loggedIn: true,
    isAdmin: true,
    guid: "test-user-a",
    songs: [structuredClone(song)],
    favorites: [],
    tasks: [],
    assets: [],
    manifests: [],
    captures: [],
    calls: [],
    searchMore: false,
    qqAccount: {
      provider: "qq",
      state: "unbound",
      binding_generation: 0,
      credential_revision: 0,
      account_ref: null,
      uin: null,
    },
    qqAttempt: null,
    neAccount: {
      provider: "netease",
      state: "unbound",
      binding_generation: 0,
      credential_revision: 0,
      account_ref: null,
      uid: null,
    },
    neAttempt: null,
    qqPoll: "confirmed",
    qqRecommendations: [
      {
        playlist: { provider: "qq", id: "77", dirid: "9" },
        title: "合成推荐歌单",
        creator: "测试创建者",
        song_count: 205,
      },
    ],
    qqSongs: [
      {
        ...structuredClone(song),
        track: { provider: "qq", id_type: "songmid", id: "syntheticMid" },
        qualities: [],
      },
    ],
    capabilities: {
      search: ["kuwo", "qq"],
      download: ["kuwo"],
      local_favorites: true,
      recommendations: false,
      cloud_accounts: false,
      injection: false,
      indexing: false,
      playback_feedback: false,
    },
    ...options,
  };
  if (options.qqEnabled) {
    result.capabilities = {
      ...result.capabilities,
      recommendations: ["qq"],
      cloud_accounts: ["qq"],
      account_playlists: ["qq"],
    };
  }
  if (options.neteaseEnabled) {
    for (const name of [
      "recommendations",
      "cloud_accounts",
      "account_playlists",
      "public_playlists",
    ])
      result.capabilities[name] = [
        ...(Array.isArray(result.capabilities[name])
          ? result.capabilities[name]
          : []),
        "netease",
      ];
  }
  return result;
}
export async function apiFixture(rig, path, options = {}) {
  const method = options.method || "GET";
  const body = options.body ? JSON.parse(options.body) : {};
  rig.calls.push({ path, method, ...options });
  const url = new URL(path, "http://localhost");
  const ok = (value) => ({ status: 200, body: value });
  if (rig.hook) {
    const override = await rig.hook(path, options, rig);
    if (override !== undefined) return override;
  }
  if (url.pathname === "/api/auth/login") {
    rig.loggedIn = true;
    return ok({ ok: true });
  }
  if (!rig.loggedIn)
    return {
      status: 401,
      body: { error: { code: "auth_required", message: "请先登录" } },
    };
  if (url.pathname === "/api/auth/logout") {
    rig.loggedIn = false;
    return ok({ ok: true });
  }
  if (url.pathname === "/api/me")
    return ok({
      principal: { instance_id: "synthetic-nas", user_guid: rig.guid },
      csrf_token: "synthetic-csrf",
      is_admin: rig.isAdmin,
      targets: [{ id: "private", path: "/synthetic-music/" + rig.guid }],
      capabilities: rig.capabilities,
    });
  if (url.pathname === "/api/accounts")
    return ok({
      enabled: true,
      items: [rig.qqAccount, ...(rig.neteaseEnabled ? [rig.neAccount] : [])],
    });
  if (url.pathname === "/api/accounts/netease/login") {
    rig.neAccount.binding_generation++;
    rig.neAttempt = {
      id: "synthetic-ne-attempt",
      uid: "20001",
      nickname: "合成网易账号",
      status: "confirmed",
    };
    return { status: 201, body: rig.neAttempt };
  }
  if (
    url.pathname === "/api/accounts/netease/login/synthetic-ne-attempt/bind"
  ) {
    Object.assign(rig.neAccount, {
      state: "bound",
      account_ref: "synthetic-ne-account",
      credential_revision: 1,
      uid: "20001",
    });
    return ok(rig.neAccount);
  }
  if (url.pathname === "/api/accounts/netease/unlink") {
    Object.assign(rig.neAccount, {
      state: "unbound",
      account_ref: null,
      uid: null,
      credential_revision: 0,
      binding_generation: rig.neAccount.binding_generation + 1,
    });
    return ok(rig.neAccount);
  }
  if (url.pathname === "/api/accounts/netease/credential") {
    rig.neAccount.credential_revision++;
    return ok(rig.neAccount);
  }
  if (url.pathname.startsWith("/api/catalog/netease/")) {
    const scope = url.searchParams.get("scope") || "account";
    if (scope === "account" && rig.neAccount.state !== "bound")
      return {
        status: 409,
        body: {
          error: {
            code: "platform_auth_required",
            message: "请关联有效的本人网易账号",
          },
        },
      };
    const page = Number(url.searchParams.get("page") || 1);
    const base = {
      provider: "netease",
      scope,
      page,
      account: scope === "account" ? rig.neAccount : null,
      complete: false,
      integrity: "page_only",
      personalization: "unverified",
      has_more: page === 1,
    };
    const neSong = {
      ...structuredClone(song),
      track: { provider: "netease", id_type: "songid", id: "123" },
      title: "合成网易歌曲",
      qualities: [],
    };
    if (
      url.pathname === "/api/catalog/netease/playlists/88" ||
      url.searchParams.get("kind") === "songs"
    )
      return ok({
        ...base,
        source_total: 103,
        items: [
          neSong,
          { track: null, title: "来源中的未知条目", qualities: [] },
          { ...neSong },
        ],
      });
    return ok({
      ...base,
      items: [
        {
          playlist: { provider: "netease", id: "88" },
          title: "合成网易歌单 " + page,
          creator: "测试账号",
          song_count: 103,
        },
      ],
    });
  }
  if (url.pathname === "/api/accounts/qq/login") {
    rig.qqAccount = {
      ...rig.qqAccount,
      state: "unbound",
      binding_generation: rig.qqAccount.binding_generation + 1,
    };
    rig.qqAttempt = {
      id: "synthetic-attempt",
      status: body.kind === "existing" ? "confirmed" : "waiting",
      uin: body.kind === "existing" ? "10001" : null,
      binding_generation: rig.qqAccount.binding_generation,
      qr_path: "/api/accounts/qq/login/synthetic-attempt/qr",
    };
    return { status: 201, body: rig.qqAttempt };
  }
  if (url.pathname === "/api/accounts/qq/login/synthetic-attempt/qr")
    return {
      status: 200,
      type: "image/png",
      raw: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jxVQAAAAASUVORK5CYII=",
        "base64",
      ),
    };
  if (url.pathname === "/api/accounts/qq/login/synthetic-attempt") {
    rig.qqAttempt = {
      ...rig.qqAttempt,
      status: rig.qqPoll,
      uin: rig.qqPoll === "confirmed" ? "10001" : null,
    };
    return ok(rig.qqAttempt);
  }
  if (url.pathname === "/api/accounts/qq/login/synthetic-attempt/bind") {
    rig.qqAccount = {
      ...rig.qqAccount,
      state: "bound",
      account_ref: "synthetic-account",
      credential_revision: 1,
      uin: "10001",
    };
    return ok(rig.qqAccount);
  }
  if (url.pathname === "/api/accounts/qq/unlink") {
    rig.qqAccount = {
      ...rig.qqAccount,
      state: "unbound",
      account_ref: null,
      uin: null,
      credential_revision: 0,
      binding_generation: rig.qqAccount.binding_generation + 1,
    };
    rig.qqAttempt = null;
    return ok(rig.qqAccount);
  }
  if (url.pathname.startsWith("/api/playlist-captures/")) {
    const capture = rig.captures.find(
      (c) => url.pathname.split("/")[3] === c.id,
    );
    if (method === "DELETE") {
      Object.assign(capture, {
        status: "deleted",
        complete: false,
        manifest_id: null,
      });
      return ok(capture);
    }
    if (url.pathname.endsWith("/run"))
      Object.assign(capture, {
        status: "complete",
        complete: true,
        fetched_count: (rig.snapshotSongs || rig.qqSongs).length,
        manifest_id: "qq-snapshot",
      });
    return ok(capture);
  }
  const historyPage = (rows) => {
    rows = [...rows].reverse();
    const before = url.searchParams.get("before");
    const offset = before ? rows.findIndex((c) => c.id === before) + 1 : 0;
    const visible = rows.slice(offset).filter((c) => c.status !== "deleted");
    const items = visible.slice(0, 20);
    return ok({
      items,
      next_cursor: visible.length > 20 ? items.at(-1).id : null,
    });
  };
  if (url.pathname === "/api/playlist-captures")
    return historyPage(rig.captures);
  if (url.pathname === "/api/manifests/qq-snapshot")
    return ok({
      fetched_count: (rig.snapshotSongs || rig.qqSongs).length,
      captured_at: "2026-10-23T12:00:00Z",
      ordered_entries: (rig.snapshotSongs || rig.qqSongs).map(
        (song, position) => ({
          song,
          position,
        }),
      ),
    });
  if (url.pathname.startsWith("/api/catalog/qq/")) {
    if (rig.qqAccount.state !== "bound")
      return {
        status: 409,
        body: {
          error: {
            code: "platform_auth_required",
            message: "请先关联本人 QQ 账号；不会回退公共推荐",
          },
        },
      };
    if (url.pathname.endsWith("/snapshots")) {
      if (method === "POST") {
        const previous = rig.captures.find(
          (c) => c.idem === options.headers["Idempotency-Key"],
        );
        if (previous) return { status: 201, body: previous };
        const capture = {
          id: "capture-" + (rig.captures.length + 1),
          idem: options.headers["Idempotency-Key"],
          status: "pending",
          complete: false,
          created_at: "2026-10-23T12:00:00Z",
          fetched_count: 0,
          source: { provider: "qq", id: "77", dirid: "9" },
        };
        rig.captures.push(capture);
        return { status: 201, body: capture };
      }
      return historyPage(rig.captures);
    }
    const base = {
      provider: "qq",
      scope: "account",
      account: rig.qqAccount,
      personalization: "unverified",
    };
    if (url.pathname.endsWith("recommendations"))
      return ok({
        ...base,
        items:
          url.searchParams.get("kind") === "songs"
            ? rig.qqSongs
            : rig.qqRecommendations,
        page: Number(url.searchParams.get("page")),
        cursor: Number(url.searchParams.get("cursor")),
        next_cursor: rig.qqNextCursor || null,
        has_more: Boolean(rig.qqNextCursor),
      });
    if (url.pathname === "/api/catalog/qq/playlists")
      return ok({ ...base, items: rig.qqRecommendations, complete: true });
    return ok({
      ...base,
      items: rig.qqSongs,
      page: Number(url.searchParams.get("page")),
      source_total: 205,
      has_more: true,
      complete: false,
      integrity: "page_only",
    });
  }
  if (url.pathname === "/api/search") {
    const provider = url.searchParams.get("provider");
    return ok({
      items: rig.songs.map((s) =>
        s.track
          ? {
              ...s,
              track: {
                ...s.track,
                provider,
                id_type: provider === "qq" ? "songid" : "rid",
              },
            }
          : s,
      ),
      has_more: rig.searchMore,
      page: Number(url.searchParams.get("page")),
    });
  }
  if (url.pathname === "/api/favorites") {
    if (method === "POST") {
      if (body.enabled)
        rig.favorites.push(
          [...rig.songs, ...rig.qqSongs].find(
            (s) => s.track?.id === body.track.id,
          ),
        );
      else
        rig.favorites = rig.favorites.filter(
          (s) => s.track.id !== body.track.id,
        );
      return ok({ ok: true });
    }
    return ok({ items: rig.favorites, kind: "local" });
  }
  if (url.pathname === "/api/manifests") {
    rig.manifests.push(body.tracks);
    return { status: 201, body: { id: "manifest-" + rig.manifests.length } };
  }
  if (url.pathname === "/api/tasks" && method === "POST") {
    const old = rig.tasks.find(
      (t) => t.idem === options.headers["Idempotency-Key"],
    );
    if (old) return ok(old);
    const tracks = rig.manifests[
      Number(body.manifest_id.split("-")[1]) - 1
    ] || [track];
    const task = {
      id: "task-" + (rig.tasks.length + 1),
      idem: options.headers["Idempotency-Key"],
      quality: body.quality,
      status: "running",
      created_at: "2026-10-21T12:00:00+08:00",
      entries: tracks.map((t) => ({
        track: t,
        title: rig.songs.find((s) => s.track?.id === t.id)?.title || song.title,
        artist: song.artist,
        status: "running",
        error: null,
      })),
    };
    rig.tasks.push(task);
    return { status: 202, body: task };
  }
  if (url.pathname === "/api/tasks") return ok({ items: rig.tasks });
  if (url.pathname === "/api/assets") return ok({ items: rig.assets });
  if (url.pathname === "/api/admin/injection")
    return rig.isAdmin
      ? ok({ available: false, reason: "官方音乐注入尚未接入" })
      : { status: 403, body: { error: { message: "无权限" } } };
  if (/\/api\/tasks\/[^/]+\/control/.test(url.pathname)) {
    const task = rig.tasks.find((t) => url.pathname.includes(t.id));
    task.status = body.action === "pause" ? "paused" : "running";
    return ok({ ok: true });
  }
  throw new Error("Unexpected test API: " + method + " " + path);
}
