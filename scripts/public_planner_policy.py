"""Explicit per-store planner policy; leaves account/transport quotas unchanged."""
def goal_completion_stores(manifest, requested=()):
    configured = manifest.get("goal_completion_stores", [])
    if not isinstance(configured, list) or any(type(x) is not str or not x for x in configured):
        raise ValueError("goal_completion_stores must be an explicit list of store names")
    requested = list(requested)
    if any(type(x) is not str or not x for x in requested):
        raise ValueError("goal-completion store names must be nonempty strings")
    selected = set(configured) | set(requested)
    unknown = selected - set(manifest["stores"])
    if unknown:
        raise ValueError("Unknown goal-completion store: " + ", ".join(sorted(unknown)))
    return sorted(selected)


def planner_options(store, selected):
    return {"planner_response_limit": None} if store in selected else {}
