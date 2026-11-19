"""Read-only copy & SHA-256 integrity helpers for real Mock PBIP models."""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Iterable

MOCK_PROJECTS: dict[str, tuple[str, str]] = {
    "finance": ("1_finance_Aevum", "Finance.pbip"),
    "sales": ("2_sales_Veloce", "Sales.pbip"),
    "ecommerce": ("3_ecommerce_NexusCohort", "Ecommerce.pbip"),
    "hr": ("4_hr_EquitasTrust", "HR.pbip"),
    "supply_chain": ("5_supply_chain_OrionRoute", "SupplyChain.pbip"),
    "manufacturing": ("6_manufacturing", "Manufacturing.pbip"),
    "healthcare": ("7_healthcare_AetherFlow", "Healthcare.pbip"),
}


def mock_data_root() -> Path:
    """Return the configured Mock data root directory without mutating it."""
    override = os.environ.get("PBIBRAIN_MOCK_DATA_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / "Desktop" / "Mock data"


def has_mock_data() -> bool:
    """Return True when the Mock data directory and at least Finance.pbip exist."""
    root = mock_data_root()
    return (root / "1_finance_Aevum" / "Finance.pbip").is_file()


def resolve_mock_project(name_or_folder: str) -> tuple[Path, Path]:
    """Return the read-only source (project_dir, pbip_path) for a mock project."""
    key = name_or_folder.strip().lower()
    if key in MOCK_PROJECTS:
        folder, pbip_name = MOCK_PROJECTS[key]
    else:
        matched = next(
            ((f, p) for f, p in MOCK_PROJECTS.values() if f.lower() == key),
            None,
        )
        if matched is None:
            raise KeyError(f"Unknown mock PBIP project: {name_or_folder!r}")
        folder, pbip_name = matched
    proj_dir = mock_data_root() / folder
    pbip_path = proj_dir / pbip_name
    if not pbip_path.is_file():
        raise FileNotFoundError(f"Mock PBIP project missing: {pbip_path}")
    return proj_dir, pbip_path


def dir_sha256_manifest(
    root: Path,
    *,
    ignore_dirs: Iterable[str] = (),
) -> dict[str, str]:
    """Return a sorted relative POSIX path -> SHA-256 digest map for all files under root."""
    ignored = frozenset(ignore_dirs)
    manifest: dict[str, str] = {}
    if not root.exists():
        return manifest
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in ignored)
        cur_path = Path(current)
        for fname in sorted(filenames):
            fpath = cur_path / fname
            if fpath.is_symlink():
                continue
            rel = fpath.relative_to(root).as_posix()
            digest = hashlib.sha256(fpath.read_bytes()).hexdigest()
            manifest[rel] = digest
    return manifest


def pbip_sha256_manifest(project_dir: Path) -> dict[str, str]:
    """Hash only the .pbip file and top-level *.SemanticModel / *.Report folders."""
    out: dict[str, str] = {}
    for entry in sorted(project_dir.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_file() and entry.suffix.lower() == ".pbip":
            out[entry.name] = hashlib.sha256(entry.read_bytes()).hexdigest()
        elif entry.is_dir() and (
            entry.name.endswith(".SemanticModel") or entry.name.endswith(".Report")
        ):
            for rel, digest in dir_sha256_manifest(entry).items():
                out[f"{entry.name}/{rel}"] = digest
    return out


def copy_mock_project(
    name_or_folder: str,
    dest_root: Path,
    *,
    dest_name: str = "",
    pbip_only: bool = True,
    include_pbibrain: bool = False,
) -> tuple[Path, Path]:
    """Copy a mock PBIP project into dest_root without ever mutating Mock data."""
    src_dir, src_pbip = resolve_mock_project(name_or_folder)
    target_dir = dest_root / (dest_name or src_dir.name)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    if pbip_only:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_pbip, target_dir / src_pbip.name)
        for entry in src_dir.iterdir():
            if entry.is_dir() and (
                entry.name.endswith(".SemanticModel") or entry.name.endswith(".Report")
            ):
                shutil.copytree(entry, target_dir / entry.name)
            elif include_pbibrain and entry.is_dir() and entry.name == ".pbibrain":
                shutil.copytree(entry, target_dir / entry.name)
    else:
        ignore = [] if include_pbibrain else [".pbibrain", ".git", "__pycache__"]
        shutil.copytree(
            src_dir,
            target_dir,
            ignore=shutil.ignore_patterns(*ignore) if ignore else None,
        )
    return target_dir, target_dir / src_pbip.name
