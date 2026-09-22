# web-jina — Jina Search + Reader native backend for Hermes Agent

Makes Jina AI a first-class `web.backend` for Hermes Agent
(`web_search` + `web_extract`). Built as a tested fallback/alternative
to `web-you` — switch any time by changing one config line.

- Search: `GET {search_base}/?q={query}&num={n}` (`Accept: application/json`)
- Extract: `GET {reader_base}/{url}` (Bearer key) → markdown
- Docs: <https://jina.ai/reader> (entry: <https://s.jina.ai/docs>, <https://r.jina.ai/docs>)

Known traits (from the 22 Sep 2026 benchmark): search is slow
(median ~4s, tail 26s) but thorough; every search request costs a fixed
~10,000 tokens; Reader output is token-counted. The provider forwards
`description` snippets only (not full per-hit content) to keep cost down.

## Install

```bash
hermes plugins install jessicasetyani/hermes-plugin-web-jina --enable
```

Dashboard (Nous-cloud): install from this repo URL via the plugin UI,
approve capability consent, then restart gateway + dashboard.

## Configure

```bash
# required — BWS (key name JINA_API_KEY) or ~/.hermes/.env
JINA_API_KEY=...

# optional overrides (only if Jina moves hosts)
JINA_SEARCH_BASE_URL=https://s.jina.ai
JINA_READER_BASE_URL=https://r.jina.ai
```

Two base vars (not one) because Jina runs two distinct services on two
hosts — unlike You.com's single host.

Switch backend (either direction, one line):

```bash
hermes config set web.backend jina   # or: you
```

Takes effect on next session (restart gateway + dashboard on cloud).

## Verify

```bash
hermes plugins doctor "web/jina"   # path key utk layout kategori lokal.
# NB: `plugins list` menampilkan ID "web-jina" (nama manifest) —
# ID itu TIDAK berlaku untuk doctor; doctor mau path key.
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `429` bursts | Search 100 RPM / Reader RPM limits | Built-in single retry; space out bulk calls |
| `reader too thin` error | Page blocked / empty | Honest failure by design — fall back, don't blind-retry |
| `no registered web search provider 'jina'` | Stale session | New session; restart gateway + dashboard on cloud |

## Versioning

Fleet installs should pin a commit SHA (see `hermes-pack.yaml`).
