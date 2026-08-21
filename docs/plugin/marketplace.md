# Plugin Marketplace

Discover plugins available on the marketplace before installing them — all
three commands here are read-only and public, no credentials required.

## Browse All

List published plugins, sorted `newest` (default), `downloads`, or `rating`.

```bash
xcli plugin marketplace browse
xcli plugin marketplace browse --sort downloads --limit 50
```

## Search

Find plugins by name or description.

```bash title="Search"
xcli plugin marketplace search "monitoring"
```

## Plugin Details

Get in-depth information about a specific marketplace plugin before
installing it — description, rating, download count, repository, and
published versions.

```bash title="Plugin Info"
xcli plugin marketplace info name-of-plugin
```

## What's not here

Rating a plugin (`POST /plugins/{slug}/ratings`) requires a full user
session (Bearer JWT), not the API key `xcli` stores — that's a web-app
action, not a CLI one; rate plugins from the XCoreHub dashboard instead.
There's also no dedicated "trending" endpoint server-side — use
`browse --sort downloads` or `--sort rating` for the same effect.

## Installing

Once you've found a plugin, see [Installing Plugins](install.md) — it
needs the API key and signing key described in
[Authentication](../getting-started/auth.md), which discovery commands on
this page don't.
