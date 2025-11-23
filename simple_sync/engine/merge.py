"""Three-way merge support for text files."""

from __future__ import annotations

import difflib
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from simple_sync import types


@dataclass
class MergeResult:
    """Result of a merge attempt."""

    success: bool
    content: Optional[str] = None
    conflicts: List[str] = None

    def __post_init__(self) -> None:
        if self.conflicts is None:
            object.__setattr__(self, "conflicts", [])


def is_text_file(path: str | Path) -> bool:
    """Determine if a file is likely a text file based on extension."""
    # Common text file extensions
    text_extensions = {
        ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
        ".cs", ".rb", ".go", ".rs", ".php", ".html", ".css", ".scss", ".sass", ".less",
        ".xml", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".sh", ".bash",
        ".zsh", ".fish", ".sql", ".r", ".R", ".m", ".swift", ".kt", ".scala", ".clj",
        ".hs", ".ml", ".ex", ".exs", ".erl", ".pl", ".pm", ".lua", ".vim", ".el",
        ".tex", ".rst", ".adoc", ".org", ".cmake", ".gradle", ".properties", ".env",
        ".gitignore", ".dockerignore", ".editorconfig", ".eslintrc", ".prettierrc",
    }

    path_obj = Path(path) if isinstance(path, str) else path
    suffix = path_obj.suffix.lower()

    # Avoid merging generic .txt files; they're often user content better handled by policy
    if suffix == ".txt":
        return False

    # Check extension
    if suffix in text_extensions:
        return True

    # Check mimetype
    mime_type, _ = mimetypes.guess_type(str(path_obj))
    if mime_type and mime_type.startswith("text/"):
        return True

    return False


def is_binary_content(content: bytes) -> bool:
    """Check if content appears to be binary by looking for null bytes."""
    # Check first 8KB for null bytes (standard heuristic)
    sample_size = min(8192, len(content))
    return b'\x00' in content[:sample_size]


def merge_three_way(base: str, current_a: str, current_b: str) -> MergeResult:
    """
    Perform a three-way merge similar to git merge.

    Args:
        base: The common ancestor content
        current_a: Content from endpoint A
        current_b: Content from endpoint B

    Returns:
        MergeResult indicating success or failure with merged content
    """
    # Split into lines for diffing
    base_lines = base.splitlines(keepends=True)
    a_lines = current_a.splitlines(keepends=True)
    b_lines = current_b.splitlines(keepends=True)

    # Use difflib.Differ to find differences
    differ = difflib.Differ()

    # Compute diffs from base to each version
    diff_a = list(difflib.unified_diff(base_lines, a_lines, lineterm=''))
    diff_b = list(difflib.unified_diff(base_lines, b_lines, lineterm=''))

    # If one side is unchanged, use the other side
    if not diff_a or len(diff_a) <= 2:  # unified_diff header is 2 lines
        return MergeResult(success=True, content=current_b)
    if not diff_b or len(diff_b) <= 2:
        return MergeResult(success=True, content=current_a)

    # Try automatic merge using difflib.merge
    try:
        merged_lines = _merge_lines(base_lines, a_lines, b_lines)
        if merged_lines is not None:
            merged_content = ''.join(merged_lines)
            return MergeResult(success=True, content=merged_content)
    except Exception:
        pass

    # If automatic merge fails, create a conflict-marked version
    conflict_content = _create_conflict_markers(base_lines, a_lines, b_lines)
    return MergeResult(
        success=False,
        content=conflict_content,
        conflicts=["Automatic merge failed - manual resolution required"]
    )


def _merge_lines(
    base_lines: List[str],
    a_lines: List[str],
    b_lines: List[str]
) -> Optional[List[str]]:
    """
    Attempt to merge lines automatically.

    Returns None if there are conflicts that can't be auto-resolved.
    """
    # Get operations that transform base -> a and base -> b
    sm_a = difflib.SequenceMatcher(None, base_lines, a_lines)
    sm_b = difflib.SequenceMatcher(None, base_lines, b_lines)

    opcodes_a = sm_a.get_opcodes()
    opcodes_b = sm_b.get_opcodes()

    # Check for overlapping changes (conflicts)
    for tag_a, i1_a, i2_a, j1_a, j2_a in opcodes_a:
        if tag_a == 'equal':
            continue
        for tag_b, i1_b, i2_b, j1_b, j2_b in opcodes_b:
            if tag_b == 'equal':
                continue
            # Check if the changes overlap in the base
            if not (i2_a <= i1_b or i2_b <= i1_a):
                # Overlapping changes - conflict
                return None

    # No conflicts - merge the changes
    result = []
    base_idx = 0
    changes_a = {(i1, i2): (j1, j2) for tag, i1, i2, j1, j2 in opcodes_a if tag != 'equal'}
    changes_b = {(i1, i2): (j1, j2) for tag, i1, i2, j1, j2 in opcodes_b if tag != 'equal'}

    # Combine all change points
    all_points = set()
    for i1, i2 in changes_a.keys():
        all_points.add(i1)
        all_points.add(i2)
    for i1, i2 in changes_b.keys():
        all_points.add(i1)
        all_points.add(i2)
    all_points.add(0)
    all_points.add(len(base_lines))

    sorted_points = sorted(all_points)

    for i in range(len(sorted_points) - 1):
        start = sorted_points[i]
        end = sorted_points[i + 1]

        # Check if this range was modified in a or b
        modified_in_a = None
        modified_in_b = None

        for (i1, i2), (j1, j2) in changes_a.items():
            if i1 == start and i2 == end:
                modified_in_a = (j1, j2)
                break

        for (i1, i2), (j1, j2) in changes_b.items():
            if i1 == start and i2 == end:
                modified_in_b = (j1, j2)
                break

        if modified_in_a and modified_in_b:
            # Both modified the same region - conflict
            return None
        elif modified_in_a:
            j1, j2 = modified_in_a
            result.extend(a_lines[j1:j2])
        elif modified_in_b:
            j1, j2 = modified_in_b
            result.extend(b_lines[j1:j2])
        else:
            # No changes, use base
            result.extend(base_lines[start:end])

    return result


def _create_conflict_markers(
    base_lines: List[str],
    a_lines: List[str],
    b_lines: List[str]
) -> str:
    """Create a file with git-style conflict markers."""
    result = []
    result.append("<<<<<<< LOCAL\n")
    result.extend(a_lines)
    if not a_lines or not a_lines[-1].endswith('\n'):
        result.append('\n')
    result.append("=======\n")
    result.extend(b_lines)
    if not b_lines or not b_lines[-1].endswith('\n'):
        result.append('\n')
    result.append(">>>>>>> REMOTE\n")
    return ''.join(result)


__all__ = [
    "MergeResult",
    "is_text_file",
    "is_binary_content",
    "merge_three_way",
]
