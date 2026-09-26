"""Shared, serializable diagnostics for file, CLI, API and library boundaries."""


def issue(level, code, message, path=""):
    return {"level": level, "code": code, "message": message, "path": str(path)}


class ValidationError(ValueError):
    def __init__(self, issues):
        self.issues = list(issues)
        summary = "; ".join(f"{i['code']} at {i['path']}: {i['message']}" for i in self.issues[:5])
        if len(self.issues) > 5:
            summary += f"; {len(self.issues) - 5} more issue(s)"
        super().__init__(summary)


def reject_errors(issues):
    if any(item["level"] == "ERROR" for item in issues):
        raise ValidationError(issues)


def location(project, section, index=None):
    """Locations live beside records, never inside canonical evidence/fingerprints."""
    locations = project.get("_locations", {})
    origin = locations.get(section) if isinstance(locations, dict) else None
    if index is None:
        return origin if isinstance(origin, str) else section
    if isinstance(origin, list) and index < len(origin):
        return origin[index]
    return f"{section}[{index}]"
