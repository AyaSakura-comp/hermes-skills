import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "validate_dataset.py"
REPO_DATASET_ROOT = Path(__file__).parents[3] / "datasets" / "v12-search-diligence"
DATASET_ROOT = (
    REPO_DATASET_ROOT
    if REPO_DATASET_ROOT.is_dir()
    else Path("/home/chihmin/backups/qwen-agentic-lora-audit/datasets/v12-search-diligence")
)
spec = importlib.util.spec_from_file_location("validate_dataset", MODULE_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(validator)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def valid_row() -> dict:
    return {
        "id": "case-001-step-1",
        "case_id": "case-001",
        "trajectory_id": "case-001",
        "trajectory_step": 1,
        "trajectory_steps": 1,
        "family_id": "local_recommendation",
        "semantic_cluster": "live_local_venue",
        "split": "train",
        "provenance": "user_supplied_incident_safe_prefix",
        "source_record": "source/case-001.md",
        "review_status": "prepared_pending_dataset_review",
        "task_status": "safe_prefix",
        "target_kind": "clarification",
        "tools": [],
        "messages": [
            {"role": "system", "content": "Ask for clarification when location is ambiguous."},
            {"role": "user", "content": "捷運紅線怎麼這麼多人？"},
            {"role": "assistant", "content": "你是指台北還是高雄？"},
        ],
        "supervise_message_indices": [2],
        "task_weight": 1.0,
    }


def policy() -> dict:
    return {
        "unit": "independent_trajectory",
        "eligible_case_statuses": ["safe_prefix_trainable", "grounded_completion_trainable"],
        "allowed_safe_prefix_tools": ["gettime", "web_search", "crawl"],
        "pilot_quotas": {
            "search_and_read": 15,
            "search": 5,
            "direct_no_tool": 5,
            "clarify_or_tool_failure": 5,
        },
        "full_candidate_quotas": {
            "search_and_read": 50,
            "search": 15,
            "direct_no_tool": 20,
            "clarify_or_tool_failure": 15,
        },
        "minimum_semantic_families": {"pilot": 5, "full_candidate": 5},
        "split_gate": {
            "pilot": {"train": 20, "validation": 5, "heldout": 5},
            "full_candidate": {"train": 70, "validation": 15, "heldout": 15},
        },
    }


def make_dataset(root: Path, row: dict | None = None) -> None:
    source = root / "source" / "case-001.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# De-identified source\n", encoding="utf-8")
    write_json(
        root / "cases" / "case-001.json",
        {
            "case_id": "case-001",
            "trajectory_id": "case-001",
            "source_record": "source/case-001.md",
            "privacy": {"deidentified": True, "raw_private_chat_included": False},
            "readiness_bucket": "clarify_or_tool_failure",
            "status": "safe_prefix_trainable",
            "trainable_row_ids": ["case-001-step-1"],
        },
    )
    write_jsonl(root / "trainable" / "candidates.jsonl", [row or valid_row()])
    write_json(root / "readiness-policy.json", policy())


