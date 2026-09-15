"""Cloudinary helpers used when a stored document is removed."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

import cloudinary.uploader


def public_id_from_url(url: str) -> str:
    """Extract a Cloudinary image public ID from a delivery URL."""
    path_parts = [unquote(part) for part in urlparse(url).path.split("/") if part]
    try:
        upload_index = path_parts.index("upload")
    except ValueError as exc:
        raise ValueError("URL is not a Cloudinary upload URL") from exc

    asset_parts = path_parts[upload_index + 1 :]
    version_index = next(
        (index for index, part in enumerate(asset_parts) if part[1:].isdigit() and part.startswith("v")),
        None,
    )
    if version_index is not None:
        asset_parts = asset_parts[version_index + 1 :]

    if not asset_parts:
        raise ValueError("Cloudinary URL does not contain an asset public ID")

    asset_parts[-1] = PurePosixPath(asset_parts[-1]).stem
    return "/".join(asset_parts)


def delete_document_assets(urls: list[str]) -> None:
    """Delete all unique document images, failing if Cloudinary rejects one."""
    public_ids = {public_id_from_url(url) for url in urls if url}

    def destroy(public_id: str) -> None:
        response = cloudinary.uploader.destroy(
            public_id,
            resource_type="image",
            invalidate=True,
        )
        result = response.get("result")
        if result not in {"ok", "not found"}:
            raise RuntimeError(f"Cloudinary could not delete {public_id}: {result}")

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(public_ids)))) as executor:
        list(executor.map(destroy, public_ids))
