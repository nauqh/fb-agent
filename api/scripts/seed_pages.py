"""One-off: seed `page` rows from the old system. Delete this after Phase 1.

Three sources, because no single one has everything:

  Supabase `facebook_post_templates`   the prompts and the quota
  Metricool `/admin/simpleProfiles`    blog id, and the page's real name
  Supabase Storage `facebook-media`    the watermark image files

Of the old table's 54 columns, five are carried. The rest are dropped, not
migrated — see docs/data-model.md#layout-is-config-not-data.

Two things this script does *not* do verbatim:

  `image_gen_system_prompt` is split. Only the page-specific opening block is
  stored; the 2030 shared characters live in app/writer/prompts.py. History
  Retraced had NULL here and fell through to a code constant, so its block is
  embedded below.

  Idempotent by `facebook_page_id`: re-running updates rather than duplicates,
  and never clobbers an edit made in Settings with a stale Supabase value
  unless --force is passed.

Usage:
    uv run python scripts/seed_pages.py            # dry run, prints the plan
    uv run python scripts/seed_pages.py --apply
    uv run python scripts/seed_pages.py --apply --force
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_engine, init_db  # noqa: E402
from app.models import Page  # noqa: E402
from app.settings import API_DIR, settings  # noqa: E402

METRICOOL_BASE = "https://app.metricool.com/api"
STORAGE_BUCKET = "facebook-media"

# The four with real production volume: 226 / 51 / 50 / 15 drafts, and the only
# four still producing in the last fortnight. The other six seed inactive.
ACTIVE_PAGE_NAMES = {
    "History Retraced",
    "The Fact Feed",
    "Hot Tub Timeout",
    "Bible Focus",
}

# History Retraced stored NULL for image_gen_system_prompt and resolved to
# HR_IMAGE_GEN_SYSTEM_PROMPT in src/lib/facebook/prompts/image-gen.ts:30. This
# is that constant's page-specific head; the shared tail is in writer/prompts.py.
HR_IMAGE_PROMPT_FALLBACK = """You generate the top hero photograph for a History Retraced Facebook post card.

