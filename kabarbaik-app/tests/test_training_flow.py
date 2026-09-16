#!/usr/bin/env python3
"""Unit tests for the Training flow: db flow plumbing, workflow recipes/gates/
timeouts/template seeding, and the elearning install step (validation, atomic
manifest merge, idempotency). Pure logic — no AI calls.

Run from the repo root:
    kabarbaik-app/.venv/bin/python kabarbaik-app/tests/test_training_flow.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_APP = _HERE.parent
sys.path.insert(0, str(_APP))

SANDBOX = Path(tempfile.mkdtemp(prefix="kb-train-"))
os.environ["HOME"] = str(SANDBOX / "home")
os.environ["KABARBAIK_DATA_DIR"] = str(SANDBOX / "data")
os.environ["KABARBAIK_ELEARNING_DIR"] = str(SANDBOX / "elearning")

# Hermetic team-kit fixture: the app reads stage templates/schemas from
# KABARBAIK_TEAM_KIT_DIR (default ~/termux-ai/team-kit). Tests must not depend
# on the real checkout existing, so seed a sandbox copy.
_KIT_FIXTURE = SANDBOX / "kit"
(_KIT_FIXTURE / "templates").mkdir(parents=True, exist_ok=True)
(_KIT_FIXTURE / "elearning").mkdir(parents=True, exist_ok=True)
for _kit_name in ("evidence-base.md", "references.md", "course-spec.md"):
    (_KIT_FIXTURE / "templates" / _kit_name).write_text(
        f"kit-template:{_kit_name}\n", encoding="utf-8")
(_KIT_FIXTURE / "elearning" / "course-package.schema.json").write_text(
    '{"$schema": "kit-fixture"}\n', encoding="utf-8")
os.environ["KABARBAIK_TEAM_KIT_DIR"] = str(_KIT_FIXTURE)

import db  # noqa: E402
import settings  # noqa: E402
import workflow  # noqa: E402

settings.ensure_dirs()
db.init()


class TrainingFlowTest(unittest.TestCase):
    def setUp(self):
        db.reset_all()
        db.init()
        self.cid = db.add_client("Tanya Test", "KBTI", "t@local", "unit")
        p = db.add_project(self.cid, "Anti-Burnout Course",
                           "help ops leads avoid burnout", flow="training")
        self.pid = p["id"]
        self.root = db.project_dir(p)
        self.root.mkdir(parents=True, exist_ok=True)
        self.docs = self.root / "docs"
        workflow._scaffold_docs(self.root)

    def tearDown(self):
        db.reset_all()
        shutil.rmtree(settings.PROJECTS_ROOT, ignore_errors=True)
        shutil.rmtree(settings.ELEARNING_DIR / "courses", ignore_errors=True)


class DbFlow(TrainingFlowTest):
    def test_stage_lists_are_distinct(self):
        self.assertEqual(db.STAGES[0][0], "discovery")
        self.assertEqual(db.TRAINING_STAGES[0][0], "training_brief")
        sdlc_names = {n for n, _ in db.STAGES}
        train_names = {n for n, _ in db.TRAINING_STAGES}
        self.assertEqual(len(db.TRAINING_STAGES), 9)
        # Unique per-flow stage names: stage_runs rows can never collide.
        self.assertFalse(sdlc_names & train_names,
                         "SDLC and Training must not share stage names")

    def test_get_stages_flow(self):
        self.assertEqual(db.get_stages("training"), db.TRAINING_STAGES)
        self.assertEqual(db.get_stages("sdlc"), db.STAGES)
        self.assertEqual(db.get_stages("bogus"), db.STAGES)

    def test_add_project_flow_stored(self):
        p = db.get_project(self.pid)
        self.assertEqual(p["flow"], "training")

    def test_sdlc_project_defaults_to_sdlc_flow(self):
        p = db.add_project(self.cid, "Portal", "x")
        self.assertEqual(p["flow"], "sdlc")
        self.assertEqual(p["stage_name"], "Gather Client Requirements")

    def test_stage_name_is_flow_aware(self):
        p = db.get_project(self.pid)
        self.assertEqual(p["stage_name"], "Understand the Training Request")
        listed = db.list_projects(self.cid)[0]
        self.assertEqual(listed["stage_name"], "Understand the Training Request")
        self.assertEqual(listed["flow"], "training")

    def test_index_artifacts_training_keys(self):
        (self.docs / "training" / "research").mkdir(parents=True, exist_ok=True)
        (self.docs / "training" / "research" / "evidence-base.md").write_text("x")
        (self.docs / "training" / "curriculum").mkdir(parents=True, exist_ok=True)
        (self.docs / "training" / "curriculum" / "curriculum.md").write_text("y")
        idx = db.index_artifacts(self.pid)
        self.assertIn("training/research", idx)
        self.assertIn("training/curriculum", idx)
        self.assertEqual(idx["training/research"], ["evidence-base.md"])
        # SDLC projects do NOT get the training/<folder> overlay
        p = db.add_project(self.cid, "Portal", "x")
        p_root = db.project_dir(p)
        (p_root / "docs" / "discovery").mkdir(parents=True, exist_ok=True)
        (p_root / "docs" / "discovery" / "discovery.md").write_text("d")
        idx2 = db.index_artifacts(p["id"])
        self.assertIn("discovery", idx2)
        self.assertFalse(any(k.startswith("training/") for k in idx2))

    def test_flow_column_migration_on_legacy_db(self):
        # Simulate a pre-flow DB: drop the column, re-init → _add_column restores it.
        with db.get_db() as conn:
            conn.execute("ALTER TABLE projects DROP COLUMN flow")
        db.init()
        cols = [r[1] for r in db.get_db().execute("PRAGMA table_info(projects)")]
        self.assertIn("flow", cols)
        p = db.add_project(self.cid, "Migrated Course", "m", flow="training")
        self.assertEqual(p["flow"], "training")


class WorkflowFlow(TrainingFlowTest):
    def test_training_recipes_map_to_training_skills(self):
        pairs = [workflow.stage_recipe(i, "training") for i in range(9)]
        skills = [r[0] for r in pairs]
        self.assertEqual(skills, ["training-brief", "evidence-research",
                                  "training-design", "lesson-script",
                                  "training-proposal",
                                  "ux-design", "elearning", "learning-qa",
                                  "rollout"])
        # SDLC stays on the SDLC map even for training-adjacent indices.
        self.assertEqual(workflow.stage_recipe(0, "sdlc")[0], "doc-ingest")

    def test_stage_timeouts(self):
        self.assertEqual(workflow.stage_timeout("training", "research"), 1800)
        self.assertEqual(workflow.stage_timeout("training", "content"), 1800)
        self.assertEqual(workflow.stage_timeout("training", "elearning_build"), 1800)
        self.assertEqual(workflow.stage_timeout("training", "training_brief"), 900)
        self.assertEqual(workflow.stage_timeout("sdlc", "discovery"), 900)
        self.assertEqual(workflow.stage_timeout("training", "rollout"), 900)

    def test_training_gate_blocks_in_order(self):
        # Fresh project: first stage allowed, everything after is blocked.
        self.assertIsNone(workflow._training_gate("training_brief", self.root))
        for stage in ("research", "curriculum", "content", "training_proposal",
                      "elearning_design", "elearning_build", "training_qa",
                      "rollout"):
            msg = workflow._training_gate(stage, self.root)
            self.assertIsNotNone(msg, f"{stage} should be gated on a fresh project")

    def test_gate_chain_progresses(self):
        d = self.docs
        (d / "training" / "discovery" / "discovery.md").write_text("d")
        self.assertIsNone(workflow._training_gate("research", self.root))
        self.assertIsNotNone(workflow._training_gate("curriculum", self.root))
        (d / "training" / "research" / "evidence-base.md").write_text("e")
        self.assertIsNone(workflow._training_gate("curriculum", self.root))
        (d / "training" / "curriculum" / "curriculum.md").write_text("c")
        self.assertIsNone(workflow._training_gate("content", self.root))
        (d / "training" / "preview" / "modules-preview.md").write_text("m")
        self.assertIsNone(workflow._training_gate("training_proposal", self.root))
        # Course UX needs an approved proposal (proposal-vN.md OR an inbox file).
        self.assertIsNotNone(workflow._training_gate("elearning_design", self.root))
        (d / "training" / "proposal" / "proposal-v1.md").write_text("p")
        self.assertIsNone(workflow._training_gate("elearning_design", self.root))
        (d / "training" / "spec" / "course-spec.md").write_text("s")
        self.assertIsNone(workflow._training_gate("elearning_build", self.root))
        (self.root / "elearning-package").mkdir(parents=True, exist_ok=True)
        (self.root / "elearning-package" / "demo-course").mkdir(parents=True,
                                                                exist_ok=True)
        (self.root / "elearning-package" / "demo-course" /
         "course.json").write_text("{}")
        self.assertIsNone(workflow._training_gate("training_qa", self.root))
        (d / "training" / "qa" / "review-checklist.md").write_text("q")
        self.assertIsNone(workflow._training_gate("rollout", self.root))

    def test_has_training_proposal_via_inbox(self):
        d = self.docs
        (d / "inbox").mkdir(parents=True, exist_ok=True)
        (d / "inbox" / "client-approved-proposal.pdf").write_text("X")
        self.assertTrue(workflow._has_training_proposal(d))
        self.assertIsNone(workflow._training_gate("elearning_design", self.root))

    def test_training_stage_templates_dest(self):
        merged = {}
        for stage, pairs in workflow.TRAINING_STAGE_TEMPLATES.items():
            for kit_name, dst in pairs:
                merged[kit_name] = dst
        self.assertEqual(merged["course-package.schema.json"],
                         "docs/training/spec/COURSE-PACKAGE-SCHEMA.md")
        self.assertEqual(merged["evidence-base.md"],
                         "docs/training/research/TEMPLATE.md")
        self.assertEqual(merged["modules-preview.md"],
                         "docs/training/preview/TEMPLATE.md")
        # training-proposal.md / review-checklist.md from the kit template set.
        self.assertIn("training-proposal.md", merged)
        self.assertIn("review-checklist.md", merged)

    def test_seed_templates_writes_training_dest(self):
        workflow._seed_templates(self.root, "research", "training")
        self.assertTrue((self.docs / "training" / "research" / "TEMPLATE.md").is_file())
        self.assertTrue((self.docs / "training" / "research" /
                         "REFERENCES-TEMPLATE.md").is_file())
        # Schema mirror is seeded from team-kit/elearning/.
        workflow._seed_templates(self.root, "elearning_design", "training")
        spec = self.docs / "training" / "spec" / "COURSE-PACKAGE-SCHEMA.md"
        self.assertTrue(spec.is_file())
        kit_schema = workflow._KIT / "elearning" / "course-package.schema.json"
        self.assertTrue(kit_schema.is_file())

    def test_unfilled_outputs_training(self):
        expected = workflow._unfilled_outputs_training(self.root, "training_brief")
        self.assertIn("docs/training/discovery/discovery.md", expected)


def _sample_course(course_id: str = "demo-course"):
    return {
        "id": course_id,
        "title": "Demo Course",
        "language": "en",
        "audience": {"roles": ["ops lead"]},
        "lessons": [
            {"id": "l1", "title": "Intro", "file": "lessons/l1.md", "type": "reading",
             "duration_min": 10,
             "quiz": {"questions": [{"q": "Pick", "options": ["A", "B"],
                                     "answer": 0}]}},
        ],
    }


class InstallCourse(TrainingFlowTest):
    def _platform(self, with_manifest=True):
        courses = settings.ELEARNING_DIR / "courses"
        courses.mkdir(parents=True, exist_ok=True)
        if with_manifest:
            (courses / "manifest.json").write_text(
                json.dumps({"version": 1, "course_ids": []}), encoding="utf-8")
        return courses

    def _write_package(self, course_id="demo-course", corrupt=False):
        pkg = self.root / "elearning-package" / course_id
        (pkg / "lessons").mkdir(parents=True, exist_ok=True)
        (pkg / "lessons" / "l1.md").write_text(
            "# Intro\n\n| Type | Duration | Module | Outcome |\n"
            "| :--- | :------- | :------ | :------ |\n"
            "| Reading | 10 min | Demo Module | OU-1 |\n", encoding="utf-8")
        course = _sample_course(course_id)
        if corrupt:
            course["lessons"] = []
        (pkg / "course.json").write_text(json.dumps(course), encoding="utf-8")
        return pkg

    def test_install_course_lifecycle(self):
        courses = self._platform()
        self._write_package("demo-course")
        status = workflow.install_course(self.root)
        self.assertIn("installed", status)
        self.assertTrue((courses / "demo-course" / "course.json").is_file())
        self.assertTrue((courses / "demo-course" / "lessons" / "l1.md").is_file())
        manifest = json.loads((courses / "manifest.json").read_text())
        self.assertEqual(manifest["course_ids"], ["demo-course"])

    def test_install_is_idempotent_and_preserves_manifest_v2(self):
        courses = self._platform()
        self._write_package("alpha")
        self._write_package("beta")
        (settings.ELEARNING_DIR / "courses" / "extra").mkdir(parents=True)
        workflow.install_course(self.root)  # installs alpha (first sorted)
        workflow.install_course(self.root)  # idempotent re-run
        manifest = json.loads((courses / "manifest.json").read_text())
        self.assertEqual(manifest["course_ids"], ["alpha"])

    def test_install_merges_manifest_atomically(self):
        courses = self._platform()
        self._write_package("bravo")
        existing = courses / "existing.txt"
        existing.write_text("untouched", encoding="utf-8")
        # seed a manifest already listing another course
        (courses / "manifest.json").write_text(
            json.dumps({"version": 1, "course_ids": ["other-course"]}), encoding="utf-8")
        workflow.install_course(self.root)
        manifest = json.loads((courses / "manifest.json").read_text())
        self.assertEqual(sorted(manifest["course_ids"]),
                         ["bravo", "other-course"])
        self.assertEqual(existing.read_text(), "untouched")
        # no temp files left behind
        self.assertFalse((courses / "manifest.json.tmp").exists())

    def test_install_rejects_non_plain_h1(self):
        self._platform()
        pkg = self._write_package("bad-h1")
        (pkg / "lessons" / "l1.md").write_text(
            "# Lesson 01: Intro\n\n| Type | Duration | Module | Outcome |\n"
            "| :--- | :------- | :------ | :------ |\n"
            "| Reading | 10 min | Demo Module | OU-1 |\n", encoding="utf-8")
        with self.assertRaises(ValueError) as cm:
            workflow.install_course(self.root)
        self.assertIn("does not match course.json title", str(cm.exception))

    def test_install_rejects_slug_cover_table(self):
        self._platform()
        pkg = self._write_package("bad-table")
        (pkg / "lessons" / "l1.md").write_text(
            "# Intro\n\n| Lesson id | type | duration_min | module | outcome |\n"
            "| :-------- | :--- | :----------- | :----- | :------ |\n"
            "| l1 | reading | 10 | module-demo | OU-1 |\n", encoding="utf-8")
        with self.assertRaises(ValueError) as cm:
            workflow.install_course(self.root)
        self.assertIn("cover table must use the human headers", str(cm.exception))

    def test_install_rejects_missing_cover_table(self):
        self._platform()
        self._write_package("no-table")
        (self.root / "elearning-package" / "no-table" / "lessons" / "l1.md")\
            .write_text("# Intro\n\nSome body only.\n", encoding="utf-8")
        with self.assertRaises(ValueError) as cm:
            workflow.install_course(self.root)
        self.assertIn("must carry the cover table", str(cm.exception))

    def test_install_rejects_invalid_course(self):
        self._platform()
        self._write_package("bad-course", corrupt=True)
        with self.assertRaises(ValueError) as cm:
            workflow.install_course(self.root)
        self.assertIn("invalid", str(cm.exception))
        manifest = json.loads((settings.ELEARNING_DIR / "courses" / "manifest.json")
                              .read_text())
        self.assertEqual(manifest["course_ids"], [])
        self.assertFalse((settings.ELEARNING_DIR / "courses" / "bad-course").exists())

    def test_install_rejects_missing_package(self):
        self._platform()
        (self.docs / "training" / "qa").mkdir(parents=True, exist_ok=True)
        with self.assertRaises(ValueError):
            workflow.install_course(self.root)

    def test_install_rejects_unready_platform(self):
        # No courses dir at all → clear platform-not-ready error.
        shutil.rmtree(settings.ELEARNING_DIR, ignore_errors=True)
        self._write_package("demo-course")
        with self.assertRaises(ValueError) as cm:
            workflow.install_course(self.root)
        self.assertIn("Platform not ready", str(cm.exception))

    def test_stage_finalize(self):
        self._platform()
        # SDLC projects: no-op.
        p = db.add_project(self.cid, "Portal", "x")
        self.assertIsNone(workflow._stage_finalize(
            p, db.project_dir(p), "task_breakdown", "sdlc"))
        # elearning_build with a valid package → status line.
        self._write_package("demo-course")
        status = workflow._stage_finalize("proj", self.root,
                                          "elearning_build", "training")
        self.assertIsInstance(status, str)
        self.assertIn("installed", status)
        # invalid package → ERR string (which fails the stage), no crash.
        self._write_package("demo-2", corrupt=True)
        status = workflow._stage_finalize("proj", self.root,
                                          "elearning_build", "training")
        self.assertTrue(status.startswith("ERR:"))


if __name__ == "__main__":
    unittest.main(verbosity=2)