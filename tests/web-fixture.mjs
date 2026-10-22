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
    return ok({ enabled: true, items: [rig.qqAccount] });
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
