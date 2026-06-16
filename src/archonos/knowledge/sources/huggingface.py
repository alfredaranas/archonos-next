"""Hugging Face source — 1M+ models, datasets, and spaces on huggingface.co.

API: REST JSON, no auth, no rate limit for read-only requests.
https://huggingface.co/docs/api-reference

Endpoints used:
    https://huggingface.co/api/models/{repo_id}      one model, JSON
    https://huggingface.co/api/datasets/{repo_id}    one dataset, JSON
    https://huggingface.co/api/spaces/{repo_id}      one space, JSON
    https://huggingface.co/api/models?search=...&limit=...   free-text search
    https://huggingface.co/api/datasets?search=...&limit=...

Identifier forms:
    hf:meta-llama/Llama-3-70B              model
    hf:meta-llama/Llama-3-70B:dataset      dataset (when same id exists for both)
    hf:meta-llama/Llama-3-70B:space        space
    https://huggingface.co/<repo_id>        model by URL
    model:meta-llama/Llama-3-70B           explicit prefix
    dataset:squad                          explicit prefix
    space:gradio/gradio                    explicit prefix

The HF API returns very rich JSON: tags, pipeline_tag, downloads, likes,
model card text (often README.md rendered as markdown), config, etc.
This module captures the human-meaningful fields and renders the README
into the document content so it chunks well.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from archonos.knowledge.sources.base import Document, SourceError
from archonos.knowledge.sources.http import get_json, DEFAULT_UA, HTTPError as HTTPHelperError

HF_API = "https://huggingface.co/api"


def _get(path: str) -> dict:
    """GET an HF API endpoint. Returns parsed JSON."""
    url = HF_API + path
    try:
        return get_json(url)
    except HTTPHelperError as e:
        if e.status in (401, 403, 404):
            raise SourceError(f"Hugging Face: not found at {url} (HTTP {e.status})")
        if e.status == 429:
            raise SourceError(f"Hugging Face: rate-limited (try again later)")
        raise SourceError(f"Hugging Face: HTTP {e.status} for {url}")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise SourceError(f"Hugging Face: not found at {url} (HTTP {e.code})")
        if e.code == 429:
            raise SourceError(f"Hugging Face: rate-limited (try again later)")
        raise SourceError(f"Hugging Face: HTTP {e.code} for {url}")


def _strip_hf_prefix(identifier: str) -> tuple[str, str]:
    """Parse identifier into (kind, repo_id).

    Returns ('model', 'meta-llama/Llama-3-70B') for 'hf:meta-llama/Llama-3-70B'.
    Returns ('dataset', 'squad') for 'dataset:squad'.
    Returns ('model', 'meta-llama/Llama-3-70B') for 'meta-llama/Llama-3-70B' (default kind=model).
    Also handles a bare HF URL like 'https://huggingface.co/owner/name'.

    Identifier must be 'owner/name' (HF's canonical repo id). Bare names
    like 'bert-base-uncased' are rejected — use 'hf:google-bert/bert-base-uncased'.
    """
    s = identifier.strip()
    if s.startswith("hf:"):
        s = s[3:].strip()
    # Strip a bare HF URL down to the path
    if s.startswith("https://huggingface.co/") or s.startswith("http://huggingface.co/"):
        s = s.split("huggingface.co/", 1)[1]
    kind = "model"
    for prefix, k in (("model:", "model"), ("dataset:", "dataset"), ("space:", "space")):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
            kind = k
            break
    if "/" not in s:
        raise SourceError(
            f"Hugging Face: identifier {identifier!r} must be 'owner/name' "
            f"(e.g. 'hf:meta-llama/Llama-3-70B'). "
            f"Most models follow the 'organization/model-name' form."
        )
    return kind, s


def _fetch_readme(repo_id: str, kind: str) -> str:
    """Fetch the rendered README from a Hugging Face repo.

    Tries the raw markdown endpoint first, then falls back to the rendered
    HTML. Returns empty string if neither works.
    """
    branch = "main"
    for ext in ("md", ""):
        url = f"https://huggingface.co/{repo_id}/resolve/{branch}/README{'.md' if ext else ''}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
                if ext == "md":
                    return raw.decode("utf-8", errors="replace")
                # HTML — strip tags naively
                text = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", errors="replace"))
                text = re.sub(r"\s+", " ", text)
                return text
        except urllib.error.HTTPError:
            continue
        except Exception:
            continue
    return ""


def _format_model_content(data: dict, readme: str) -> str:
    """Render a model JSON into a chunkable text document."""
    parts = []
    parts.append(f"# {data.get('modelId') or data.get('id') or 'Hugging Face Model'}")
    parts.append("")
    if data.get("pipeline_tag"):
        parts.append(f"**Pipeline:** {data['pipeline_tag']}")
    if data.get("library_name"):
        parts.append(f"**Library:** {data['library_name']}")
    if data.get("tags"):
        tags = data["tags"][:25]  # cap so chunks stay small
        parts.append(f"**Tags:** {', '.join(tags)}")
    parts.append("")
    parts.append("## Stats")
    parts.append(f"- Downloads: {data.get('downloads', 0):,}")
    parts.append(f"- Likes: {data.get('likes', 0):,}")
    parts.append(f"- Last modified: {data.get('lastModified', 'unknown')}")
    parts.append("")
    if readme:
        parts.append("## Model Card")
        parts.append("")
        parts.append(readme[:4000])  # cap content for kernel
    return "\n".join(parts)


def _format_dataset_content(data: dict, readme: str) -> str:
    parts = []
    parts.append(f"# {data.get('id') or 'Hugging Face Dataset'}")
    parts.append("")
    if data.get("tags"):
        parts.append(f"**Tags:** {', '.join(data['tags'][:25])}")
    parts.append("")
    parts.append("## Stats")
    parts.append(f"- Downloads: {data.get('downloads', 0):,}")
    parts.append(f"- Likes: {data.get('likes', 0):,}")
    parts.append("")
    if readme:
        parts.append("## Dataset Card")
        parts.append("")
        parts.append(readme[:4000])
    return "\n".join(parts)


def _format_space_content(data: dict, readme: str) -> str:
    parts = []
    parts.append(f"# {data.get('id') or 'Hugging Face Space'}")
    parts.append("")
    if data.get("tags"):
        parts.append(f"**Tags:** {', '.join(data['tags'][:25])}")
    parts.append("")
    parts.append("## Stats")
    parts.append(f"- Likes: {data.get('likes', 0):,}")
    parts.append(f"- SDK: {data.get('sdk', 'unknown')}")
    parts.append("")
    if readme:
        parts.append("## Space README")
        parts.append("")
        parts.append(readme[:4000])
    return "\n".join(parts)


class HuggingFaceSource:
    scheme = "hf"
    base_url = "https://huggingface.co/api"
    name = "Hugging Face"

    def fetch(self, identifier: str) -> list[Document]:
        """Fetch one model, dataset, or space by repo_id."""
        kind, repo_id = _strip_hf_prefix(identifier)
        try:
            data = _get(f"/{kind}s/{repo_id}")
        except SourceError as e:
            # 404, 401, 403 all mean "we can't get this repo"
            if "not found" in str(e) or "rate-limited" in str(e):
                raise
            raise SourceError(f"Hugging Face: cannot fetch {kind} {repo_id!r}: {e}")

        readme = _fetch_readme(repo_id, kind)
        if kind == "model":
            content = _format_model_content(data, readme)
        elif kind == "dataset":
            content = _format_dataset_content(data, readme)
        else:
            content = _format_space_content(data, readme)

        size = len(content.encode("utf-8"))
        return [
            Document(
                source_path=f"https://huggingface.co/{repo_id}",
                title=data.get("modelId") or data.get("id") or repo_id,
                doc_type=f"hf_{kind}",
                content=content,
                byte_size=size,
                meta={
                    "kind": kind,
                    "repo_id": repo_id,
                    "downloads": data.get("downloads", 0),
                    "likes": data.get("likes", 0),
                    "tags": data.get("tags", [])[:25],
                    "pipeline_tag": data.get("pipeline_tag"),
                    "library_name": data.get("library_name"),
                },
            )
        ]

    def search(self, query: str, limit: int = 10) -> list[Document]:
        """Free-text search across HF models. Returns up to `limit` candidates."""
        if limit <= 0:
            return []
        # Search models only (datasets and spaces are typically browsed, not searched).
        params = {
            "search": query,
            "limit": str(min(limit, 30)),
        }
        url = HF_API + "/models?" + urllib.parse.urlencode(params)
        try:
            data = get_json(url)
        except urllib.error.HTTPError as e:
            raise SourceError(f"Hugging Face: search HTTP {e.code}")

        docs = []
        for item in data[:limit]:
            repo_id = item.get("modelId") or item.get("id")
            if not repo_id:
                continue
            content = (
                f"# {repo_id}\n\n"
                f"**Pipeline:** {item.get('pipeline_tag', 'unknown')}\n"
                f"**Library:** {item.get('library_name', 'unknown')}\n"
                f"**Downloads:** {item.get('downloads', 0):,}\n"
                f"**Likes:** {item.get('likes', 0):,}\n\n"
                f"Tags: {', '.join((item.get('tags') or [])[:15])}\n\n"
                f"Source: https://huggingface.co/{repo_id}\n"
            )
            docs.append(Document(
                source_path=f"https://huggingface.co/{repo_id}",
                title=repo_id,
                doc_type="hf_model_search_result",
                content=content,
                byte_size=len(content.encode("utf-8")),
                meta={
                    "kind": "model",
                    "repo_id": repo_id,
                    "downloads": item.get("downloads", 0),
                    "pipeline_tag": item.get("pipeline_tag"),
                },
            ))
        return docs