Visual style — MANDATORY:
- 100% photorealistic photograph. It must look like a real photo from a camera, NOT illustration or digital painting.
- Mid-shot / medium close-up with a clear focal face or figure in the foreground.
- Documentary or cinematic historical reenactment photography: believable environment (battlefield, city, interior, landscape).
- Dramatic but natural lighting (golden hour, overcast, torchlight); no neon, no magic glow, no fire heads, no supernatural effects.
- One grounded historical moment — factual tone, not fantasy or surreal symbolism."""

SHARED_BLOCK_MARKER = "Final post card assembly"


def require(name: str, value: str) -> str:
    if not value:
        sys.exit(f"{name} is not set in .env — cannot seed.")
    return value


def fetch_templates() -> list[dict]:
    url = require("SUPABASE_URL", settings.supabase_url).rstrip("/")
    key = require("SUPABASE_SERVICE_ROLE_KEY", settings.supabase_service_role_key)
    response = httpx.get(
        f"{url}/rest/v1/facebook_post_templates",
        params={"select": "*"},
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=30,
    )
    response.raise_for_status()
    return [row for row in response.json() if row.get("page_id")]


def fetch_metricool_profiles() -> dict[str, dict]:
    """Facebook page id -> {blog_id, label}."""
    token = require("METRICOOL_API_TOKEN", settings.metricool_api_token)
    user_id = require("METRICOOL_USER_ID", settings.metricool_user_id)
    response = httpx.get(
        f"{METRICOOL_BASE}/admin/simpleProfiles",
        params={"userId": user_id},
        headers={"X-Mc-Auth": token},
        timeout=30,
    )
    response.raise_for_status()

    profiles: dict[str, dict] = {}
    for row in response.json():
        # resolveFacebookPageId(): facebookPageId first, then facebook.
        page_id = str(row.get("facebookPageId") or row.get("facebook") or "").strip()
        if page_id:
            profiles[page_id] = {
                "blog_id": str(row.get("id") or ""),
                "label": (row.get("label") or "").strip(),
            }
    return profiles


def download_watermark(storage_path: str) -> str | None:
    """Pull the logo out of Supabase Storage onto local disk.

    Stored as `media/watermarks/<page>.<ext>` and referenced relative to
    media_root, so the path survives the eventual move to hosted storage.
    """
    url = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_role_key
    response = httpx.get(
        f"{url}/storage/v1/object/{STORAGE_BUCKET}/{storage_path}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=60,
        follow_redirects=True,
    )
    if response.status_code != 200:
        print(f"    ! watermark {storage_path} -> HTTP {response.status_code}")
        return None

    target = Path(settings.media_root) / "watermarks" / Path(storage_path).name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)
    return str(target.relative_to(settings.media_root)).replace("\\", "/")


def page_specific_image_prompt(stored: str | None, page_name: str) -> str:
    """Keep the opening block, drop the 2030 shared characters."""
    if not stored or not stored.strip():
        if page_name == "History Retraced":
            return HR_IMAGE_PROMPT_FALLBACK
        return ""
    head, marker, _ = stored.partition(SHARED_BLOCK_MARKER)
    if not marker:
        # No shared block found — an edited prompt. Keep it whole.
        return stored.strip()
    return head.strip()


def build_rows(apply: bool) -> list[dict]:
    templates = fetch_templates()
    profiles = fetch_metricool_profiles()
    print(f"templates: {len(templates)}   metricool facebook profiles: {len(profiles)}")

    rows = []
    for template in templates:
        facebook_page_id = str(template["page_id"])
        profile = profiles.get(facebook_page_id)
        if profile is None:
            print(f"  ! {template.get('page_name')} not in Metricool — skipped")
            continue

        name = profile["label"] or template.get("page_name") or facebook_page_id
        watermark = None
        if template.get("portrait_image_path"):
            watermark = (
                download_watermark(template["portrait_image_path"]) if apply else "…"
            )

        rows.append(
            {
                "facebook_page_id": facebook_page_id,
                "name": name,
                "metricool_blog_id": profile["blog_id"],
                "is_active": name in ACTIVE_PAGE_NAMES,
                "daily_quota": template.get("daily_quota") or 12,
                "system_prompt": (template.get("system_prompt") or "").strip(),
                "overlay_prompt": (template.get("text_overlay_prompt") or "").strip(),
                "image_prompt": page_specific_image_prompt(
                    template.get("image_gen_system_prompt"), name
                ),
                "watermark_image_path": watermark,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write to the database")
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite prompts on pages that already exist",
    )
    args = parser.parse_args()

    rows = build_rows(apply=args.apply)
    print()

    if not args.apply:
        for row in rows:
            mark = "*" if row["is_active"] else " "
            print(
                f" {mark} {row['name'][:30]:<30} blog={row['metricool_blog_id']:<9} "
                f"quota={row['daily_quota']:<3} sys={len(row['system_prompt']):<5} "
                f"overlay={len(row['overlay_prompt']):<5} "
                f"img={len(row['image_prompt']):<5} "
                f"wm={'yes' if row['watermark_image_path'] else '-'}"
            )
        print(f"\ndry run: {len(rows)} pages, {sum(r['is_active'] for r in rows)} active")
        print("re-run with --apply to write")
        return

    init_db()
    created = updated = skipped = 0
    with Session(get_engine()) as session:
        for row in rows:
            existing = session.exec(
                select(Page).where(Page.facebook_page_id == row["facebook_page_id"])
            ).first()

            if existing is None:
                session.add(Page(**row))
                created += 1
                continue

            if not args.force:
                skipped += 1
                continue

            for field, value in row.items():
                setattr(existing, field, value)
            existing.updated_at = datetime.now(timezone.utc)
            session.add(existing)
            updated += 1

        session.commit()

    print(f"created {created}   updated {updated}   left alone {skipped}")
    if skipped:
        print("(--force to overwrite existing rows, including Settings edits)")


if __name__ == "__main__":
    main()
