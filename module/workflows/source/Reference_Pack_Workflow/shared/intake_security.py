#!/usr/bin/env python3
"""Central, fail-closed security policy for Reference Pack material intake."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tempfile
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable
from xml.etree import ElementTree


MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_INPUT_FILES = 5_000
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_PDF_PAGES = 1_000
MAX_PPTX_SLIDES = 500
MAX_SPREADSHEET_SHEETS = 200
MAX_SPREADSHEET_NONEMPTY_CELLS = 1_000_000
MAX_EXTRACTED_TEXT_CHARS_PER_FILE = 10_000_000
MAX_EXTRACTED_TEXT_CHARS_PER_JOB = 50_000_000
MAX_IMAGE_PIXELS = 100_000_000
MAX_IMAGE_EDGE = 32_768

OOXML_REQUIRED_MEMBERS = {
    ".docx": "word/document.xml",
    ".pptx": "ppt/presentation.xml",
    ".xlsx": "xl/workbook.xml",
}
ACTIVE_SVG_ELEMENTS = {"script", "foreignobject", "iframe", "object", "embed"}
EXTERNAL_REFERENCE = re.compile(r"^(?:https?:|ftp:|file:|//)", re.IGNORECASE)


class IntakeSecurityError(ValueError):
    """Material is unsafe, malformed, disguised, or outside intake budgets."""


@dataclass
class IntakeBudget:
    """One cumulative archive/material budget for a complete intake Job.

    OOXML is itself a ZIP container.  Keeping the accounting object outside a
    single ``validate_ooxml`` call prevents a material archive containing many
    individually-small Office files from multiplying the configured limits.
    """

    file_count: int = 0
    uncompressed_bytes: int = 0
    compressed_bytes: int = 0

    def consume(
        self, *, file_count: int, uncompressed_bytes: int,
        compressed_bytes: int, label: str,
    ) -> None:
        if min(file_count, uncompressed_bytes, compressed_bytes) < 0:
            raise IntakeSecurityError(f"{label}_invalid_budget_accounting")
        next_count = self.file_count + file_count
        if next_count > MAX_INPUT_FILES:
            raise IntakeSecurityError(f"{label}_too_many_members")
        next_uncompressed = self.uncompressed_bytes + uncompressed_bytes
        next_compressed = self.compressed_bytes + compressed_bytes
        if next_uncompressed and not next_compressed:
            raise IntakeSecurityError(f"{label}_compression_ratio_exceeded")
        if next_compressed and next_uncompressed / next_compressed > MAX_COMPRESSION_RATIO:
            raise IntakeSecurityError(f"{label}_compression_ratio_exceeded")
        self.file_count = next_count
        self.uncompressed_bytes = next_uncompressed
        self.compressed_bytes = next_compressed


def _safe_member_name(value: str) -> bool:
    if not value or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() == value


def path_has_symlink_component(path: Path) -> bool:
    """Inspect a caller-supplied path before ``resolve`` can erase its identity."""

    absolute = Path(os.path.abspath(Path(path).expanduser()))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            if current.is_symlink():
                # Stable macOS aliases are outside the caller-controlled tail.
                if current.parent == Path(current.anchor) and current.name in {
                    "var", "tmp", "etc",
                }:
                    continue
                return True
        except OSError:
            return True
    return False


def _copy_open_fd(
    source_fd: int, destination_fd: int, expected_size: int, *,
    enforce_size_limit: bool = False,
) -> str:
    digest = hashlib.sha256()
    total = 0
    with os.fdopen(os.dup(destination_fd), "wb") as target:
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            total += len(block)
            if (enforce_size_limit and total > MAX_INPUT_BYTES) or total > expected_size:
                raise IntakeSecurityError("knowledge_base_input_changed_during_intake")
            digest.update(block)
            target.write(block)
        target.flush()
        os.fsync(target.fileno())
    if total != expected_size:
        raise IntakeSecurityError("knowledge_base_input_changed_during_intake")
    return digest.hexdigest()


def freeze_regular_file(
    path: Path, staging: Path, *, label: str,
    budget: IntakeBudget | None = None, budget_label: str = "knowledge_base_job",
    enforce_size_limit: bool = False,
) -> tuple[Path, int, str]:
    """Create a no-follow, hash-verified immutable staging copy.

    The source is compared before/open/after by device, inode, size, mtime and
    ctime.  Budget consumption and the frozen file commit as one transaction.
    """

    source = Path(path).expanduser()
    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=True)
    if path_has_symlink_component(source):
        raise IntakeSecurityError("knowledge_base_item_not_regular_or_symlink")
    try:
        before = source.lstat()
    except OSError as exc:
        raise IntakeSecurityError(f"knowledge_base_item_unreadable: {label}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise IntakeSecurityError("knowledge_base_item_not_regular_or_symlink")
    if enforce_size_limit and before.st_size > MAX_INPUT_BYTES:
        raise IntakeSecurityError("knowledge_base_item_too_large")

    budget_before = None if budget is None else (
        budget.file_count, budget.uncompressed_bytes, budget.compressed_bytes,
    )
    source_fd = -1
    frozen_fd, frozen_name = tempfile.mkstemp(
        prefix="frozen_", suffix=source.suffix.casefold(), dir=staging,
    )
    frozen = Path(frozen_name)
    flags = os.O_RDONLY
    # The Windows CRT otherwise opens descriptors in text mode and translates
    # CRLF while ``os.read`` streams bytes.  That makes the byte count differ
    # from ``st_size`` for ordinary Markdown/text inputs and falsely reports a
    # TOCTOU mutation.  Keep the source snapshot byte-for-byte on every host.
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        source_fd = os.open(source, flags)
        opened = os.fstat(source_fd)
        if not stat.S_ISREG(opened.st_mode) or (
            opened.st_dev, opened.st_ino
        ) != (before.st_dev, before.st_ino):
            raise IntakeSecurityError("knowledge_base_input_changed_during_intake")
        if budget is not None:
            budget.consume(
                file_count=1, uncompressed_bytes=opened.st_size,
                compressed_bytes=opened.st_size, label=budget_label,
            )
        digest = _copy_open_fd(
            source_fd, frozen_fd, opened.st_size,
            enforce_size_limit=enforce_size_limit,
        )
        after_fd = os.fstat(source_fd)
        after_path = source.lstat()
        # Windows' CRT ``fstat`` reports creation time with a different
        # precision/rounding than ``Path.lstat`` even when the file is
        # unchanged.  Comparing that field creates intermittent false TOCTOU
        # failures for ordinary CRLF text.  Device/inode, size and mtime still
        # provide the mutation check there; retain ctime on POSIX.
        stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
        if os.name != "nt":
            stable += ("st_ctime_ns",)
        if any(getattr(opened, key) != getattr(after_fd, key) for key in stable):
            raise IntakeSecurityError("knowledge_base_input_changed_during_intake")
        if any(getattr(opened, key) != getattr(after_path, key) for key in stable):
            raise IntakeSecurityError("knowledge_base_input_changed_during_intake")
        os.lseek(frozen_fd, 0, os.SEEK_SET)
        frozen_digest = hashlib.sha256()
        while block := os.read(frozen_fd, 1024 * 1024):
            frozen_digest.update(block)
        if frozen_digest.hexdigest() != digest:
            raise IntakeSecurityError("knowledge_base_frozen_copy_hash_mismatch")
        return frozen, opened.st_size, digest
    except (OSError, IntakeSecurityError) as exc:
        # Windows does not permit unlinking an open file.  Close both handles
        # before rolling back the staging member; POSIX keeps the same
        # fail-closed behavior and simply makes the ordering explicit.
        if source_fd >= 0:
            os.close(source_fd)
            source_fd = -1
        if frozen_fd >= 0:
            os.close(frozen_fd)
            frozen_fd = -1
        try:
            frozen.unlink(missing_ok=True)
        except OSError:
            # The original intake error is the useful contract error.  A
            # failed cleanup must not turn a rejected input into an unrelated
            # platform-specific exception.
            pass
        if budget is not None and budget_before is not None:
            budget.file_count, budget.uncompressed_bytes, budget.compressed_bytes = budget_before
        if isinstance(exc, IntakeSecurityError):
            raise
        raise IntakeSecurityError(f"knowledge_base_item_unreadable: {label}") from exc
    finally:
        if source_fd >= 0:
            os.close(source_fd)
        if frozen_fd >= 0:
            os.close(frozen_fd)


def freeze_directory_tree(
    source: Path, destination: Path, *, label: str,
    budget: IntakeBudget | None = None,
    file_validator: Callable[[Path, PurePosixPath, IntakeBudget | None], None] | None = None,
    enforce_size_limits: bool = False,
) -> Path:
    """Freeze a complete directory as one create-only transaction.

    A symlink, socket/FIFO/device, budget breach, source mutation, or validator
    error removes the complete temporary tree and restores the shared budget.
    """

    raw_source = Path(source).expanduser()
    destination = Path(destination)
    if path_has_symlink_component(raw_source) or raw_source.is_symlink():
        raise IntakeSecurityError(f"{label}_directory_symlink_forbidden")
    try:
        metadata = raw_source.lstat()
    except OSError as exc:
        raise IntakeSecurityError(f"{label}_directory_unreadable") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise IntakeSecurityError(f"{label}_directory_not_regular")
    if destination.exists() or destination.is_symlink():
        raise IntakeSecurityError(f"{label}_destination_exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    budget_before = None if budget is None else (
        budget.file_count, budget.uncompressed_bytes, budget.compressed_bytes,
    )
    temporary = Path(tempfile.mkdtemp(
        prefix=f".{destination.name}.staging-", dir=destination.parent,
    ))
    try:
        file_count = 0
        for item in sorted(
            raw_source.rglob("*"), key=lambda value: value.relative_to(raw_source).as_posix(),
        ):
            relative = PurePosixPath(item.relative_to(raw_source).as_posix())
            item_metadata = item.lstat()
            staged = temporary / relative.as_posix()
            if stat.S_ISLNK(item_metadata.st_mode):
                raise IntakeSecurityError(f"{label}_directory_symlink_forbidden: {relative}")
            if stat.S_ISDIR(item_metadata.st_mode):
                staged.mkdir(parents=True, exist_ok=True)
                continue
            if not stat.S_ISREG(item_metadata.st_mode):
                raise IntakeSecurityError(f"{label}_directory_special_file_forbidden: {relative}")
            file_count += 1
            if file_count > MAX_INPUT_FILES:
                raise IntakeSecurityError(f"{label}_too_many_members")
            staged.parent.mkdir(parents=True, exist_ok=True)
            frozen, _, _ = freeze_regular_file(
                item, staged.parent, label=relative.as_posix(), budget=budget,
                budget_label=label, enforce_size_limit=enforce_size_limits,
            )
            os.replace(frozen, staged)
            if file_validator is not None:
                file_validator(staged, relative, budget)
        os.replace(temporary, destination)
        return destination
    except Exception:
        if budget is not None and budget_before is not None:
            budget.file_count, budget.uncompressed_bytes, budget.compressed_bytes = budget_before
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def validate_directory_tree(
    source: Path, *, label: str, budget: IntakeBudget | None = None,
    enforce_size_limits: bool = False,
) -> IntakeBudget:
    """Read-only directory preflight using the same file and byte budget."""

    raw_source = Path(source).expanduser()
    if path_has_symlink_component(raw_source) or raw_source.is_symlink():
        raise IntakeSecurityError(f"{label}_directory_symlink_forbidden")
    try:
        root_metadata = raw_source.lstat()
    except OSError as exc:
        raise IntakeSecurityError(f"{label}_directory_unreadable") from exc
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise IntakeSecurityError(f"{label}_directory_not_regular")
    active = budget if budget is not None else IntakeBudget()
    file_count = 0
    for item in sorted(
        raw_source.rglob("*"), key=lambda value: value.relative_to(raw_source).as_posix(),
    ):
        relative = item.relative_to(raw_source).as_posix()
        try:
            metadata = item.lstat()
        except OSError as exc:
            raise IntakeSecurityError(f"{label}_directory_unreadable: {relative}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise IntakeSecurityError(f"{label}_directory_symlink_forbidden: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise IntakeSecurityError(f"{label}_directory_special_file_forbidden: {relative}")
        file_count += 1
        if file_count > MAX_INPUT_FILES:
            raise IntakeSecurityError(f"{label}_too_many_members")
        if enforce_size_limits:
            active.consume(
                file_count=1, uncompressed_bytes=metadata.st_size,
                compressed_bytes=metadata.st_size, label=label,
            )
        else:
            active.file_count = file_count
            active.uncompressed_bytes += metadata.st_size
            active.compressed_bytes += metadata.st_size
    return active


def validate_zip_infos(
    infos: Iterable[zipfile.ZipInfo], *, label: str,
    budget: IntakeBudget | None = None,
    enforce_size_limits: bool = False,
) -> list[zipfile.ZipInfo]:
    values = list(infos)
    names = [item.filename for item in values]
    if len(names) != len(set(names)):
        raise IntakeSecurityError(f"{label}_duplicate_member")
    if len(values) > MAX_INPUT_FILES:
        raise IntakeSecurityError(f"{label}_too_many_members")
    total = 0
    for item in values:
        checked = item.filename[:-1] if item.is_dir() and item.filename.endswith("/") else item.filename
        if not _safe_member_name(checked):
            raise IntakeSecurityError(f"{label}_unsafe_path: {item.filename!r}")
        if item.flag_bits & 0x1:
            raise IntakeSecurityError(f"{label}_encrypted_member: {item.filename}")
        mode = item.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if kind == stat.S_IFLNK:
            raise IntakeSecurityError(f"{label}_symlink_member: {item.filename}")
        if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise IntakeSecurityError(f"{label}_special_member: {item.filename}")
        if item.is_dir():
            continue
        if enforce_size_limits and item.file_size > MAX_INPUT_BYTES:
            raise IntakeSecurityError(f"{label}_member_too_large: {item.filename}")
        if item.file_size and not item.compress_size:
            raise IntakeSecurityError(f"{label}_compression_ratio_exceeded: {item.filename}")
        if item.compress_size and item.file_size / item.compress_size > MAX_COMPRESSION_RATIO:
            raise IntakeSecurityError(f"{label}_compression_ratio_exceeded: {item.filename}")
        total += item.file_size
    if enforce_size_limits and total > MAX_TOTAL_BYTES:
        raise IntakeSecurityError(f"{label}_total_size_exceeded")
    if budget is not None and enforce_size_limits:
        files = [item for item in values if not item.is_dir()]
        budget.consume(
            file_count=len(values),
            uncompressed_bytes=sum(item.file_size for item in files),
            compressed_bytes=sum(item.compress_size for item in files),
            label=label,
        )
    return values


def validate_ooxml(path: Path, suffix: str, *, budget: IntakeBudget | None = None) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = validate_zip_infos(
                archive.infolist(), label="knowledge_base_ooxml", budget=None,
                enforce_size_limits=False,
            )
            if budget is not None:
                files = [item for item in infos if not item.is_dir()]
                next_count = budget.file_count + len(infos)
                if next_count > MAX_INPUT_FILES:
                    raise IntakeSecurityError("knowledge_base_ooxml_too_many_members")
                budget.file_count = next_count
                budget.uncompressed_bytes += sum(item.file_size for item in files)
                budget.compressed_bytes += sum(item.compress_size for item in files)
            names = {item.filename for item in infos if not item.is_dir()}
            if "[Content_Types].xml" not in names or OOXML_REQUIRED_MEMBERS[suffix] not in names:
                raise IntakeSecurityError(f"knowledge_base_format_mismatch: {path.name}")
            lowered = {name.casefold() for name in names}
            if "encryptedpackage" in lowered or "encryptioninfo" in lowered:
                raise IntakeSecurityError(f"knowledge_base_encrypted_office: {path.name}")
            if any(PurePosixPath(name).suffix.casefold() == ".zip" for name in names):
                raise IntakeSecurityError(f"knowledge_base_ooxml_nested_archive: {path.name}")
    except IntakeSecurityError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise IntakeSecurityError(f"knowledge_base_ooxml_unreadable: {path.name}") from exc


def validate_svg(path: Path) -> tuple[int | None, int | None]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise IntakeSecurityError(f"knowledge_base_svg_unreadable: {path.name}") from exc
    prefix = raw[:4096].decode("utf-8-sig", errors="replace")
    if "<!DOCTYPE" in prefix.upper() or "<!ENTITY" in prefix.upper():
        raise IntakeSecurityError(f"knowledge_base_svg_active_content: {path.name}")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise IntakeSecurityError(f"knowledge_base_svg_unreadable: {path.name}") from exc
    if root.tag.rsplit("}", 1)[-1].casefold() != "svg":
        raise IntakeSecurityError(f"knowledge_base_format_mismatch: {path.name}")
    for element in root.iter():
        local = element.tag.rsplit("}", 1)[-1].casefold()
        if local in ACTIVE_SVG_ELEMENTS:
            raise IntakeSecurityError(f"knowledge_base_svg_active_content: {path.name}")
        for raw_name, raw_value in element.attrib.items():
            name = raw_name.rsplit("}", 1)[-1].casefold()
            value = str(raw_value).strip()
            if name.startswith("on") or name == "style" and "url(" in value.casefold():
                raise IntakeSecurityError(f"knowledge_base_svg_active_content: {path.name}")
            if name in {"href", "src"} and (EXTERNAL_REFERENCE.match(value) or value.casefold().startswith("data:")):
                raise IntakeSecurityError(f"knowledge_base_svg_external_reference: {path.name}")

    def dimension(name: str) -> int | None:
        value = root.attrib.get(name)
        matched = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)(?:px)?\s*", value or "", re.IGNORECASE)
        return int(float(matched.group(1))) if matched else None

    width, height = dimension("width"), dimension("height")
    validate_image_dimensions(width, height, path.name)
    return width, height


def validate_image_dimensions(width: int | None, height: int | None, label: str) -> None:
    if width is None or height is None:
        return
    if width <= 0 or height <= 0 or width > MAX_IMAGE_EDGE or height > MAX_IMAGE_EDGE:
        raise IntakeSecurityError(f"knowledge_base_image_dimensions_exceeded: {label}")
    if width * height > MAX_IMAGE_PIXELS:
        raise IntakeSecurityError(f"knowledge_base_image_pixels_exceeded: {label}")


def validate_raster_image(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                width, height = int(image.width), int(image.height)
                validate_image_dimensions(width, height, path.name)
                image.verify()
                return width, height
    except IntakeSecurityError:
        raise
    except Exception as exc:
        raise IntakeSecurityError(f"knowledge_base_image_unreadable: {path.name}") from exc


def validate_declared_format(path: Path, *, budget: IntakeBudget | None = None) -> None:
    suffix = path.suffix.casefold()
    try:
        with path.open("rb") as handle:
            header = handle.read(32)
    except OSError as exc:
        raise IntakeSecurityError(f"knowledge_base_item_unreadable: {path.name}") from exc
    if suffix == ".pdf" and not header.startswith(b"%PDF-"):
        raise IntakeSecurityError(f"knowledge_base_format_mismatch: {path.name}")
    if suffix in OOXML_REQUIRED_MEMBERS:
        if not header.startswith(b"PK"):
            raise IntakeSecurityError(f"knowledge_base_format_mismatch_or_encrypted_office: {path.name}")
        validate_ooxml(path, suffix, budget=budget)
    if suffix == ".xls" and not header.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise IntakeSecurityError(f"knowledge_base_format_mismatch: {path.name}")
    if suffix == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
        raise IntakeSecurityError(f"knowledge_base_format_mismatch: {path.name}")
    if suffix in {".jpg", ".jpeg"} and not header.startswith(b"\xff\xd8\xff"):
        raise IntakeSecurityError(f"knowledge_base_format_mismatch: {path.name}")
    if suffix == ".webp" and not (header.startswith(b"RIFF") and header[8:12] == b"WEBP"):
        raise IntakeSecurityError(f"knowledge_base_format_mismatch: {path.name}")
    if suffix in {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".html", ".htm"}:
        if b"\x00" in header:
            raise IntakeSecurityError(f"knowledge_base_format_mismatch: {path.name}")


def validate_material(
    path: Path, *, budget: IntakeBudget | None = None,
) -> tuple[int | None, int | None]:
    validate_declared_format(path, budget=budget)
    suffix = path.suffix.casefold()
    if suffix == ".svg":
        return validate_svg(path)
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return validate_raster_image(path)
    return None, None


def enforce_text_budget(value: str, *, label: str) -> str:
    if len(value) > MAX_EXTRACTED_TEXT_CHARS_PER_FILE:
        raise IntakeSecurityError(f"knowledge_base_extracted_text_exceeded: {label}")
    return value


__all__ = [
    "IntakeSecurityError",
    "IntakeBudget",
    "MAX_COMPRESSION_RATIO",
    "MAX_EXTRACTED_TEXT_CHARS_PER_FILE",
    "MAX_EXTRACTED_TEXT_CHARS_PER_JOB",
    "MAX_IMAGE_EDGE",
    "MAX_IMAGE_PIXELS",
    "MAX_INPUT_BYTES",
    "MAX_INPUT_FILES",
    "MAX_PDF_PAGES",
    "MAX_PPTX_SLIDES",
    "MAX_SPREADSHEET_NONEMPTY_CELLS",
    "MAX_SPREADSHEET_SHEETS",
    "MAX_TOTAL_BYTES",
    "enforce_text_budget",
    "freeze_regular_file",
    "freeze_directory_tree",
    "path_has_symlink_component",
    "validate_declared_format",
    "validate_directory_tree",
    "validate_image_dimensions",
    "validate_material",
    "validate_ooxml",
    "validate_raster_image",
    "validate_svg",
    "validate_zip_infos",
]
