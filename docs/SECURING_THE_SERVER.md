# Securing the deployed server

**Status: research only, nothing implemented.** Written 2026-07-18 after confirming the live Railway deployment is reachable by anyone.

## The problem, in one paragraph

This server is single-user by design: whoever's TickTick credentials sit in the Railway env vars *is* the user, and there is no per-request identity. `docs/ARCHITECTURE.md` already states the consequence plainly: **anyone who can reach `/mcp` acts as them.** Inbound protection exists in the code (`BearerTokenMiddleware`, `server.py:3482-3516`) but it only installs itself when `MCP_BEARER_TOKEN` is set, and that variable is **not set on the Railway deployment**. So the only thing standing between a stranger and full read/write/delete access to the owner's TickTick account is that they have not tried the URL.

## What was verified (2026-07-18)

| Claim | Method | Result |
|---|---|---|
| The deployment is open | Sent an MCP `initialize` to the live `/mcp` with no credentials | **Confirmed open.** Got HTTP 200 and a real `mcp-session-id`. |
| The URL is guessable | Inspection | It follows Railway's default `<service>-<environment>.up.railway.app` pattern, and the service name matches a **public** GitHub repo. Obscurity is weak here. |
| The claude.ai OAuth fields do something | Code read | **They do nothing.** The server has no OAuth surface of its own (no `/authorize`, `/token`, `/register`, no `.well-known/oauth-*`, no `TokenVerifier`). `TICKTICK_CLIENT_ID`/`SECRET` authenticate the server *outbound to TickTick*, a different direction entirely. The connector works because `/mcp` is unauthenticated, not because those fields were filled in. |
| claude.ai can send a bearer token | Opened the real "Add custom connector" dialog on the owner's account, Advanced settings expanded | **Not on this account.** The dialog offers exactly three inputs: Name, Remote MCP server URL, and (under Advanced settings) OAuth Client ID and OAuth Client Secret. There is no Request headers section. |
| The app sleeps when idle | Repeated `/health` requests | First request returned a Railway 502, subsequent ones returned `{"status":"ok"}`. Any client must tolerate a cold start. |

## Answering the two questions that prompted this

### "Can we put the V2 cookies into the claude.ai connector settings instead of Railway?"

**No, for three independent reasons, any one of which is fatal.**

1. **There is no field for it.** Verified above: the dialog takes a URL and OAuth client credentials, nothing else.
2. **Even the beta feature would not accept it.** Anthropic's docs describe `static_headers` (request-header auth, in beta), but header names are restricted to a reviewed allowlist of standard auth/routing names such as `authorization`, `x-api-key`, and `x-auth-token`. `cookie` is not a name you can expect to send, and the docs say additions require contacting Anthropic.
3. **The server could not consume it anyway.** TickTick credentials are read from env/settings at startup, and a single shared `TickTickClient` is reused per process. Accepting per-request credentials would mean restructuring the client lifecycle. That is a real rewrite, not a config change.

Worth noting *why* the idea was appealing: if the server held no TickTick credentials of its own, an anonymous visitor would reach a server that can do nothing. That instinct is sound, it is a legitimate architecture. It is just not reachable from where this code and this UI currently are, and a bearer token achieves the same protection for a fraction of the effort.

### "Why did we end up using Railway env vars? Did the claude.ai route fail?"

Two things were conflated, and the git history shows it.

- **TickTick credentials in Railway env vars was never an alternative to anything.** The server is single-user; there is no mechanism by which claude.ai could ever supply them. This part was never a retreat, it is simply the design.
- **Dropping `MCP_BEARER_TOKEN` was a retreat, and an unverified one.** Commit `ae24d8e` (2026-03-12 20:14 UTC) added bearer auth and documented it as required. Commit `b371efa`, **55 minutes later in the same session**, removed it from the setup path with the message "Remove bearer token from Railway setup (Claude.ai doesn't support it)". No 401, no error log, no troubleshooting entry, no issue was ever recorded. `git log -S"does not currently support"` returns only that one commit; the claim has never been revisited. The repo later half-admits this in `docs/OfficialTickTickMCP.md:45`, which flags the connector-UI auth behaviour as explicitly **unverified**.

**The accidental punchline: the claim turned out to be right, for the wrong reason.** It was written as an inference, but the dialog inspection above confirms this account genuinely cannot send a bearer token today. The feature exists in beta and simply has not been rolled out here.

