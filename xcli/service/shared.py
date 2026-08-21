from __future__ import annotations

from pathlib import Path

from xcli.config.runtime import marketplace_services_directory

# marketplace_api_base() is catalog-agnostic (same backend origin for both
# plugins and services) — imported, not forked, so the marketplace.url/
# api_url fallback logic can't drift between the two catalogs.
from xcli.plugin.shared import console, marketplace_api_base

__all__ = ['console', 'marketplace_api_base', 'service_install_url', 'services_dir']


def service_install_url(name: str, version: str) -> str:
    return f'{marketplace_api_base()}/app/xservices/services/{name}/install?version={version}'


def services_dir() -> Path:
    return marketplace_services_directory()
