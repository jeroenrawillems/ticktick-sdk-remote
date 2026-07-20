# Securing the deployed server

## The problem

This server is **single-user by design**: whoever's TickTick credentials sit in the environment variables *is* the user, and there is no per-request identity. The consequence, already stated in `docs/ARCHITECTURE.md`, is blunt: **anyone who can reach `/mcp` acts as that user**, with full read, write, and delete access to their TickTick account.

Inbound protection has existed in the code for a long time (`BearerTokenMiddleware` in `server.py`), but it only installs itself when `MCP_BEARER_TOKEN` is set. A deployment with that variable unset is completely open, and nothing in the startup output used to say so.

## Why the obvious fix does not work on Claude.ai

Setting `MCP_BEARER_TOKEN` requires the client to send an `Authorization` header. Claude.ai supports that only through its **Request headers** feature (`static_headers` in Anthropic's docs), which is in beta and rolled out gradually.

Verified 2026-07-18 on a real account: the "Add custom connector" dialog, with Advanced settings expanded, offers exactly **Name**, **Remote MCP server URL**, **OAuth Client ID**, and **OAuth Client Secret**. There is no Request headers section, and no other field that could carry a credential.

Two follow-on facts worth recording, because both have caused confusion:

- **The OAuth Client ID/Secret fields do nothing here.** This server exposes no OAuth surface of its own: no `/authorize`, no `/token`, no `/register`, no `.well-known/oauth-*`, no `TokenVerifier`. `TICKTICK_CLIENT_ID` / `TICKTICK_CLIENT_SECRET` authenticate this server *outbound to TickTick*, the opposite direction. A connector with those fields filled in works because the endpoint is unauthenticated, not because the fields did anything.
- **The TickTick credentials cannot be moved into the connector either.** Even with the beta, header names are restricted to a reviewed allowlist of standard auth/routing names (`authorization`, `x-api-key`, `x-auth-token` and similar), so a `Cookie` header is not an option. And the server reads its TickTick credentials once at startup into a single shared client, so accepting them per request would mean restructuring the client lifecycle.

## The implemented fix: `MCP_SECRET_PATH`

Since the connector stores the whole **URL**, the secret can live there instead of in a header.

Set `MCP_SECRET_PATH` to a random single path segment. `SecretPathMiddleware` (`server.py`) then requires it as the first segment of every request:

| Request | Result |
|---|---|
| `/<secret>/mcp` | Passes through, rewritten to `/mcp` before the MCP app sees it |
| `/mcp` | `404 {"error": "not found"}` |
| `/wrong/mcp` | `404` |
| `/health` | Passes through **without** the secret |

Design decisions, and why:

- **`/health` is exempt on purpose.** Railway's healthcheck hits it, and a failing healthcheck fails the deploy. It reveals only that something is deployed, no data and no tools.
- **A wrong path returns 404, not 401**, so probing the bare `/mcp` looks like an empty host rather than a guarded one worth attacking.
- **The comparison is constant-time** (`secrets.compare_digest`) and matches only the **first** segment, so `/mcp/<secret>` and partial prefixes are both rejected.
- **The middleware sits outermost**, so a wrong path is rejected before any other logic runs. It composes with `MCP_BEARER_TOKEN`: set both and a client must satisfy both.
- **Unset by default**, so existing deployments keep working unchanged. When neither protection is configured, startup now logs an explicit `SERVER IS UNAUTHENTICATED` warning.

### Honest limitations

A secret in a URL is weaker than a secret in a header, because URLs are routinely recorded in server logs, proxies, and browser history, and Anthropic's own guidance discourages putting credentials in them. This closes the realistic hole (someone reaching a public endpoint that has no lock at all) but it is not a rigorous auth system. Treat it as a strong deterrent, not a vault.

`/health` remaining public also means the hostname can still be confirmed as live by anyone who has it. That is an accepted tradeoff for keeping deploys healthy.

## Alternatives that were considered and rejected

**Request-headers beta, then `MCP_BEARER_TOKEN`.** The clean answer, and still worth pursuing: the middleware already exists, so it becomes a pure config change. Blocked only on Anthropic granting beta access. Note that the GitHub issue requesting exactly this feature (anthropics/claude-ai-mcp#112) was closed as not planned, so the timeline is unpredictable.

**Restricting to Anthropic's egress IP range** (`160.79.104.0/21`, the outbound range; the `/23` one is inbound and a different thing). Attractive because it needs no client configuration, but the deployment sits behind Railway's proxy, so the application sees the proxy rather than the caller. The real address arrives in `X-Forwarded-For`, and if that header is trusted naively an attacker simply sends their own. **Do not implement this without first verifying whether Railway's edge overwrites or merely appends a client-supplied value**, and read the last entry rather than the first. A spoofable allowlist is worse than no allowlist, because it manufactures confidence that was never earned. It would also block any non-Anthropic client, such as a phone app.

**Implementing real OAuth (DCR or CIMD).** The officially supported path, requiring resource metadata, an authorization server, PKCE S256, and a consent step. Hundreds of lines and a consent flow for a server with exactly one user. FastMCP ships an OAuth proxy, but it carries an unresolved security advisory (GHSA-5h2m-4q8j-pqpj) about tokens being scoped to the base URL rather than the specific server, so it is not a drop-in.

**Making the GitHub repository private.** Not possible directly: this repo is a fork, and GitHub does not allow changing a fork's visibility. It would require duplicating the repository and repointing Railway. More work than the secret path, and it would only hide the project's name while leaving the endpoint itself unlocked.

## Operational notes

- Generate a secret with `python -c "import secrets; print(secrets.token_urlsafe(24))"`.
- The value must be a single path segment; the server raises on a `/` inside it and warns below 16 characters.
- Changing the secret invalidates the old URL. A connector's URL generally cannot be edited in place, so plan on removing and re-adding it.
- The secret is never written to the logs. Startup logs the endpoint as `/<secret>/mcp` literally.