class ValidateDatasetTests(unittest.TestCase):
    def test_valid_safe_prefix_reports_deterministic_readiness_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)
            report = validator.validate_dataset(root)

        self.assertTrue(report["valid"])
        self.assertEqual(report["case_count"], 1)
        self.assertEqual(report["eligible_trajectory_count"], 1)
        self.assertEqual(report["trainable_row_count"], 1)
        self.assertEqual(report["pilot_target"], 30)
        self.assertEqual(report["pilot_remaining"], 29)
        self.assertEqual(report["remaining_by_bucket"]["clarify_or_tool_failure"], 4)
        self.assertEqual(report["full_candidate_target"], 100)
        self.assertEqual(report["full_candidate_remaining"], 99)
        self.assertFalse(report["pilot_pool_complete"])
        self.assertFalse(report["full_candidate_pool_complete"])

    def test_fixed_policy_and_candidates_must_not_be_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            make_dataset(root)
            external_policy = Path(outside) / "policy.json"
            write_json(external_policy, policy())
            (root / "readiness-policy.json").unlink()
            (root / "readiness-policy.json").symlink_to(external_policy)
            report = validator.validate_dataset(root)
            self.assertFalse(report["valid"])
            self.assertTrue(any("symlink" in error for error in report["errors"]))

            (root / "readiness-policy.json").unlink()
            write_json(root / "readiness-policy.json", policy())
            external_rows = Path(outside) / "candidates.jsonl"
            write_jsonl(external_rows, [valid_row()])
            (root / "trainable" / "candidates.jsonl").unlink()
            (root / "trainable" / "candidates.jsonl").symlink_to(external_rows)
            report = validator.validate_dataset(root)
            self.assertFalse(report["valid"])
            self.assertTrue(any("symlink" in error for error in report["errors"]))

    def test_dataset_root_rejects_symlinked_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real_parent = base / "real"
            root = real_parent / "dataset"
            root.mkdir(parents=True)
            make_dataset(root)
            alias = base / "alias"
            alias.symlink_to(real_parent, target_is_directory=True)
            report = validator.validate_dataset(alias / "dataset")

        self.assertFalse(report["valid"])
        self.assertTrue(any("ancestor" in error for error in report["errors"]))

    def test_output_rejects_traversal_and_existing_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            make_dataset(root)
            report = validator.validate_dataset(root)
            escaped = root / ".." / "escaped.json"
            with self.assertRaises(ValueError):
                validator.write_report(root, escaped, report)
            self.assertFalse(escaped.exists())

            external = Path(outside) / "report.json"
            external.write_text("untouched\n", encoding="utf-8")
            linked = root / "linked-report.json"
            linked.symlink_to(external)
            with self.assertRaises(ValueError):
                validator.write_report(root, linked, report)
            self.assertEqual(external.read_text(encoding="utf-8"), "untouched\n")

    def test_write_report_rejects_symlinked_dataset_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real_parent = base / "real"
            root = real_parent / "dataset"
            root.mkdir(parents=True)
            make_dataset(root)
            alias = base / "alias"
            alias.symlink_to(real_parent, target_is_directory=True)
            report = validator.validate_dataset(root)
            with self.assertRaises(ValueError):
                validator.write_report(alias / "dataset", alias / "dataset" / "report.json", report)

    def test_raw_private_chat_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)
            case_path = root / "cases" / "case-001.json"
            case = json.loads(case_path.read_text(encoding="utf-8"))
            case["privacy"]["raw_private_chat_included"] = True
            write_json(case_path, case)
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("raw_private_chat_included" in error for error in report["errors"]))

    def test_duplicate_trajectory_does_not_inflate_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)
            duplicate_case = json.loads((root / "cases" / "case-001.json").read_text(encoding="utf-8"))
            duplicate_case["case_id"] = "case-002"
            duplicate_case["trainable_row_ids"] = ["case-002-step-1"]
            write_json(root / "cases" / "case-002.json", duplicate_case)
            duplicate_row = valid_row()
            duplicate_row["id"] = "case-002-step-1"
            duplicate_row["case_id"] = "case-002"
            write_jsonl(root / "trainable" / "candidates.jsonl", [valid_row(), duplicate_row])
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertEqual(report["eligible_trajectory_count"], 1)
        self.assertEqual(report["pilot_remaining"], 29)
        self.assertTrue(any("duplicate trajectory_id" in error for error in report["errors"]))

    def test_case_row_trajectory_mismatch_and_empty_inventory_are_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)
            row = valid_row()
            row["trajectory_id"] = "different"
            write_jsonl(root / "trainable" / "candidates.jsonl", [row])
            report = validator.validate_dataset(root)
            self.assertFalse(report["valid"])
            self.assertEqual(report["eligible_trajectory_count"], 0)
            self.assertEqual(report["pilot_remaining"], 30)
            self.assertTrue(any("trajectory_id does not match" in error for error in report["errors"]))

            case_path = root / "cases" / "case-001.json"
            case = json.loads(case_path.read_text(encoding="utf-8"))
            case["trainable_row_ids"] = []
            write_json(case_path, case)
            write_jsonl(root / "trainable" / "candidates.jsonl", [])
            report = validator.validate_dataset(root)
            self.assertEqual(report["eligible_trajectory_count"], 0)
            self.assertTrue(any("non-empty" in error for error in report["errors"]))

    def test_policy_rejects_unknown_eligible_case_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)
            configured = policy()
            configured["eligible_case_statuses"].append("mystery_trainable")
            write_json(root / "readiness-policy.json", configured)
            case_path = root / "cases" / "case-001.json"
            case = json.loads(case_path.read_text(encoding="utf-8"))
            case["status"] = "mystery_trainable"
            write_json(case_path, case)
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertEqual(report["eligible_trajectory_count"], 0)
        self.assertTrue(any("unknown eligible case status" in error for error in report["errors"]))

    def test_ineligible_case_status_is_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)
            case_path = root / "cases" / "case-001.json"
            case = json.loads(case_path.read_text(encoding="utf-8"))
            case["status"] = "quarantined"
            write_json(case_path, case)
            report = validator.validate_dataset(root)

        self.assertTrue(report["valid"])
        self.assertEqual(report["eligible_trajectory_count"], 0)
        self.assertEqual(report["pilot_remaining"], 30)

    def test_split_and_trajectory_steps_must_be_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = valid_row()
            first["trajectory_steps"] = 2
            second = valid_row()
            second["id"] = "case-001-step-2"
            second["trajectory_step"] = 3
            second["trajectory_steps"] = 3
            second["split"] = "validation"
            make_dataset(root, first)
            case_path = root / "cases" / "case-001.json"
            case = json.loads(case_path.read_text(encoding="utf-8"))
            case["trainable_row_ids"] = [first["id"], second["id"]]
            write_json(case_path, case)
            write_jsonl(root / "trainable" / "candidates.jsonl", [first, second])
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("one split" in error for error in report["errors"]))
        self.assertTrue(any("trajectory steps" in error for error in report["errors"]))

    def test_semantic_family_and_split_gates_block_pool_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_dataset(root)
            gate_policy = policy()
            gate_policy["pilot_quotas"] = {"clarify_or_tool_failure": 1}
            gate_policy["full_candidate_quotas"] = {"clarify_or_tool_failure": 1}
            gate_policy["minimum_semantic_families"] = {"pilot": 2, "full_candidate": 2}
            gate_policy["split_gate"] = {
                "pilot": {"train": 0, "validation": 1, "heldout": 0},
                "full_candidate": {"train": 0, "validation": 1, "heldout": 0},
            }
            write_json(root / "readiness-policy.json", gate_policy)
            report = validator.validate_dataset(root)

        self.assertTrue(report["valid"])
        self.assertEqual(report["pilot_remaining"], 0)
        self.assertEqual(report["semantic_family_count"], 1)
        self.assertEqual(report["split_counts"]["train"], 1)
        self.assertFalse(report["pilot_semantic_family_gate_met"])
        self.assertFalse(report["pilot_split_gate_met"])
        self.assertFalse(report["pilot_pool_complete"])

    def test_unknown_task_status_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = valid_row()
            row["task_status"] = "grounded_completioN"
            row["messages"][-1] = {"role": "assistant", "content": "Unsupported factual answer"}
            row.pop("target_kind")
            make_dataset(root, row)
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("unsupported task_status" in error for error in report["errors"]))

    def test_safe_prefix_target_kind_and_tool_call_are_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = valid_row()
            row["target_kind"] = "next_tool_action"
            row["tools"] = [{"type": "function", "function": {"name": "gettime"}}]
            row["messages"][-1] = {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "web_search", "arguments": {}}}],
            }
            make_dataset(root, row)
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("undeclared tool" in error for error in report["errors"]))

    def test_safe_prefix_rejects_arbitrary_locally_declared_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = valid_row()
            row["target_kind"] = "next_tool_action"
            row["tools"] = [{"type": "function", "function": {"name": "delete_everything"}}]
            row["messages"][-1] = {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "delete_everything", "arguments": {}}}],
            }
            make_dataset(root, row)
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("approved safe-prefix tool" in error for error in report["errors"]))

    def test_safe_prefix_rejects_disallowed_tool_in_unsupervised_assistant_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = valid_row()
            row["tools"] = [{"type": "function", "function": {"name": "delete_everything"}}]
            row["messages"].insert(2, {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "old", "type": "function", "function": {"name": "delete_everything", "arguments": {}}}],
            })
            row["supervise_message_indices"] = [3]
            make_dataset(root, row)
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("approved safe-prefix tool" in error for error in report["errors"]))

    def test_safe_prefix_rejects_tool_results_and_missing_target_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = valid_row()
            del row["target_kind"]
            row["messages"].insert(2, {"role": "tool", "name": "web_search", "content": "invented result"})
            row["supervise_message_indices"] = [3]
            make_dataset(root, row)
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("target_kind" in error for error in report["errors"]))
        self.assertTrue(any("tool result" in error for error in report["errors"]))

    def test_source_grounded_reconstruction_requires_captured_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = valid_row()
            row["provenance"] = "source_grounded_reconstruction"
            row["task_status"] = "grounded_completion"
            row.pop("target_kind")
            make_dataset(root, row)
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("evidence_paths" in error for error in report["errors"]))

    def test_direct_and_clarification_tasks_reject_tool_results_and_tool_targets(self):
        for task_status, provenance, case_status in [
            ("direct_no_tool", "direct_no_tool", "direct_no_tool_trainable"),
            ("clarification", "clarification", "safe_prefix_trainable"),
        ]:
            with self.subTest(task_status=task_status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                row = valid_row()
                row["task_status"] = task_status
                row["provenance"] = provenance
                row.pop("target_kind")
                row["messages"].insert(2, {"role": "tool", "name": "web_search", "content": "invented"})
                row["messages"][-1] = {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "call", "type": "function", "function": {"name": "web_search", "arguments": {}}}],
                }
                row["supervise_message_indices"] = [3]
                make_dataset(root, row)
                case_path = root / "cases" / "case-001.json"
                case = json.loads(case_path.read_text(encoding="utf-8"))
                case["status"] = case_status
                write_json(case_path, case)
                report = validator.validate_dataset(root)

            self.assertFalse(report["valid"])
            self.assertTrue(any("must not contain tool results" in error for error in report["errors"]))
            self.assertTrue(any("assistant text without tool calls" in error for error in report["errors"]))

    def test_grounded_completion_requires_grounded_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = valid_row()
            row["task_status"] = "grounded_completion"
            row.pop("target_kind")
            make_dataset(root, row)
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("grounded provenance" in error for error in report["errors"]))

    def test_grounded_evidence_must_be_in_evidence_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = valid_row()
            row["provenance"] = "source_grounded_reconstruction"
            row["task_status"] = "grounded_completion"
            row.pop("target_kind")
            row["evidence_paths"] = ["source/case-001.md"]
            make_dataset(root, row)
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("evidence/" in error for error in report["errors"]))

    def test_published_dataset_and_manifest_report_drift(self):
        verified = validator.verify_published(DATASET_ROOT)
        self.assertTrue(verified["valid"], verified["errors"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dataset"
            shutil.copytree(DATASET_ROOT, root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["case_count"] += 1
            write_json(manifest_path, manifest)
            result = validator.verify_published(root)
            self.assertFalse(result["valid"])
            self.assertTrue(any("manifest" in error for error in result["errors"]))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dataset"
            shutil.copytree(DATASET_ROOT, root)
            report_path = root / "readiness-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["pilot_remaining"] += 1
            write_json(report_path, report)
            result = validator.verify_published(root)
            self.assertFalse(result["valid"])
            self.assertTrue(any("readiness report" in error for error in result["errors"]))

    def test_published_verifier_rejects_candidate_symlink_empty_hashes_and_deployment_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dataset"
            shutil.copytree(DATASET_ROOT, root)
            original = root / "trainable" / "original.jsonl"
            candidates = root / "trainable" / "candidates.jsonl"
            candidates.rename(original)
            candidates.symlink_to(original.name)
            result = validator.verify_published(root)
            self.assertFalse(result["valid"])
            self.assertTrue(any("symlink" in error for error in result["errors"]))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dataset"
            shutil.copytree(DATASET_ROOT, root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["hashes"] = {}
            manifest["authorization_boundaries"]["deployment"] = True
            write_json(manifest_path, manifest)
            result = validator.verify_published(root)
            self.assertFalse(result["valid"])
            self.assertTrue(any("hash inventory" in error for error in result["errors"]))
            self.assertTrue(any("deployment authorization" in error for error in result["errors"]))

    def test_missing_source_and_duplicate_rows_and_bad_supervision_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = valid_row()
            row["supervise_message_indices"] = [1]
            make_dataset(root, row)
            (root / "source" / "case-001.md").unlink()
            write_jsonl(root / "trainable" / "candidates.jsonl", [row, row])
            report = validator.validate_dataset(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("source record" in error for error in report["errors"]))
        self.assertTrue(any("duplicate row id" in error for error in report["errors"]))
        self.assertTrue(any("assistant message" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
