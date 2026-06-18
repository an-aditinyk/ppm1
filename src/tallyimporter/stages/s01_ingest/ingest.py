"""S01 — Ingest (Zoho adapter): unzip a known archive into role-tagged immutable bytes.

Thin unpacker (S01 D1): no CSV parsing, no joins, no canonicalization. The
``filename -> role`` table is blessed Zoho input-side knowledge supplied as data via the
source profile (S01 D3). Imports only ``contracts/`` and ``core/``.
"""

from __future__ import annotations

import io
import zipfile

from tallyimporter.contracts.errors import IngestError
from tallyimporter.contracts.source import (
    ArtifactRole,
    IngestedArchive,
    RawArtifact,
    SourceProfile,
)


def _decode(name: str, data: bytes) -> str:
    """Validate the artifact decodes as UTF-8 (BOM-tolerant); fail loud otherwise."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestError(
            f"artifact {name!r} is not valid UTF-8", code="encoding", detail={"artifact": name}
        ) from exc


def ingest(archive: bytes, profile: SourceProfile) -> IngestedArchive:
    """Unpack ``archive`` into role-tagged raw artifacts. Pure; never mutates input."""
    roles: dict[str, ArtifactRole] = dict(profile.file_roles)

    try:
        zf = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise IngestError("input is not a valid ZIP archive", code="corrupt_zip") from exc

    artifacts: list[RawArtifact] = []
    extras: list[str] = []
    seen_roles: set[ArtifactRole] = set()

    with zf:
        for name in sorted(zf.namelist()):
            if name.endswith("/"):
                continue  # directory entry
            base = name.rsplit("/", 1)[-1]
            role = roles.get(base)
            if role is None:
                extras.append(base)
                continue
            data = zf.read(name)
            if not data.strip():
                raise IngestError(
                    f"required-or-known artifact {base!r} is empty",
                    code="empty_artifact",
                    detail={"artifact": base},
                )
            _decode(base, data)  # encoding gate
            artifacts.append(
                RawArtifact(role=role, content=data, encoding="utf-8", source_name=base)
            )
            seen_roles.add(role)

    missing = [r.value for r in profile.required_roles if r not in seen_roles]
    if missing:
        raise IngestError(
            f"missing required artifact(s): {sorted(missing)}",
            code="missing_required",
            detail={"missing": ",".join(sorted(missing))},
        )

    artifacts.sort(key=lambda a: a.role.value)  # determinism
    return IngestedArchive(
        source_system=profile.source_system,
        artifacts=tuple(artifacts),
        extra_artifacts_seen=tuple(sorted(extras)),
    )
