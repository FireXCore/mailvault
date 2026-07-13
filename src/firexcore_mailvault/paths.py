from __future__ import annotations

from pathlib import Path

from firexcore_mailvault.models import ArchivePaths


def build_archive_paths(root: Path) -> ArchivePaths:
    root = root.expanduser().resolve()
    paths = ArchivePaths(
        root=root,
        raw_objects=root / "objects" / "raw" / "sha256",
        blobs=root / "objects" / "blobs" / "sha256",
        metadata_messages=root / "metadata" / "messages",
        database=root / "database" / "mailvault.sqlite3",
        manifests=root / "manifests",
        state=root / "state",
        reports=root / "reports",
        views=root / "views",
        logs=root / "logs",
    )
    for directory in (
        paths.raw_objects,
        paths.blobs,
        paths.metadata_messages,
        paths.database.parent,
        paths.manifests,
        paths.state,
        paths.reports,
        paths.views,
        paths.logs,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return paths