## Options for actually fixing it

Ordered by how soon they can work, not by preference.

### Option 1: Get beta access to request headers, then just set the variable

Anthropic's docs describe `static_headers` as "in beta... being slowly rolled out to customers; contact Anthropic for early access." If granted, the fix is: set `MCP_BEARER_TOKEN` in Railway, and in the connector dialog add an `Authorization` header with the value `Bearer <token>` (the scheme must be typed, Claude sends the value verbatim).

- **Effort: near zero.** The server-side middleware already exists and needs no changes.
- **Blocker: waiting on Anthropic**, with no guaranteed timeline. GitHub issue anthropics/claude-ai-mcp#112, which requested exactly this, was closed as not planned.
- **Confidence it solves the problem once granted: ~95%.**

### Option 2: Secret path segment

Move the MCP endpoint from `/mcp` to `/<32-random-chars>/mcp` and paste the new URL into the connector. The secret rides in the URL that claude.ai already stores.

- **Effort: small**, a routing change in `server.py`.
- **Works today, needs nothing from Anthropic, and defeats the actual threat** (someone guessing a predictable hostname).
- **Caveats, stated honestly:** Anthropic's own docs discourage credentials in URLs because URLs land in logs, proxies, and history. That warning targets query strings specifically, and a path secret is meaningfully better than `?token=`, but it is the same family of weakness. It is a large improvement over nothing, not a rigorous solution.
- **Confidence: ~85%** against opportunistic discovery, lower against anyone who can read Railway's request logs.

### Option 3: Restrict by Anthropic's egress IP range

Anthropic publishes the outbound range it uses for MCP tool calls: **`160.79.104.0/21`** (confirmed current on the platform IP-addresses page; the `/23` range seen in some search results is the *inbound* range, a different thing, and the phased-out addresses are the old `34.162.x.x` ones). A middleware could reject anything outside it.

- **Works today, needs no claude.ai configuration at all.**
- **Serious caveat that must be resolved before relying on this:** Railway terminates TLS at its edge, so the app sees the proxy, not the client. The real address arrives in `X-Forwarded-For`, and if that header is trusted naively an attacker can simply *send* `X-Forwarded-For: 160.79.104.5` and walk straight through. Whether Railway's edge overwrites or merely appends to a client-supplied value decides whether this option is genuinely secure or actively misleading. **Verify before implementing**, and prefer reading the last entry rather than the first.
- It would also block the planned TrackyTime phone sync, which comes from a residential IP and would need its own separately-authenticated route.
- **Confidence: ~60%**, entirely because of the header-trust question.

### Option 4: Implement real OAuth (DCR or CIMD)

The officially blessed path, and the only one Anthropic actively supports for custom connectors without beta flags. Requires resource metadata, an authorization server, PKCE S256, and a consent step.

- **Effort: large**, hundreds of lines plus a consent flow, for a server with exactly one user.
- FastMCP ships an OAuth proxy, but it currently carries an unresolved security advisory (GHSA-5h2m-4q8j-pqpj) about tokens being scoped to the base URL rather than the specific server, so it is not a drop-in.
- **Confidence it works: high. Confidence it is worth it for a single-user server: low.**

### Non-option: renaming the Railway service

Tempting because it costs nothing, but it only reshuffles obscurity, and hostnames are far more discoverable than paths (certificate transparency logs and DNS enumeration both surface hostnames; neither ever sees a URL path). Fine as a small extra layer, useless as the primary defence.

## Recommendation

**Option 2 now, Option 1 as the real fix.** A secret path can be shipped today, closes the "someone guesses the URL" hole that actually exists, and costs almost nothing. In parallel, ask Anthropic for `static_headers` beta access; when it lands, set `MCP_BEARER_TOKEN`, add the header in the connector, and the path secret becomes a redundant second layer rather than the only one.

Option 3 is attractive but must not be implemented until the `X-Forwarded-For` question is settled, because a spoofable allowlist is worse than no allowlist: it creates confidence that is not earned.

Whichever is chosen, the TrackyTime daily-note endpoint described in `TICKTICK_SYNC_PLAN.md` (in the TrackyTime repo) should get its own separate token checked inside the route handler, since that traffic originates from a phone rather than from Anthropic.
