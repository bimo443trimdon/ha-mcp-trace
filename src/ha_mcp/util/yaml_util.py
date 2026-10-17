import yaml
from typing import Any

def to_yaml(data: Any, *, indent: int = 2) -> str:
    """Convert data to a nicely formatted YAML string."""
    return yaml.dump(
        data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        indent=indent,
    ).rstrip()

def from_yaml(text: str) -> Any:
    """Parse a YAML string safely."""
    return yaml.safe_load(text)

def validate_yaml_syntax(text: str) -> tuple[bool, str]:
    """Check if a string is valid YAML syntax.

    Returns (is_valid, error_message).
    """
    try:
        yaml.safe_load(text)
        return True, ""
    except yaml.YAMLError as e:
        return False, str(e)

def diff_configs(old: dict, new: dict) -> str:
    """Generate a human-readable diff between two configs."""
    old_yaml = to_yaml(old)
    new_yaml = to_yaml(new)

    if old_yaml == new_yaml:
        return "No changes detected."

    import difflib
    diff = difflib.unified_diff(
        old_yaml.splitlines(keepends=True),
        new_yaml.splitlines(keepends=True),
        fromfile="current",
        tofile="proposed",
    )
    return "".join(diff) or "No differences."
