from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path

from firexcore_mailvault.repository import ArchiveRepository


@dataclass(slots=True)
class VerificationReport:
    checked_messages: int = 0
    checked_blobs: int = 0
    missing_files: int = 0
    hash_mismatches: int = 0
    size_mismatches: int = 0

    @property
    def ok(self) -> bool:
        return self.missing_files == 0 and self.hash_mismatches == 0 and self.size_mismatches == 0


class IntegrityVerifier:
    def __init__(self, repository: ArchiveRepository, archive_root: Path) -> None:
        self.repository = repository
        self.archive_root = archive_root

    def verify(self, sample_ratio: float = 1.0) -> VerificationReport:
        if not 0 < sample_ratio <= 1:
            raise ValueError("sample_ratio must be within (0, 1].")
        report = VerificationReport()
        for row in self.repository.integrity_messages():
            if random.random() > sample_ratio:
                continue
            report.checked_messages += 1
            self._verify_path(
                self.archive_root / str(row["raw_path"]),
                str(row["raw_sha256"]),
                int(row["raw_size_bytes"] or 0),
                report,
            )
        for row in self.repository.integrity_blobs():
            if random.random() > sample_ratio:
                continue
            report.checked_blobs += 1
            path = self.archive_root / str(row["storage_path"])
            before = report.hash_mismatches + report.missing_files + report.size_mismatches
            self._verify_path(path, str(row["sha256"]), int(row["size_bytes"]), report)
            after = report.hash_mismatches + report.missing_files + report.size_mismatches
            if after == before:
                self.repository.mark_blob_verified(str(row["sha256"]))
        return report

    @staticmethod
    def _verify_path(
        path: Path,
        expected_hash: str,
        expected_size: int,
        report: VerificationReport,
    ) -> None:
        if not path.exists():
            report.missing_files += 1
            return
        if path.stat().st_size != expected_size:
            report.size_mismatches += 1
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_hash:
            report.hash_mismatches += 1
