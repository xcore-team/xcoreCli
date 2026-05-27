# Plugin Marketplace

Discover and explore new capabilities for your `xcore` project via the official marketplace.

## Discovery Commands

### Browse All

List everything available on the marketplace.

```bash
xcli plugin marketplace browse
```

### Search

Find plugins by keywords, tags, or categories.

```bash title="Search"
xcli plugin marketplace search "monitoring"
```

### Trending

See what's popular in the community.

```bash
xcli plugin marketplace trending
```

## Viewing Plugin Details

Get in-depth information about a specific marketplace plugin before installing it.

```bash title="Plugin Info"
xcli plugin marketplace info name-of-plugin
```

## Community Feedback

### Rating Plugins

Share your experience by rating a plugin (1 to 5 stars).

```bash
xcli plugin marketplace rate name-of-plugin --score 5
```

!!! info "API Keys"
    Interacting with the marketplace requires an API key. Configure it using `xcli config set api-key xdk_...`.
