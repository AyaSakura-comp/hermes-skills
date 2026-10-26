#!/usr/bin/env python3
"""Validate provenance-safe research incident training candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ALLOWED_PROVENANCE = {
    "user_supplied_incident_safe_prefix",
    "source_grounded_reconstruction",
    "direct_no_tool",
    "clarification",
}
ALLOWED_SPLITS = {"candidate", "train", "validation", "heldout"}
SAFE_PREFIX_TARGETS = {"clarification", "next_tool_action"}
TASK_PROVENANCE = {
    "safe_prefix": {"user_supplied_incident_safe_prefix", "clarification"},
    "grounded_completion": {"source_grounded_reconstruction"},
    "direct_no_tool": {"direct_no_tool"},
    "clarification": {"clarification"},
}
CASE_TASK_STATUS = {
    "safe_prefix_trainable": {"safe_prefix", "clarification"},
    "grounded_completion_trainable": {"grounded_completion"},
    "direct_no_tool_trainable": {"direct_no_tool"},
}


def _lexical_root(root: Path) -> Path:
    return Path(os.path.abspath(os.fspath(root)))


def _has_symlink_component(path: Path) -> bool:
    absolute = _lexical_root(path)
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


def _safe_path(
    root: Path,
    relative_or_path: object,
    label: str,
    errors: list[str],
    *,
    must_exist: bool = True,
    expect_file: bool | None = True,
) -> Path | None:
    if not isinstance(relative_or_path, (str, os.PathLike)):
        errors.append(f"{label}: path is missing")
        return None
    supplied = Path(relative_or_path)
    candidate = supplied if supplied.is_absolute() else root / supplied
    candidate = Path(os.path.abspath(os.fspath(candidate)))
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        errors.append(f"{label}: path is outside dataset root")
        return None
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            errors.append(f"{label}: symlink is not allowed")
            return None
    if must_exist and not candidate.exists():
        errors.append(f"{label}: path does not exist")
        return None
    if must_exist and expect_file is True and not candidate.is_file():
        errors.append(f"{label}: expected a regular file")
        return None
    if must_exist and expect_file is False and not candidate.is_dir():
        errors.append(f"{label}: expected a directory")
        return None
    return candidate


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected JSON object")
        rows.append(value)
    return rows


def _quota_map(value: object, label: str, errors: list[str]) -> dict[str, int]:
    if not isinstance(value, dict) or not value or any(
        not isinstance(name, str) or not isinstance(count, int) or count < 0 for name, count in value.items()
    ):
        errors.append(f"{label} must be non-negative integer counts")
        return {}
    return dict(value)


def _declared_tool_names(row: dict[str, Any], label: str, errors: list[str]) -> set[str]:
    tools = row.get("tools")
    if not isinstance(tools, list):
        errors.append(f"{label}: tools must be a list")
        return set()
    names: set[str] = set()
    for tool in tools:
        function = tool.get("function") if isinstance(tool, dict) else None
        name = function.get("name") if isinstance(function, dict) else None
        if not isinstance(name, str) or not name:
            errors.append(f"{label}: malformed declared tool")
        else:
            names.add(name)
    return names


def _validate_target(
    root: Path,
    row: dict[str, Any],
    messages: list[dict[str, Any]],
    supervised: list[int],
    label: str,
    approved_safe_tools: set[str],
    errors: list[str],
) -> None:
    provenance = row.get("provenance")
    task_status = row.get("task_status")
    if task_status == "grounded_completion" and provenance != "source_grounded_reconstruction":
        errors.append(f"{label}: grounded_completion requires grounded provenance")
    if provenance == "source_grounded_reconstruction":
        evidence_paths = row.get("evidence_paths")
        if not isinstance(evidence_paths, list) or not evidence_paths:
            errors.append(f"{label}: source_grounded_reconstruction requires evidence_paths")
        else:
            for evidence in evidence_paths:
                evidence_path = Path(evidence) if isinstance(evidence, str) else None
                if evidence_path is None or evidence_path.is_absolute() or not evidence_path.parts or evidence_path.parts[0] != "evidence":
                    errors.append(f"{label}: evidence_paths must point under evidence/")
                else:
                    _safe_path(root, evidence, f"{label} evidence_paths", errors)

    if task_status in {"direct_no_tool", "clarification"}:
        if any(message.get("role") == "tool" for message in messages):
            errors.append(f"{label}: {task_status} must not contain tool results")
        if any(message.get("role") == "assistant" and message.get("tool_calls") for message in messages):
            errors.append(f"{label}: {task_status} must use assistant text without tool calls")
        for index in supervised:
            if isinstance(index, int) and 0 <= index < len(messages):
                target = messages[index]
                if not isinstance(target.get("content"), str) or not target.get("content", "").strip():
                    errors.append(f"{label}: {task_status} target must be nonempty assistant text without tool calls")
        return
    if task_status != "safe_prefix":
        return
    if any(message.get("role") == "tool" for message in messages):
        errors.append(f"{label}: safe prefix must not contain an unverified tool result")
    target_kind = row.get("target_kind")
    if target_kind not in SAFE_PREFIX_TARGETS:
        errors.append(f"{label}: safe prefix target_kind must be clarification or next_tool_action")
        return

    declared = _declared_tool_names(row, label, errors)
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls", []) if isinstance(message.get("tool_calls"), list) else []:
            function = call.get("function") if isinstance(call, dict) else None
            name = function.get("name") if isinstance(function, dict) else None
            if isinstance(name, str) and name not in declared:
                errors.append(f"{label}: assistant context uses undeclared tool {name!r}")
            elif isinstance(name, str) and name not in approved_safe_tools:
                errors.append(f"{label}: assistant context tool {name!r} is not an approved safe-prefix tool")
    for index in supervised:
        if not isinstance(index, int) or not 0 <= index < len(messages):
            continue
        target = messages[index]
        if target.get("role") != "assistant":
            continue
        calls = target.get("tool_calls")
        text = target.get("content")
        if target_kind == "clarification":
            if not isinstance(text, str) or not text.strip() or calls:
                errors.append(f"{label}: clarification target must be assistant text without tool calls")
        elif not isinstance(calls, list) or not calls:
            errors.append(f"{label}: next_tool_action target must contain tool_calls")
        else:
            for call in calls:
                function = call.get("function") if isinstance(call, dict) else None
                name = function.get("name") if isinstance(function, dict) else None
                arguments = function.get("arguments") if isinstance(function, dict) else None
                if not isinstance(name, str) or not name:
                    errors.append(f"{label}: malformed target tool call")
                elif name not in declared:
                    errors.append(f"{label}: target uses undeclared tool {name!r}")
                elif name not in approved_safe_tools:
                    errors.append(f"{label}: target tool {name!r} is not an approved safe-prefix tool")
                if not isinstance(arguments, dict):
                    errors.append(f"{label}: target tool arguments must be an object")


def _gate_met(actual: Counter[str], required: object) -> bool:
    return isinstance(required, dict) and all(
        isinstance(count, int) and count >= 0 and actual.get(split, 0) >= count for split, count in required.items()
    )


def validate_dataset(root: Path) -> dict[str, Any]:
    original_root = Path(root)
    if _has_symlink_component(original_root):
        return {"valid": False, "errors": ["dataset root ancestor symlink is not allowed"]}
    root = _lexical_root(original_root)
    errors: list[str] = []
    if not root.is_dir():
        return {"valid": False, "errors": ["dataset root is not a directory"]}

    policy_path = _safe_path(root, "readiness-policy.json", "readiness policy", errors)
    candidates_path = _safe_path(root, "trainable/candidates.jsonl", "trainable candidates", errors)
    cases_dir = _safe_path(root, "cases", "cases directory", errors, expect_file=False)
    if policy_path is None:
        return {"valid": False, "errors": errors}
    try:
        policy = _read_json(policy_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"valid": False, "errors": errors + [f"readiness policy unreadable: {exc}"]}

    pilot_quotas = _quota_map(policy.get("pilot_quotas"), "readiness policy pilot_quotas", errors)
    full_quotas = _quota_map(policy.get("full_candidate_quotas"), "readiness policy full_candidate_quotas", errors)
    if set(full_quotas) != set(pilot_quotas) or any(
        full_quotas.get(name, -1) < count for name, count in pilot_quotas.items()
    ):
        errors.append("full_candidate_quotas must cover pilot buckets at equal or higher counts")
    eligible_statuses = policy.get("eligible_case_statuses")
    if not isinstance(eligible_statuses, list) or any(not isinstance(value, str) for value in eligible_statuses):
        errors.append("readiness policy eligible_case_statuses must be a list of strings")
        eligible_statuses = []
    unknown_eligible_statuses = set(eligible_statuses) - set(CASE_TASK_STATUS)
    if unknown_eligible_statuses:
        errors.append(f"readiness policy contains unknown eligible case status: {sorted(unknown_eligible_statuses)}")
        eligible_statuses = [value for value in eligible_statuses if value in CASE_TASK_STATUS]
    allowed_safe_prefix_tools = policy.get("allowed_safe_prefix_tools")
    if not isinstance(allowed_safe_prefix_tools, list) or any(
        not isinstance(value, str) or not value for value in allowed_safe_prefix_tools
    ):
        errors.append("readiness policy allowed_safe_prefix_tools must be a list of tool names")
        allowed_safe_prefix_tools = []
    approved_safe_tools = set(allowed_safe_prefix_tools)

    case_files = sorted(cases_dir.glob("*.json")) if cases_dir else []
    cases: dict[str, dict[str, Any]] = {}
    invalid_cases: set[str] = set()
    expected_rows: dict[str, set[str]] = {}
    trajectory_owner: dict[str, str] = {}

    def case_error(case_id: str, message: str) -> None:
        errors.append(f"{case_id}: {message}")
        invalid_cases.add(case_id)

    for path in case_files:
        safe_case = _safe_path(root, path, f"case file {path.name}", errors)
        if safe_case is None:
            continue
        try:
            case = _read_json(safe_case)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"case unreadable {path.name}: {exc}")
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"{path.name}: missing case_id")
            continue
        if case_id in cases:
            case_error(case_id, "duplicate case id")
            continue
        cases[case_id] = case
        privacy = case.get("privacy")
        if not isinstance(privacy, dict) or privacy.get("deidentified") is not True:
            case_error(case_id, "case must be deidentified")
        if isinstance(privacy, dict) and privacy.get("raw_private_chat_included") is not False:
            case_error(case_id, "raw_private_chat_included must be false")
        if _safe_path(root, case.get("source_record"), f"{case_id} source record", errors) is None:
            invalid_cases.add(case_id)
        bucket = case.get("readiness_bucket")
        if bucket not in pilot_quotas:
            case_error(case_id, f"unknown readiness bucket {bucket!r}")
        row_ids = case.get("trainable_row_ids")
        if not isinstance(row_ids, list) or any(not isinstance(item, str) for item in row_ids):
            case_error(case_id, "trainable_row_ids must be a list of strings")
            row_ids = []
        if case.get("status") in eligible_statuses and not row_ids:
            case_error(case_id, "eligible case requires a non-empty trainable_row_ids inventory")
        expected_rows[case_id] = set(row_ids)
        trajectory_id = case.get("trajectory_id")
        if not isinstance(trajectory_id, str) or not trajectory_id:
            case_error(case_id, "missing trajectory_id")
        elif case.get("status") in eligible_statuses:
            previous = trajectory_owner.get(trajectory_id)
            if previous is not None:
                case_error(case_id, f"duplicate trajectory_id also owned by {previous}")
            else:
                trajectory_owner[trajectory_id] = case_id

    try:
        rows = _read_jsonl(candidates_path) if candidates_path else []
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"trainable candidates unreadable: {exc}")
        rows = []

    seen_row_ids: set[str] = set()
    actual_rows: dict[str, set[str]] = defaultdict(set)
    rows_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for index, row in enumerate(rows, 1):
        label = f"candidate row {index}"
        row_id = row.get("id")
        case_id = row.get("case_id")
        if not isinstance(row_id, str) or not row_id:
            errors.append(f"{label}: missing row id")
        elif row_id in seen_row_ids:
            errors.append(f"duplicate row id: {row_id}")
            if isinstance(case_id, str):
                invalid_cases.add(case_id)
        else:
            seen_row_ids.add(row_id)
        if case_id not in cases:
            errors.append(f"{label}: unknown case_id {case_id!r}")
        elif isinstance(row_id, str):
            actual_rows[case_id].add(row_id)
        trajectory_id = row.get("trajectory_id")
        if not isinstance(trajectory_id, str) or not trajectory_id:
            errors.append(f"{label}: missing trajectory_id")
            if isinstance(case_id, str):
                invalid_cases.add(case_id)
        if isinstance(case_id, str):
            rows_by_case[case_id].append(row)
        if case_id in cases and trajectory_id != cases[case_id].get("trajectory_id"):
            case_error(case_id, "row trajectory_id does not match case trajectory_id")

        provenance = row.get("provenance")
        task_status = row.get("task_status")
        if provenance not in ALLOWED_PROVENANCE:
            errors.append(f"{label}: unsupported provenance")
            if isinstance(case_id, str):
                invalid_cases.add(case_id)
        if task_status not in TASK_PROVENANCE:
            errors.append(f"{label}: unsupported task_status {task_status!r}")
            if isinstance(case_id, str):
                invalid_cases.add(case_id)
        elif provenance not in TASK_PROVENANCE[task_status]:
            errors.append(f"{label}: task_status and provenance combination is not allowed")
            if isinstance(case_id, str):
                invalid_cases.add(case_id)
        if _safe_path(root, row.get("source_record"), f"{label} source record", errors) is None and isinstance(case_id, str):
            invalid_cases.add(case_id)
        split = row.get("split")
        if split not in ALLOWED_SPLITS:
            errors.append(f"{label}: unsupported split {split!r}")
            if isinstance(case_id, str):
                invalid_cases.add(case_id)

        messages_value = row.get("messages")
        if not isinstance(messages_value, list) or not messages_value or any(
            not isinstance(message, dict) for message in messages_value
        ):
            errors.append(f"{label}: messages must be a non-empty list of objects")
            if isinstance(case_id, str):
                invalid_cases.add(case_id)
            continue
        messages = messages_value
        supervised_value = row.get("supervise_message_indices")
        if not isinstance(supervised_value, list) or not supervised_value:
            errors.append(f"{label}: supervise_message_indices must be non-empty")
            if isinstance(case_id, str):
                invalid_cases.add(case_id)
            continue
        supervised = supervised_value
        before = len(errors)
        for message_index in supervised:
            if not isinstance(message_index, int) or not 0 <= message_index < len(messages):
                errors.append(f"{label}: supervision index is out of range")
            elif messages[message_index].get("role") != "assistant":
                errors.append(f"{label}: supervision must target an assistant message")
        _validate_target(root, row, messages, supervised, label, approved_safe_tools, errors)
        if len(errors) != before and isinstance(case_id, str):
            invalid_cases.add(case_id)

    for case_id, case in cases.items():
        if expected_rows.get(case_id, set()) != actual_rows.get(case_id, set()):
            case_error(case_id, "trainable row inventory does not match candidates.jsonl")
        expected_statuses = CASE_TASK_STATUS.get(case.get("status"))
        if expected_statuses is not None and any(
            row.get("task_status") not in expected_statuses for row in rows_by_case.get(case_id, [])
        ):
            case_error(case_id, "case status and row task_status combination is not allowed")

    for case_id, trajectory_rows in rows_by_case.items():
        trajectory_id = cases.get(case_id, {}).get("trajectory_id", case_id)
        splits = {row.get("split") for row in trajectory_rows}
        if len(splits) != 1:
            errors.append(f"{trajectory_id}: all trajectory rows must stay in one split")
            invalid_cases.add(case_id)
        totals = {row.get("trajectory_steps") for row in trajectory_rows}
        steps = {row.get("trajectory_step") for row in trajectory_rows}
        expected_steps = set(range(1, len(trajectory_rows) + 1))
        if len(totals) != 1 or totals != {len(trajectory_rows)} or steps != expected_steps:
            errors.append(f"{trajectory_id}: trajectory steps must be contiguous and match row count")
            invalid_cases.add(case_id)

    bucket_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    semantic_families: set[str] = set()
    eligible_trajectories: set[str] = set()
    for case_id, case in cases.items():
        if case.get("status") not in eligible_statuses or case_id in invalid_cases:
            continue
        trajectory_id = case.get("trajectory_id")
        case_rows = [row for row in rows if row.get("case_id") == case_id]
        if not case_rows or trajectory_id in eligible_trajectories:
            continue
        eligible_trajectories.add(trajectory_id)
        bucket_counts[case.get("readiness_bucket")] += 1
        split_counts[case_rows[0].get("split")] += 1
        family = case.get("task_family") or case_rows[0].get("family_id")
        if isinstance(family, str) and family:
            semantic_families.add(family)

    remaining_by_bucket = {
        bucket: max(0, target - bucket_counts.get(bucket, 0)) for bucket, target in pilot_quotas.items()
    }
    full_remaining_by_bucket = {
        bucket: max(0, target - bucket_counts.get(bucket, 0)) for bucket, target in full_quotas.items()
    }
    pilot_remaining = sum(remaining_by_bucket.values())
    full_remaining = sum(full_remaining_by_bucket.values())
    minimum_families = policy.get("minimum_semantic_families")
    if not isinstance(minimum_families, dict):
        errors.append("minimum_semantic_families must be an object")
        minimum_families = {}
    pilot_family_gate = len(semantic_families) >= minimum_families.get("pilot", 0)
    full_family_gate = len(semantic_families) >= minimum_families.get("full_candidate", 0)
    split_gate = policy.get("split_gate") if isinstance(policy.get("split_gate"), dict) else {}
    pilot_split_gate = _gate_met(split_counts, split_gate.get("pilot"))
    full_split_gate = _gate_met(split_counts, split_gate.get("full_candidate"))

    valid = not errors
    return {
        "valid": valid,
        "errors": errors,
        "case_count": len(cases),
        "eligible_trajectory_count": len(eligible_trajectories),
        "trainable_row_count": len(rows),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "split_counts": {split: split_counts.get(split, 0) for split in sorted(ALLOWED_SPLITS)},
        "semantic_family_count": len(semantic_families),
        "pilot_target": sum(pilot_quotas.values()),
        "pilot_remaining": pilot_remaining,
        "remaining_by_bucket": remaining_by_bucket,
        "pilot_semantic_family_gate_met": pilot_family_gate,
        "pilot_split_gate_met": pilot_split_gate,
        "pilot_pool_complete": valid and pilot_remaining == 0 and pilot_family_gate and pilot_split_gate,
        "full_candidate_target": sum(full_quotas.values()),
        "full_candidate_remaining": full_remaining,
        "full_remaining_by_bucket": full_remaining_by_bucket,
        "full_candidate_semantic_family_gate_met": full_family_gate,
        "full_candidate_split_gate_met": full_split_gate,
        "full_candidate_pool_complete": valid and full_remaining == 0 and full_family_gate and full_split_gate,
        "training_authorized": False,
        "unit": policy.get("unit"),
    }


def write_report(root: Path, output: Path, report: dict[str, Any]) -> None:
    if _has_symlink_component(root):
        raise ValueError("dataset root ancestor symlink is not allowed")
    root = _lexical_root(root)
    output = _safe_path(root, output, "output", [], must_exist=False, expect_file=None)
    if output is None:
        raise ValueError("output must stay under dataset root and must not use symlinks")
    parent_errors: list[str] = []
    parent = _safe_path(root, output.parent, "output parent", parent_errors, must_exist=False, expect_file=None)
    if parent is None:
        raise ValueError("output parent must stay under dataset root and must not use symlinks")
    parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError("output symlink is not allowed")
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_published(root: Path) -> dict[str, Any]:
    original_root = Path(root)
    if _has_symlink_component(original_root):
        return {"valid": False, "errors": ["dataset root ancestor symlink is not allowed"]}
    root = _lexical_root(original_root)
    errors: list[str] = []
    computed = validate_dataset(root)
    errors.extend(computed.get("errors", []))
    manifest_path = _safe_path(root, "manifest.json", "manifest", errors)
    report_path = _safe_path(root, "readiness-report.json", "readiness report", errors)
    candidates_path = _safe_path(root, "trainable/candidates.jsonl", "published trainable candidates", errors)
    if manifest_path is None or report_path is None or candidates_path is None:
        return {"valid": False, "errors": errors}
    try:
        manifest = _read_json(manifest_path)
        published_report = _read_json(report_path)
        rows = _read_jsonl(candidates_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"valid": False, "errors": errors + [f"published artifact unreadable: {exc}"]}

    expected_manifest = {
        "case_count": computed.get("case_count"),
        "independent_trajectory_count": computed.get("eligible_trajectory_count"),
        "trainable_safe_prefix_rows": sum(1 for row in rows if row.get("task_status") == "safe_prefix"),
        "grounded_completion_rows": sum(1 for row in rows if row.get("task_status") == "grounded_completion"),
        "raw_tool_result_rows": sum(
            1
            for row in rows
            if any(isinstance(message, dict) and message.get("role") == "tool" for message in row.get("messages", []))
        ),
        "pilot_target_trajectories": computed.get("pilot_target"),
        "pilot_remaining_trajectories": computed.get("pilot_remaining"),
        "full_candidate_target_trajectories": computed.get("full_candidate_target"),
        "full_candidate_remaining_trajectories": computed.get("full_candidate_remaining"),
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            errors.append(f"manifest {key} does not match computed dataset")
    authorization = manifest.get("authorization_boundaries")
    if not isinstance(authorization, dict) or authorization.get("training") is not False:
        errors.append("manifest must explicitly keep training authorization false")
    if not isinstance(authorization, dict) or authorization.get("deployment") is not False:
        errors.append("manifest must explicitly keep deployment authorization false")

    required_hashes = {
        "readiness-policy.json",
        "readiness-report.json",
        "trainable/candidates.jsonl",
    }
    for case_path in sorted((root / "cases").glob("*.json")):
        required_hashes.add(case_path.relative_to(root).as_posix())
        try:
            case = _read_json(case_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        source_record = case.get("source_record")
        if isinstance(source_record, str):
            required_hashes.add(source_record)
    for row in rows:
        for evidence in row.get("evidence_paths", []):
            if isinstance(evidence, str):
                required_hashes.add(evidence)

    hashes = manifest.get("hashes")
    if not isinstance(hashes, dict) or set(hashes) != required_hashes:
        errors.append("manifest hash inventory does not exactly match required published artifacts")
        hashes = hashes if isinstance(hashes, dict) else {}
    for relative, expected_hash in hashes.items():
        artifact = _safe_path(root, relative, f"manifest hash {relative}", errors)
        if artifact is not None:
            actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if actual != expected_hash:
                errors.append(f"manifest hash mismatch: {relative}")
    if published_report != computed:
        errors.append("readiness report does not match computed dataset")
    return {"valid": not errors, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-published", action="store_true")
    args = parser.parse_args()
    if args.verify_published:
        report = verify_published(args.dataset_root)
    else:
        report = validate_dataset(args.dataset_root)
        if args.output:
            write_report(args.dataset_root, args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
