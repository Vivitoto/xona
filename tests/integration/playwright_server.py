from __future__ import annotations

import argparse
import base64
import hashlib
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response


REDACTED = "********"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def create_app() -> FastAPI:
    state = FixtureState()
    app = FastAPI(title="Xona Playwright Fixture")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "fixture": True}

    @app.post("/api/e2e/reset")
    async def reset_fixture() -> dict[str, Any]:
        return state.reset()

    @app.get("/api/e2e/assets/{asset_name:path}")
    async def fixture_asset(asset_name: str) -> Response:
        if asset_name not in state.assets:
            raise HTTPException(status_code=404, detail="Asset not found")
        return Response(content=state.assets[asset_name], media_type="image/png")

    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        return state.settings

    @app.put("/api/settings")
    async def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
        deep_merge(state.settings, payload)
        return state.settings

    @app.post("/api/settings/templates/preview")
    async def preview_templates(payload: dict[str, Any]) -> dict[str, Any]:
        folder_templates = payload.get("folder_templates") or []
        filename_template = payload.get("filename_template") or "{title}"
        context = payload.get("context") or {}
        rendered_parts = [
            render_template(str(template), context)
            for template in folder_templates
            if str(template).strip()
        ]
        return {
            "folder_path": "/".join(rendered_parts) if rendered_parts else None,
            "filename": render_template(str(filename_template), context),
            "validation_errors": [],
            "warnings": [],
        }

    @app.post("/api/settings/flaresolverr/test")
    async def test_flaresolverr(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "status_code": 200,
            "elapsed_ms": 3,
            "cloudflare_state": "fixture-ok",
            "cookie_count": 1,
            "diagnostics": {
                "endpoint": payload.get("url"),
                "proxy_url": redact_url(payload.get("proxy_url")),
            },
        }

    @app.post("/api/settings/xchina/test")
    async def test_xchina(payload: dict[str, Any]) -> dict[str, Any]:
        query = payload.get("query") or "sample"
        return {"ok": True, "candidate_count": 1, "diagnostics": {"query": query}}

    @app.post("/api/emby/test")
    async def test_emby(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "server": payload.get("server_url"),
            "diagnostics": {"api_key": REDACTED},
        }

    @app.get("/api/storage-roots/browse")
    async def browse_storage_roots(root_id: int = 1, path: str = "") -> dict[str, Any]:
        if root_id != 1:
            raise HTTPException(status_code=404, detail="Storage root not found")
        root = Path(state.paths["media_root"])
        browse_path = Path(path) if path else root
        if not is_inside(browse_path, root):
            raise HTTPException(status_code=400, detail="Path outside fixture root")
        entries = [
            {
                "name": child.name,
                "path": str(child),
                "is_dir": child.is_dir(),
            }
            for child in sorted(browse_path.iterdir(), key=lambda item: item.name)
        ]
        return {
            "root": {
                "id": 1,
                "path": str(root),
                "source": "playwright-fixture",
                "enabled": True,
            },
            "entries": entries,
        }

    @app.post("/api/manual/scan")
    async def manual_scan(payload: dict[str, Any]) -> dict[str, Any]:
        directory = Path(str(payload.get("directory") or ""))
        if not directory.is_dir() or not is_inside(directory, Path(state.paths["media_root"])):
            raise HTTPException(status_code=400, detail="Fixture source directory required")
        recursive = bool(payload.get("recursive", True))
        iterator = directory.rglob("*") if recursive else directory.iterdir()
        files = [
            item
            for item in iterator
            if item.is_file() and item.suffix.lower() in {".mkv", ".mp4"}
        ]
        jobs = [state.create_manual_job(item) for item in sorted(files)]
        return {
            "scanned_count": len(jobs),
            "jobs": [
                {
                    "job_id": job["id"],
                    "state": job["state"],
                    "media_identity": job["media_identity"],
                    "media_items": job["media_items"],
                }
                for job in jobs
            ],
        }

    @app.post("/api/manual/search")
    async def manual_search(payload: dict[str, Any]) -> dict[str, Any]:
        job = state.job_or_404(int(payload.get("job_id") or 0))
        normalized_query = str(
            payload.get("normalized_query")
            or normalize_query(str(payload.get("filename") or job["media_identity"]))
        )
        candidates = state.manual_candidates(normalized_query)
        job["state"] = "candidate_found"
        job["selected_candidate"] = None
        job["payload"]["manual"]["candidates"] = candidates
        state.add_event(job["id"], "scanned", "candidate_found", {"query": normalized_query})
        return {
            "job_id": job["id"],
            "search_query_id": 700 + job["id"],
            "query": normalized_query,
            "normalized_query": normalized_query,
            "candidates": candidates,
        }

    @app.post("/api/manual/jobs/{job_id}/select-candidate")
    async def select_manual_candidate(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        job = state.job_or_404(job_id)
        candidate = state.find_candidate(job, payload.get("candidate_id"))
        safety = payload.get("safety") or {}
        reasons = [key for key, enabled in safety.items() if enabled]
        accepted = not reasons
        job["state"] = "ready" if accepted else "review_required"
        job["selected_candidate"] = candidate
        job["gate_reasons"] = reasons
        job["payload"]["manual"]["selected_detail"] = {
            "source_id": candidate["source_candidate_id"],
            "title": candidate["title"],
            "source_url": candidate["url"],
        }
        job["payload"]["manual"]["selection_refusal_reasons"] = reasons
        state.add_event(
            job_id,
            "candidate_found",
            job["state"],
            {"source_url": candidate["url"], "api_key": REDACTED, "reasons": reasons},
        )
        return {
            "job_id": job_id,
            "accepted": accepted,
            "reasons": reasons,
            "selected_candidate": candidate,
            "metadata_record_id": 900 + job_id,
            "metadata": state.metadata_record(candidate),
        }

    @app.post("/api/manual/jobs/{job_id}/preview")
    async def preview_manual_plan(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        job = state.job_or_404(job_id)
        destination_root = Path(str(payload.get("destination_root") or state.paths["destination_dir"]))
        if not is_inside(destination_root, Path(state.paths["media_root"])):
            raise HTTPException(status_code=400, detail="Destination must stay inside fixture root")
        plan = state.create_plan(job, destination_root, payload)
        return {
            "job_id": job_id,
            "plan_id": plan["plan_id"],
            "metadata": state.metadata_record(job["selected_candidate"]),
            "materialized_assets": plan["materialized_assets"],
            "missing_assets": [],
            "plan": plan["plan"],
        }

    @app.post("/api/manual/jobs/{job_id}/organize")
    async def organize_manual_job(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        job = state.job_or_404(job_id)
        destination_root = Path(str(payload.get("destination_root") or state.paths["destination_dir"]))
        if not is_inside(destination_root, Path(state.paths["media_root"])):
            raise HTTPException(status_code=400, detail="Destination must stay inside fixture root")
        safe_payload = {**payload, "mode": "copy" if payload.get("mode") == "preview" else payload.get("mode", "copy")}
        plan_entry = state.create_plan(job, destination_root, safe_payload)
        state.execute_plan(plan_entry)
        return {
            "plan_id": plan_entry["plan_id"],
            "job_id": plan_entry["job_id"],
            "state": plan_entry["status"],
        }

    @app.post("/api/manual/plans/{plan_id}/execute")
    async def execute_manual_plan(plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        plan_entry = state.plans.get(plan_id)
        if plan_entry is None:
            raise HTTPException(status_code=404, detail="Plan not found")
        if payload.get("plan_version") != plan_entry["plan"]["version"]:
            raise HTTPException(status_code=409, detail="Plan version mismatch")
        state.execute_plan(plan_entry)
        return {
            "plan_id": plan_id,
            "job_id": plan_entry["job_id"],
            "state": plan_entry["status"],
        }

    @app.get("/api/jobs")
    async def list_jobs(state_filter: str | None = None, state_query: str | None = None, state: str | None = None) -> dict[str, Any]:
        requested_state = state_filter or state_query or state
        jobs = list(app.state.fixture.jobs.values())
        if requested_state:
            jobs = [job for job in jobs if job["state"] == requested_state]
        return {"jobs": [public_job(job) for job in jobs]}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: int) -> dict[str, Any]:
        return public_job(state.job_or_404(job_id))

    @app.get("/api/jobs/{job_id}/events")
    async def get_job_events(job_id: int) -> dict[str, Any]:
        state.job_or_404(job_id)
        return {"events": state.events.get(job_id, [])}

    @app.post("/api/jobs/{job_id}/retry")
    async def retry_job(job_id: int) -> dict[str, Any]:
        job = state.job_or_404(job_id)
        previous = job["state"]
        job["state"] = "searching"
        job["attempts"] += 1
        state.add_event(job_id, previous, "searching", {"token": REDACTED, "action": "retry"})
        return {"job": public_job(job)}

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: int) -> dict[str, Any]:
        job = state.job_or_404(job_id)
        previous = job["state"]
        job["state"] = "cancelled"
        state.add_event(job_id, previous, "cancelled", {"cancelled_by": "playwright"})
        return {"job": public_job(job)}

    @app.post("/api/jobs/{job_id}/retry-emby")
    async def retry_emby(job_id: int) -> dict[str, Any]:
        job = state.job_or_404(job_id)
        previous = job["state"]
        job["state"] = "completed"
        state.add_event(job_id, previous, "completed", {"api_key": REDACTED})
        return {"job": public_job(job)}

    @app.get("/api/history/plans")
    async def list_history_plans() -> dict[str, Any]:
        return {"plans": state.history_plans}

    @app.post("/api/plans/{plan_id}/rollback")
    async def rollback_plan(plan_id: str) -> dict[str, Any]:
        for plan in state.history_plans:
            if plan["plan_id"] == plan_id:
                plan["status"] = "rolled_back"
                return {
                    "plan_id": plan_id,
                    "status": "rolled_back",
                    "reversed_steps": ["copy-media"],
                    "refusal_reason": None,
                }
        raise HTTPException(status_code=404, detail="Plan not found")

    @app.get("/api/watch-rules")
    async def list_watch_rules() -> dict[str, Any]:
        return {"rules": list(state.watch_rules.values())}

    @app.post("/api/watch-rules", status_code=201)
    async def create_watch_rule(payload: dict[str, Any]) -> dict[str, Any]:
        rule_id = f"rule-{state.next_rule_id}"
        state.next_rule_id += 1
        rule = watch_rule_from_payload(rule_id, payload)
        state.watch_rules[rule_id] = rule
        return rule

    @app.put("/api/watch-rules/{rule_id}")
    async def update_watch_rule(rule_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if rule_id not in state.watch_rules:
            raise HTTPException(status_code=404, detail="Watch rule not found")
        state.watch_rules[rule_id] = watch_rule_from_payload(rule_id, payload)
        return state.watch_rules[rule_id]

    @app.post("/api/watch-rules/{rule_id}/scan-now")
    async def scan_watch_rule_now(rule_id: str) -> dict[str, Any]:
        rule = state.watch_rules.get(rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="Watch rule not found")
        job = state.create_review_job(rule_id=rule_id, identity="Monitor review item")
        return {"rule_id": rule_id, "enqueued_jobs": [job["id"]]}

    @app.get("/api/actors")
    async def list_actors(search: str | None = None, missing_image: bool = False) -> dict[str, Any]:
        actors = list(state.actors.values())
        if search:
            needle = search.lower()
            actors = [
                actor
                for actor in actors
                if needle in actor["canonical_name"].lower()
                or any(needle in alias.lower() for alias in actor["aliases"])
            ]
        if missing_image:
            actors = [
                actor
                for actor in actors
                if not actor.get("portrait_cache_path") and not actor.get("portrait_source_url")
            ]
        return {"actors": actors}

    @app.put("/api/actors/{actor_id}/aliases")
    async def update_actor_aliases(actor_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        actor = state.actor_or_404(actor_id)
        actor["aliases"] = [str(alias) for alias in payload.get("aliases", [])]
        return actor

    @app.post("/api/actors/{actor_id}/portrait")
    async def replace_actor_portrait(actor_id: int, request: Request) -> dict[str, Any]:
        actor = state.actor_or_404(actor_id)
        content = await request.body()
        digest = hashlib.sha256(content).hexdigest()
        asset_name = f"actor-{actor_id}-uploaded.png"
        state.assets[asset_name] = content or PNG_1X1
        actor["portrait_cache_path"] = str(Path(state.paths["asset_dir"]) / asset_name)
        actor["portrait_source_url"] = f"/api/e2e/assets/{asset_name}"
        actor["portrait_sha256"] = digest
        actor["portrait_size_bytes"] = len(content)
        return {"actor": actor, "sha256": digest, "size_bytes": len(content)}

    @app.post("/api/actors/{actor_id}/refresh")
    async def refresh_actor(actor_id: int) -> dict[str, Any]:
        actor = state.actor_or_404(actor_id)
        actor["biography"] = "Refreshed synthetic biography."
        return {"actor": actor, "diagnostics": {"source": "fixture"}}

    @app.get("/api/actors/{actor_id}/works")
    async def actor_works(actor_id: int) -> dict[str, Any]:
        actor = state.actor_or_404(actor_id)
        return {"actor_id": actor_id, "works": actor["linked_works"]}

    @app.post("/api/actors/{actor_id}/sync-emby")
    async def sync_actor_emby(actor_id: int) -> dict[str, Any]:
        actor = state.actor_or_404(actor_id)
        actor["emby_person_id"] = f"emby-person-{actor_id}"
        return {
            "actor": actor,
            "uploaded_portrait": bool(actor.get("portrait_source_url")),
            "diagnostics": {"api_key": REDACTED, "server_url": "http://emby.fixture.local"},
        }

    app.state.fixture = state
    return app


class FixtureState:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="xona-playwright-")
        self.base_dir = Path(self._tmp.name)
        self.generation = 0
        self.assets: dict[str, bytes] = {}
        self.settings: dict[str, Any] = {}
        self.jobs: dict[int, dict[str, Any]] = {}
        self.events: dict[int, list[dict[str, Any]]] = {}
        self.plans: dict[str, dict[str, Any]] = {}
        self.history_plans: list[dict[str, Any]] = []
        self.watch_rules: dict[str, dict[str, Any]] = {}
        self.actors: dict[int, dict[str, Any]] = {}
        self.paths: dict[str, str] = {}
        self.next_job_id = 1
        self.next_event_id = 1
        self.next_plan_id = 1
        self.next_rule_id = 1
        self.reset()

    def reset(self) -> dict[str, Any]:
        self.generation += 1
        run_dir = self.base_dir / f"run-{self.generation}"
        if run_dir.exists():
            shutil.rmtree(run_dir)
        media_root = run_dir / "media"
        source_dir = media_root / "incoming"
        nested_destination_dir = source_dir / "organized"
        destination_dir = media_root / "organized"
        config_dir = run_dir / "config"
        asset_dir = run_dir / "assets"
        for directory in (
            source_dir,
            nested_destination_dir,
            destination_dir,
            config_dir / "xchina-cache",
            config_dir / "safety-cache",
            asset_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        sample_file = source_dir / "Sample.Work.Alpha.2026.mkv"
        sample_file.write_bytes(b"synthetic media bytes")
        ignored_file = source_dir / "ignore.tmp"
        ignored_file.write_text("ignored", encoding="utf-8")

        self.assets = {
            "candidate-poster.png": PNG_1X1,
            "actor-present.png": PNG_1X1,
        }
        self.paths = {
            "run_dir": str(run_dir),
            "media_root": str(media_root),
            "source_dir": str(source_dir),
            "destination_dir": str(destination_dir),
            "nested_destination_dir": str(nested_destination_dir),
            "config_dir": str(config_dir),
            "asset_dir": str(asset_dir),
            "xchina_cache_dir": str(config_dir / "xchina-cache"),
            "safety_cache_dir": str(config_dir / "safety-cache"),
            "sample_file": str(sample_file),
        }
        self.settings = default_settings(self.paths)
        self.jobs = {}
        self.events = {}
        self.plans = {}
        self.history_plans = [self.seed_history_plan()]
        self.watch_rules = {}
        self.actors = self.seed_actors()
        self.next_job_id = 1
        self.next_event_id = 1
        self.next_plan_id = 1
        self.next_rule_id = 1
        review = self.create_review_job(rule_id="rule-seeded", identity="Review.Required.Work.2026")
        self.paths["review_job_id"] = str(review["id"])
        return self.fixture_info()

    def fixture_info(self) -> dict[str, Any]:
        return {
            **self.paths,
            "review_job_id": int(self.paths["review_job_id"]),
            "history_plan_id": self.history_plans[0]["plan_id"],
        }

    def seed_history_plan(self) -> dict[str, Any]:
        target = Path(self.paths["destination_dir"]) / "Studio One" / "Archived Work" / "XC-000 - Archived Work.mkv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"archived media bytes")
        return {
            "plan_id": "hist-plan-1",
            "job_id": 99,
            "mode": "copy",
            "status": "completed",
            "verification_status": "verified",
            "target_paths": [str(target)],
            "created_at": now(),
        }

    def seed_actors(self) -> dict[int, dict[str, Any]]:
        return {
            1: actor_read(
                1,
                "Aiko Fixture",
                aliases=["A. Fixture"],
                portrait_source_url=None,
                portrait_cache_path=None,
                emby_person_id=None,
            ),
            2: actor_read(
                2,
                "Mina Complete",
                aliases=["Mina C."],
                portrait_source_url="/api/e2e/assets/actor-present.png",
                portrait_cache_path=str(Path(self.paths["asset_dir"]) / "actor-present.png"),
                emby_person_id="emby-person-2",
            ),
        }

    def create_manual_job(self, path: Path) -> dict[str, Any]:
        stat = path.stat()
        job_id = self.next_job_id
        self.next_job_id += 1
        job = job_summary(
            job_id,
            state="scanned",
            media_identity=normalize_query(path.stem),
            rule_id=None,
            manual=True,
            payload={"manual": {"source_path": str(path)}},
        )
        job["media_items"] = [
            {
                "path": str(path),
                "group_key": path.stem,
                "identity": normalize_query(path.stem),
                "size_bytes": stat.st_size,
                "multipart_index": None,
            }
        ]
        self.jobs[job_id] = job
        self.add_event(job_id, None, "scanned", {"source_path": str(path)})
        return job

    def create_review_job(self, *, rule_id: str, identity: str) -> dict[str, Any]:
        job_id = self.next_job_id
        self.next_job_id += 1
        job = job_summary(
            job_id,
            state="review_required",
            media_identity=identity,
            rule_id=rule_id,
            manual=False,
            payload={
                "auto": {
                    "gate_reasons": ["confidence_below_threshold", "strict_assets_missing"],
                    "plan_id": "review-plan-1",
                },
                "api_key": REDACTED,
            },
            plan_id="review-plan-1",
            gate_reasons=["confidence_below_threshold", "strict_assets_missing"],
            selected_candidate={
                "source_id": "XC-REVIEW",
                "title": "Review Required Candidate",
                "source_url": "https://xchina.fixture.test/videos/review.html",
            },
        )
        self.jobs[job_id] = job
        self.add_event(job_id, None, "created", {"api_key": REDACTED})
        self.add_event(
            job_id,
            "created",
            "review_required",
            {
                "reason": "confidence_below_threshold",
                "proxy_url": f"http://{REDACTED}:{REDACTED}@proxy.fixture.local:8080",
            },
        )
        return job

    def manual_candidates(self, normalized_query: str) -> list[dict[str, Any]]:
        return [
            {
                "candidate_id": 1001,
                "source": "xchina",
                "source_candidate_id": "XC-001",
                "title": "Sample Work Alpha",
                "image_url": "/api/e2e/assets/candidate-poster.png",
                "actors": ["Actor One", "Aiko Fixture"],
                "studio": "Studio One",
                "series": "Series One",
                "release_date": "2026-01-02",
                "url": "https://xchina.fixture.test/videos/xc-001.html",
                "confidence_score": 97,
                "score_breakdown": {
                    "title": 60,
                    "actors": 20,
                    "release_date": 17,
                },
            },
            {
                "candidate_id": 1002,
                "source": "xchina",
                "source_candidate_id": "XC-002",
                "title": "Sample Work Alternate",
                "image_url": None,
                "actors": ["Actor Two"],
                "studio": "Studio Two",
                "series": None,
                "release_date": "2025-12-31",
                "url": "https://xchina.fixture.test/videos/xc-002.html",
                "confidence_score": 74,
                "score_breakdown": {"title": 44, "actors": 12, "release_date": 18},
            },
        ]

    def find_candidate(self, job: dict[str, Any], candidate_id: Any) -> dict[str, Any]:
        candidates = job["payload"]["manual"].get("candidates") or self.manual_candidates(job["media_identity"])
        if candidate_id is None:
            return candidates[0]
        for candidate in candidates:
            if candidate["candidate_id"] == int(candidate_id):
                return candidate
        raise HTTPException(status_code=404, detail="Candidate not found")

    def create_plan(
        self,
        job: dict[str, Any],
        destination_root: Path,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        candidate = job.get("selected_candidate") or self.find_candidate(job, None)
        plan_id = f"fixture-plan-{self.next_plan_id}"
        self.next_plan_id += 1
        target_directory = destination_root / "Studio One" / candidate["title"]
        media_source = Path(job["media_items"][0]["path"])
        media_target = target_directory / "XC-001 - Sample Work Alpha.mkv"
        poster_cache = Path(self.paths["asset_dir"]) / f"{plan_id}-poster.png"
        poster_cache.write_bytes(PNG_1X1)
        plan = {
            "plan_id": plan_id,
            "version": 1,
            "database_id": None,
            "job_id": job["id"],
            "mode": payload.get("mode") or "copy",
            "destination_root": str(destination_root),
            "target_directory": str(target_directory),
            "source_snapshot": [
                {
                    "path": str(media_source),
                    "kind": "media",
                    "expected_size_bytes": media_source.stat().st_size,
                    "mtime_ns": media_source.stat().st_mtime_ns,
                    "sha256": None,
                    "sidecar": False,
                    "materialized_asset": False,
                    "generated_artifact": False,
                    "actor_output": False,
                }
            ],
            "materialized_asset_cache_paths": [str(poster_cache)],
            "steps": [
                operation_step(
                    plan_id,
                    "copy-media",
                    "copy",
                    "media",
                    str(media_source),
                    str(media_target),
                    destructive=False,
                ),
                operation_step(
                    plan_id,
                    "write-nfo",
                    "write_generated",
                    "metadata",
                    None,
                    str(media_target.with_suffix(".nfo")),
                    generated_artifact=True,
                ),
                operation_step(
                    plan_id,
                    "copy-poster",
                    "copy_asset",
                    "asset",
                    str(poster_cache),
                    str(target_directory / "poster.png"),
                    materialized_asset=True,
                ),
                operation_step(
                    plan_id,
                    "write-actor",
                    "write_generated",
                    "actor_output",
                    None,
                    str(target_directory / ".actors" / "Aiko Fixture" / "folder.png"),
                    generated_artifact=True,
                    actor_output=True,
                ),
            ],
            "conflicts": [],
            "safety_warnings": [],
            "created_at": now(),
        }
        plan_entry = {
            "plan_id": plan_id,
            "job_id": job["id"],
            "status": "previewed",
            "plan": plan,
            "materialized_assets": [
                {
                    "kind": "poster",
                    "path": str(poster_cache),
                    "url": "/api/e2e/assets/candidate-poster.png",
                }
            ],
        }
        self.plans[plan_id] = plan_entry
        job["plan_id"] = plan_id
        job["payload"]["manual"]["plan_id"] = plan_id
        self.add_event(job["id"], job["state"], "previewed", {"plan_id": plan_id})
        return plan_entry

    def execute_plan(self, plan_entry: dict[str, Any]) -> None:
        job = self.job_or_404(plan_entry["job_id"])
        plan = plan_entry["plan"]
        status = "previewed"
        if plan["mode"] == "copy":
            for step in plan["steps"]:
                target = Path(step["target_path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                source_path = step.get("source_path")
                if source_path and Path(source_path).is_file():
                    target.write_bytes(Path(source_path).read_bytes())
                else:
                    target.write_text("synthetic generated output", encoding="utf-8")
            status = "completed"
        plan_entry["status"] = status
        job["state"] = status
        self.history_plans.insert(
            0,
            {
                "plan_id": plan["plan_id"],
                "job_id": job["id"],
                "mode": plan["mode"],
                "status": status,
                "verification_status": "verified",
                "target_paths": [step["target_path"] for step in plan["steps"]],
                "created_at": now(),
            },
        )
        self.add_event(job["id"], "previewed", status, {"plan_id": plan["plan_id"]})

    def metadata_record(self, candidate: dict[str, Any] | None) -> dict[str, Any]:
        candidate = candidate or self.manual_candidates("Sample Work Alpha")[0]
        return {
            "source_id": candidate["source_candidate_id"],
            "title": candidate["title"],
            "studio": candidate["studio"],
            "actors": candidate["actors"],
            "asset_policy": self.settings["metadata_assets"]["asset_policy"],
        }

    def add_event(
        self,
        job_id: int,
        from_state: str | None,
        to_state: str,
        payload: dict[str, Any],
    ) -> None:
        event = {
            "id": self.next_event_id,
            "job_id": job_id,
            "from_state": from_state,
            "to_state": to_state,
            "payload": payload,
        }
        self.next_event_id += 1
        self.events.setdefault(job_id, []).append(event)

    def job_or_404(self, job_id: int) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    def actor_or_404(self, actor_id: int) -> dict[str, Any]:
        actor = self.actors.get(actor_id)
        if actor is None:
            raise HTTPException(status_code=404, detail="Actor not found")
        return actor


def default_settings(paths: dict[str, str]) -> dict[str, Any]:
    return {
        "storage": {"roots": [paths["media_root"]]},
        "xchina": {
            "base_url": "https://xchina.fixture.test",
            "flaresolverr_url": None,
            "proxy_url": None,
            "cache_dir": paths["xchina_cache_dir"],
        },
        "emby": {
            "enabled": False,
            "server_url": None,
            "api_key": None,
            "path_mappings": [],
            "upload_actor_portraits": True,
        },
        "naming": {
            "folder_templates": ["{studio}", "{title}"],
            "filename_template": "{xchina_id} - {title}",
        },
        "metadata_assets": {
            "write_nfo": True,
            "include_source_snapshot": False,
            "asset_policy": "lenient",
            "max_asset_bytes": 10485760,
        },
        "confidence_safety": {
            "confidence_threshold": 92,
            "refuse_destination_collisions": True,
            "refuse_unresolved_multipart": True,
            "cache_dir": paths["safety_cache_dir"],
        },
        "auth": {"enabled": False, "username": None},
    }


def job_summary(
    job_id: int,
    *,
    state: str,
    media_identity: str,
    rule_id: str | None,
    manual: bool,
    payload: dict[str, Any],
    plan_id: str | None = None,
    gate_reasons: list[str] | None = None,
    selected_candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": job_id,
        "state": state,
        "media_identity": media_identity,
        "rule_id": rule_id,
        "manual": manual,
        "attempts": 1,
        "max_attempts": 3,
        "next_run_at": None,
        "last_error_code": "confidence_below_threshold" if state == "review_required" else None,
        "payload": payload,
        "plan_id": plan_id,
        "selected_candidate": selected_candidate,
        "gate_reasons": gate_reasons or [],
        "retryable": state in {"failed", "review_required"},
        "retry_emby_available": state == "local_complete_emby_failed",
        "media_items": [],
    }


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in job.items()
        if key
        in {
            "id",
            "state",
            "media_identity",
            "rule_id",
            "manual",
            "attempts",
            "max_attempts",
            "next_run_at",
            "last_error_code",
            "payload",
            "plan_id",
            "selected_candidate",
            "gate_reasons",
            "retryable",
            "retry_emby_available",
        }
    } | {
        "retryable": job["state"] in {"failed", "review_required"},
        "retry_emby_available": job["state"] == "local_complete_emby_failed",
    }


def actor_read(
    actor_id: int,
    canonical_name: str,
    *,
    aliases: list[str],
    portrait_source_url: str | None,
    portrait_cache_path: str | None,
    emby_person_id: str | None,
) -> dict[str, Any]:
    return {
        "id": actor_id,
        "canonical_name": canonical_name,
        "aliases": aliases,
        "source": "xchina",
        "source_id": f"ACT-{actor_id:03d}",
        "profile_url": f"https://xchina.fixture.test/actors/{actor_id}",
        "portrait_source_url": portrait_source_url,
        "portrait_cache_path": portrait_cache_path,
        "portrait_sha256": None,
        "portrait_size_bytes": None,
        "biography": "Synthetic actor fixture.",
        "profile_fields": {"height": "fixture"},
        "associated_works": [{"title": "Sample Work Alpha"}],
        "emby_person_id": emby_person_id,
        "linked_works": [{"title": "Sample Work Alpha"}],
    }


def watch_rule_from_payload(rule_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "source_directory": str(payload.get("source_directory") or ""),
        "destination_directory": str(payload.get("destination_directory") or ""),
        "recursive": bool(payload.get("recursive", True)),
        "realtime": bool(payload.get("realtime", True)),
        "polling_interval_seconds": int(payload.get("polling_interval_seconds") or 60),
        "stability_seconds": int(payload.get("stability_seconds") or 30),
        "stable_check_count": int(payload.get("stable_check_count") or 2),
        "organization_mode": str(payload.get("organization_mode") or "copy"),
        "folder_templates": list(payload.get("folder_templates") or []),
        "filename_template": str(payload.get("filename_template") or "{source_filename}"),
        "asset_policy": str(payload.get("asset_policy") or "strict"),
        "emby_options": dict(payload.get("emby_options") or {}),
        "metadata_options": dict(payload.get("metadata_options") or {}),
        "include_patterns": list(payload.get("include_patterns") or []),
        "exclude_patterns": list(payload.get("exclude_patterns") or []),
        "excluded_destination_prefixes": [
            str(prefix) for prefix in payload.get("excluded_destination_prefixes") or []
        ],
        "confidence_threshold": int(payload.get("confidence_threshold") or 92),
        "enabled": bool(payload.get("enabled", True)),
    }


def operation_step(
    plan_id: str,
    suffix: str,
    operation: str,
    category: str,
    source_path: str | None,
    target_path: str,
    *,
    destructive: bool = False,
    materialized_asset: bool = False,
    generated_artifact: bool = False,
    actor_output: bool = False,
) -> dict[str, Any]:
    return {
        "step_id": f"{plan_id}:{suffix}",
        "operation": operation,
        "category": category,
        "source_path": source_path,
        "target_path": target_path,
        "temp_parent_path": str(Path(target_path).parent / ".xona-tmp"),
        "expected_size_bytes": None,
        "mtime_ns": None,
        "sha256": None,
        "sidecar": False,
        "materialized_asset": materialized_asset,
        "generated_artifact": generated_artifact,
        "actor_output": actor_output,
        "destructive": destructive,
        "allow_existing_generated_replacement": False,
        "metadata": {},
    }


def deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = value


def render_template(template: str, context: dict[str, Any]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def normalize_query(value: str) -> str:
    return (
        value.replace(".", " ")
        .replace("_", " ")
        .replace("-", " ")
        .replace("2026", "")
        .strip()
    )


def redact_url(value: Any) -> Any:
    if not isinstance(value, str) or "@" not in value or "://" not in value:
        return value
    scheme, rest = value.split("://", 1)
    _, host = rest.split("@", 1)
    return f"{scheme}://{REDACTED}:{REDACTED}@{host}"


def is_inside(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
