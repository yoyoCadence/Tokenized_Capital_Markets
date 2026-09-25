from collections import deque


def affected_by_event(project, event):
    """Graph reachability is a research queue, not an assertion of economic capture."""
    edges = project["graph"]["edges"]
    discovered = set(event["affected_nodes"])
    queue = deque(discovered)
    traversed = []
    while queue:
        node = queue.popleft()
        for edge in edges:
            if edge["from"] == node:
                traversed.append(edge)
                if edge["to"] not in discovered:
                    discovered.add(edge["to"])
                    queue.append(edge["to"])
    return {"event_id": event["id"], "event_status": event["status"],
            "affected_nodes": sorted(discovered), "direct_nodes": event["affected_nodes"],
            "economic_edges": [e for e in traversed if e["economic_transmission"]],
            "other_edges": [e for e in traversed if not e["economic_transmission"]],
            "observation_ids": event["observation_ids"],
            "note": "ASSUMED or PLANNED edges signal research dependencies; they do not establish holder value."}
