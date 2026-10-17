"""Rule-based pattern matching engine for suggesting automations.

Analyzes Home Assistant entities, areas, and existing automations to suggest
new automations, detect conflicts, and recommend dashboard layouts.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_entity_domain(entity_id: str) -> str:
    """Extract the domain portion of an entity_id (e.g. 'light' from 'light.kitchen')."""
    return entity_id.split(".")[0] if "." in entity_id else ""


def _get_entities_in_area(
    entities: list[dict],
    area_id: str,
) -> list[dict]:
    """Return entities that belong to a given area."""
    return [e for e in entities if e.get("area_id") == area_id]


def _extract_entity_ids_from_config(config: dict) -> set[str]:
    """Recursively extract every entity_id reference from an automation config.

    Walks through triggers, conditions, actions, and any nested structure
    looking for keys typically holding entity references.
    """
    entity_ids: set[str] = set()
    _ENTITY_KEYS = {
        "entity_id", "entity", "target", "service_data",
        "data", "data_template",
    }
    _ENTITY_ID_RE = re.compile(
        r"\b([a-z_]+\.[a-z0-9_]+)\b"
    )

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in ("entity_id", "entity"):
                    if isinstance(value, str):
                        for eid in value.split(","):
                            eid = eid.strip()
                            if "." in eid:
                                entity_ids.add(eid)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str) and "." in item:
                                entity_ids.add(item.strip())
                else:
                    _walk(value)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(config)
    return entity_ids


def _build_suggestion_config(
    alias: str,
    description: str,
    triggers: list[dict],
    actions: list[dict],
    conditions: list[dict] | None = None,
    mode: str = "single",
) -> dict:
    """Build a ready-to-use Home Assistant automation configuration dict."""
    config: dict[str, Any] = {
        "alias": alias,
        "description": description,
        "mode": mode,
        "triggers": triggers,
        "actions": actions,
    }
    if conditions:
        config["conditions"] = conditions
    return config


def _entity_has_device_class(entity: dict, device_class: str) -> bool:
    """Check whether an entity has a given device_class (in attributes or top-level)."""
    if entity.get("device_class") == device_class:
        return True
    attrs = entity.get("attributes", {})
    return attrs.get("device_class") == device_class


def _entities_of_domain(entities: list[dict], domain: str) -> list[dict]:
    """Filter entities to those matching a specific domain."""
    return [
        e for e in entities
        if _get_entity_domain(e.get("entity_id", "")) == domain
    ]


def _entity_id_covered(entity_id: str, covered_ids: set[str]) -> bool:
    """Check if an entity_id is referenced by any existing automation."""
    return entity_id in covered_ids


def _collect_all_automation_entity_ids(automations: list[dict]) -> set[str]:
    """Return the union of all entity_ids referenced across all automations."""
    all_ids: set[str] = set()
    for auto in automations:
        all_ids |= _extract_entity_ids_from_config(auto)
    return all_ids


def _resolve_entity_area(entity: dict, entities: list[dict]) -> str | None:
    """Return the area_id for an entity, falling back to None."""
    return entity.get("area_id") or None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_coverage(
    entities: list[dict],
    automations: list[dict],
    areas: list[dict],
) -> dict:
    """Analyze which entities are covered by automations and which are not.

    Returns:
        {
            "total_entities": int,
            "covered_entities": list[str],
            "uncovered_entities": list[str],
            "coverage_percentage": float,
            "by_area": {
                area_id: {
                    "total": int,
                    "covered": int,
                    "uncovered": list[str],
                }
            },
        }
    """
    covered_ids = _collect_all_automation_entity_ids(automations)

    all_entity_ids = [e.get("entity_id", "") for e in entities if e.get("entity_id")]
    covered = sorted(eid for eid in all_entity_ids if eid in covered_ids)
    uncovered = sorted(eid for eid in all_entity_ids if eid not in covered_ids)

    total = len(all_entity_ids)
    coverage_pct = (len(covered) / total * 100.0) if total else 0.0

    # Per-area breakdown
    by_area: dict[str, dict] = {}
    # Build a mapping of area_id -> entity_ids
    area_entity_map: dict[str, list[str]] = {a.get("area_id", ""): [] for a in areas}
    unassigned: list[str] = []
    for e in entities:
        eid = e.get("entity_id", "")
        if not eid:
            continue
        a_id = e.get("area_id")
        if a_id and a_id in area_entity_map:
            area_entity_map[a_id].append(eid)
        else:
            unassigned.append(eid)

    for area in areas:
        a_id = area.get("area_id", "")
        eids = area_entity_map.get(a_id, [])
        area_covered = [eid for eid in eids if eid in covered_ids]
        area_uncovered = [eid for eid in eids if eid not in covered_ids]
        by_area[a_id] = {
            "total": len(eids),
            "covered": len(area_covered),
            "uncovered": area_uncovered,
        }

    # Include unassigned entities under a synthetic key
    if unassigned:
        by_area["_unassigned"] = {
            "total": len(unassigned),
            "covered": len([u for u in unassigned if u in covered_ids]),
            "uncovered": [u for u in unassigned if u not in covered_ids],
        }

    return {
        "total_entities": total,
        "covered_entities": covered,
        "uncovered_entities": uncovered,
        "coverage_percentage": round(coverage_pct, 1),
        "by_area": by_area,
    }


def generate_suggestions(
    entities: list[dict],
    automations: list[dict],
    areas: list[dict],
    target_area_id: str | None = None,
    target_entity_id: str | None = None,
) -> list[dict]:
    """Generate automation suggestions based on entity types and existing automations.

    Returns a list of suggestion dicts, each containing:
        - title: str
        - description: str
        - entity_ids: list[str]
        - area_id: str | None
        - priority: "high" | "medium" | "low"
        - category: str
        - suggested_config: dict  (ready-to-use HA automation config)
    """
    suggestions: list[dict] = []
    covered_ids = _collect_all_automation_entity_ids(automations)

    # If targeting a single entity, narrow the working set
    if target_entity_id:
        entities = [e for e in entities if e.get("entity_id") == target_entity_id]

    # Build area lookup: area_id -> list[dict]
    area_entities: dict[str | None, list[dict]] = {}
    for e in entities:
        a_id = e.get("area_id") or None
        area_entities.setdefault(a_id, []).append(e)

    # If targeting a specific area, keep only that area
    if target_area_id:
        area_entities = {
            k: v for k, v in area_entities.items()
            if k == target_area_id
        }

    # ------------------------------------------------------------------
    # Rule 1: Motion sensor + light in same area -> motion-activated lighting
    # ------------------------------------------------------------------
    for a_id, area_ents in area_entities.items():
        motion_sensors = [
            e for e in area_ents
            if _get_entity_domain(e.get("entity_id", "")) == "binary_sensor"
            and _entity_has_device_class(e, "motion")
        ]
        lights = _entities_of_domain(area_ents, "light")

        if motion_sensors and lights:
            motion_ids = [e["entity_id"] for e in motion_sensors]
            light_ids = [e["entity_id"] for e in lights]
            involved = motion_ids + light_ids
            if not all(_entity_id_covered(eid, covered_ids) for eid in involved):
                area_name = _area_name(areas, a_id)
                title = f"Motion-activated lighting in {area_name}"
                suggestions.append({
                    "title": title,
                    "description": (
                        f"Turn on lights when motion is detected in {area_name}, "
                        "and turn them off after a period of no motion."
                    ),
                    "entity_ids": involved,
                    "area_id": a_id,
                    "priority": "high",
                    "category": "motion_lighting",
                    "suggested_config": _build_suggestion_config(
                        alias=title,
                        description=f"Automatically control lights in {area_name} based on motion.",
                        triggers=[
                            {
                                "trigger": "state",
                                "entity_id": motion_ids,
                                "to": "on",
                            },
                        ],
                        actions=[
                            {
                                "action": "light.turn_on",
                                "target": {"entity_id": light_ids},
                            },
                            {
                                "wait_for_trigger": [
                                    {
                                        "trigger": "state",
                                        "entity_id": motion_ids,
                                        "to": "off",
                                        "for": {"minutes": 5},
                                    }
                                ],
                            },
                            {
                                "action": "light.turn_off",
                                "target": {"entity_id": light_ids},
                            },
                        ],
                        mode="restart",
                    ),
                })

    # ------------------------------------------------------------------
    # Rule 2: Door sensor alone -> "door left open" alert
    # ------------------------------------------------------------------
    for a_id, area_ents in area_entities.items():
        door_sensors = [
            e for e in area_ents
            if _get_entity_domain(e.get("entity_id", "")) == "binary_sensor"
            and _entity_has_device_class(e, "door")
        ]
        for ds in door_sensors:
            eid = ds["entity_id"]
            if _entity_id_covered(eid, covered_ids):
                continue
            area_name = _area_name(areas, a_id)
            friendly = ds.get("name") or ds.get("attributes", {}).get("friendly_name", eid)
            title = f"Door left open alert: {friendly}"
            suggestions.append({
                "title": title,
                "description": (
                    f"Send a notification if {friendly} in {area_name} "
                    "has been open for more than 5 minutes."
                ),
                "entity_ids": [eid],
                "area_id": a_id,
                "priority": "medium",
                "category": "door_alert",
                "suggested_config": _build_suggestion_config(
                    alias=title,
                    description=f"Alert when {friendly} is left open too long.",
                    triggers=[
                        {
                            "trigger": "state",
                            "entity_id": eid,
                            "to": "on",
                            "for": {"minutes": 5},
                        },
                    ],
                    actions=[
                        {
                            "action": "notify.persistent_notification",
                            "data": {
                                "title": "Door Left Open",
                                "message": f"{friendly} has been open for 5 minutes.",
                            },
                        },
                    ],
                ),
            })

    # ------------------------------------------------------------------
    # Rule 3: Window sensor + climate in same area -> turn off climate
    # ------------------------------------------------------------------
    for a_id, area_ents in area_entities.items():
        window_sensors = [
            e for e in area_ents
            if _get_entity_domain(e.get("entity_id", "")) == "binary_sensor"
            and _entity_has_device_class(e, "window")
        ]
        climate_ents = _entities_of_domain(area_ents, "climate")

        if window_sensors and climate_ents:
            window_ids = [e["entity_id"] for e in window_sensors]
            climate_ids = [e["entity_id"] for e in climate_ents]
            involved = window_ids + climate_ids
            if not all(_entity_id_covered(eid, covered_ids) for eid in involved):
                area_name = _area_name(areas, a_id)
                title = f"Turn off climate when window open in {area_name}"
                suggestions.append({
                    "title": title,
                    "description": (
                        f"Turn off climate control in {area_name} when a window is opened "
                        "to save energy, and restore it when the window is closed."
                    ),
                    "entity_ids": involved,
                    "area_id": a_id,
                    "priority": "high",
                    "category": "window_climate",
                    "suggested_config": _build_suggestion_config(
                        alias=title,
                        description=f"Save energy by pausing climate when windows are open in {area_name}.",
                        triggers=[
                            {
                                "trigger": "state",
                                "entity_id": window_ids,
                                "to": "on",
                            },
                        ],
                        actions=[
                            {
                                "action": "climate.turn_off",
                                "target": {"entity_id": climate_ids},
                            },
                            {
                                "wait_for_trigger": [
                                    {
                                        "trigger": "state",
                                        "entity_id": window_ids,
                                        "to": "off",
                                    },
                                ],
                            },
                            {
                                "action": "climate.turn_on",
                                "target": {"entity_id": climate_ids},
                            },
                        ],
                        mode="restart",
                    ),
                })

    # ------------------------------------------------------------------
    # Rule 4: Battery sensors -> low battery alerts
    # ------------------------------------------------------------------
    battery_sensors = [
        e for e in entities
        if _get_entity_domain(e.get("entity_id", "")) == "sensor"
        and _entity_has_device_class(e, "battery")
    ]
    # Filter by target area if set
    if target_area_id:
        battery_sensors = [e for e in battery_sensors if e.get("area_id") == target_area_id]

    for bs in battery_sensors:
        eid = bs["entity_id"]
        if _entity_id_covered(eid, covered_ids):
            continue
        friendly = bs.get("name") or bs.get("attributes", {}).get("friendly_name", eid)
        title = f"Low battery alert: {friendly}"
        suggestions.append({
            "title": title,
            "description": f"Notify when {friendly} battery drops below 20%.",
            "entity_ids": [eid],
            "area_id": bs.get("area_id"),
            "priority": "medium",
            "category": "battery_alert",
            "suggested_config": _build_suggestion_config(
                alias=title,
                description=f"Alert when {friendly} battery is low.",
                triggers=[
                    {
                        "trigger": "numeric_state",
                        "entity_id": eid,
                        "below": 20,
                    },
                ],
                actions=[
                    {
                        "action": "notify.persistent_notification",
                        "data": {
                            "title": "Low Battery Warning",
                            "message": f"{friendly} battery is below 20%.",
                        },
                    },
                ],
            ),
        })

    # ------------------------------------------------------------------
    # Rule 5: Lock entities -> auto-lock and notifications
    # ------------------------------------------------------------------
    locks = [
        e for e in entities
        if _get_entity_domain(e.get("entity_id", "")) == "lock"
    ]
    if target_area_id:
        locks = [e for e in locks if e.get("area_id") == target_area_id]

    for lk in locks:
        eid = lk["entity_id"]
        if _entity_id_covered(eid, covered_ids):
            continue
        friendly = lk.get("name") or lk.get("attributes", {}).get("friendly_name", eid)

        # Auto-lock suggestion
        title_auto = f"Auto-lock: {friendly}"
        suggestions.append({
            "title": title_auto,
            "description": (
                f"Automatically lock {friendly} after it has been unlocked for 10 minutes."
            ),
            "entity_ids": [eid],
            "area_id": lk.get("area_id"),
            "priority": "high",
            "category": "lock_auto",
            "suggested_config": _build_suggestion_config(
                alias=title_auto,
                description=f"Auto-lock {friendly} after 10 minutes.",
                triggers=[
                    {
                        "trigger": "state",
                        "entity_id": eid,
                        "to": "unlocked",
                        "for": {"minutes": 10},
                    },
                ],
                actions=[
                    {
                        "action": "lock.lock",
                        "target": {"entity_id": eid},
                    },
                    {
                        "action": "notify.persistent_notification",
                        "data": {
                            "title": "Auto-Locked",
                            "message": f"{friendly} was automatically locked after 10 minutes.",
                        },
                    },
                ],
            ),
        })

        # Unlock notification
        title_notif = f"Unlock notification: {friendly}"
        suggestions.append({
            "title": title_notif,
            "description": f"Send a notification whenever {friendly} is unlocked.",
            "entity_ids": [eid],
            "area_id": lk.get("area_id"),
            "priority": "medium",
            "category": "lock_notification",
            "suggested_config": _build_suggestion_config(
                alias=title_notif,
                description=f"Notify when {friendly} is unlocked.",
                triggers=[
                    {
                        "trigger": "state",
                        "entity_id": eid,
                        "to": "unlocked",
                    },
                ],
                actions=[
                    {
                        "action": "notify.persistent_notification",
                        "data": {
                            "title": "Lock Unlocked",
                            "message": f"{friendly} has been unlocked.",
                        },
                    },
                ],
            ),
        })

    # ------------------------------------------------------------------
    # Rule 6: Climate entities -> presence-based climate control
    # ------------------------------------------------------------------
    climate_all = [
        e for e in entities
        if _get_entity_domain(e.get("entity_id", "")) == "climate"
    ]
    if target_area_id:
        climate_all = [e for e in climate_all if e.get("area_id") == target_area_id]

    for cl in climate_all:
        eid = cl["entity_id"]
        if _entity_id_covered(eid, covered_ids):
            continue
        friendly = cl.get("name") or cl.get("attributes", {}).get("friendly_name", eid)
        area_name = _area_name(areas, cl.get("area_id"))
        title = f"Presence-based climate: {friendly}"
        suggestions.append({
            "title": title,
            "description": (
                f"Control {friendly} based on home occupancy. "
                "Turn off when everyone leaves, restore when someone arrives."
            ),
            "entity_ids": [eid],
            "area_id": cl.get("area_id"),
            "priority": "medium",
            "category": "climate_presence",
            "suggested_config": _build_suggestion_config(
                alias=title,
                description=f"Control {friendly} based on presence.",
                triggers=[
                    {
                        "trigger": "state",
                        "entity_id": "zone.home",
                        "attribute": "persons",
                    },
                ],
                conditions=[
                    {
                        "condition": "numeric_state",
                        "entity_id": "zone.home",
                        "below": 1,
                    },
                ],
                actions=[
                    {
                        "action": "climate.set_hvac_mode",
                        "target": {"entity_id": eid},
                        "data": {"hvac_mode": "off"},
                    },
                ],
            ),
        })

    # ------------------------------------------------------------------
    # Rule 7: Light entities with no automation -> schedule/presence lighting
    # ------------------------------------------------------------------
    all_lights = [
        e for e in entities
        if _get_entity_domain(e.get("entity_id", "")) == "light"
    ]
    if target_area_id:
        all_lights = [e for e in all_lights if e.get("area_id") == target_area_id]

    for lt in all_lights:
        eid = lt["entity_id"]
        if _entity_id_covered(eid, covered_ids):
            continue
        friendly = lt.get("name") or lt.get("attributes", {}).get("friendly_name", eid)
        area_name = _area_name(areas, lt.get("area_id"))
        title = f"Scheduled lighting: {friendly}"
        suggestions.append({
            "title": title,
            "description": (
                f"Turn {friendly} on at sunset and off at a set time, "
                "providing automatic daily lighting."
            ),
            "entity_ids": [eid],
            "area_id": lt.get("area_id"),
            "priority": "low",
            "category": "light_schedule",
            "suggested_config": _build_suggestion_config(
                alias=title,
                description=f"Schedule {friendly} to turn on at sunset and off at 23:00.",
                triggers=[
                    {
                        "trigger": "sun",
                        "event": "sunset",
                    },
                ],
                actions=[
                    {
                        "action": "light.turn_on",
                        "target": {"entity_id": eid},
                    },
                    {
                        "delay": {"hours": 4},
                    },
                    {
                        "action": "light.turn_off",
                        "target": {"entity_id": eid},
                    },
                ],
            ),
        })

    # ------------------------------------------------------------------
    # Rule 8: Media player entities -> media-based lighting scenes
    # ------------------------------------------------------------------
    media_players = [
        e for e in entities
        if _get_entity_domain(e.get("entity_id", "")) == "media_player"
    ]
    if target_area_id:
        media_players = [e for e in media_players if e.get("area_id") == target_area_id]

    for mp in media_players:
        mp_eid = mp["entity_id"]
        if _entity_id_covered(mp_eid, covered_ids):
            continue
        mp_area = mp.get("area_id")
        friendly = mp.get("name") or mp.get("attributes", {}).get("friendly_name", mp_eid)
        area_name = _area_name(areas, mp_area)

        # Find lights in the same area for the scene
        same_area_lights = [
            e["entity_id"] for e in entities
            if _get_entity_domain(e.get("entity_id", "")) == "light"
            and e.get("area_id") == mp_area
            and mp_area is not None
        ]

        if same_area_lights:
            involved = [mp_eid] + same_area_lights
            title = f"Media lighting scene: {area_name}"
            suggestions.append({
                "title": title,
                "description": (
                    f"Dim lights in {area_name} when {friendly} starts playing, "
                    "and restore them when playback stops."
                ),
                "entity_ids": involved,
                "area_id": mp_area,
                "priority": "low",
                "category": "media_lighting",
                "suggested_config": _build_suggestion_config(
                    alias=title,
                    description=f"Adjust lighting in {area_name} based on media playback.",
                    triggers=[
                        {
                            "trigger": "state",
                            "entity_id": mp_eid,
                            "to": "playing",
                        },
                    ],
                    actions=[
                        {
                            "action": "light.turn_on",
                            "target": {"entity_id": same_area_lights},
                            "data": {"brightness_pct": 20},
                        },
                        {
                            "wait_for_trigger": [
                                {
                                    "trigger": "state",
                                    "entity_id": mp_eid,
                                    "from": "playing",
                                },
                            ],
                        },
                        {
                            "action": "light.turn_on",
                            "target": {"entity_id": same_area_lights},
                            "data": {"brightness_pct": 100},
                        },
                    ],
                    mode="restart",
                ),
            })
        else:
            # No lights in the same area; still suggest a simple notification
            title = f"Media playback notification: {friendly}"
            suggestions.append({
                "title": title,
                "description": f"Notify when {friendly} starts or stops playback.",
                "entity_ids": [mp_eid],
                "area_id": mp_area,
                "priority": "low",
                "category": "media_notification",
                "suggested_config": _build_suggestion_config(
                    alias=title,
                    description=f"Log when {friendly} playback state changes.",
                    triggers=[
                        {
                            "trigger": "state",
                            "entity_id": mp_eid,
                            "to": "playing",
                        },
                    ],
                    actions=[
                        {
                            "action": "notify.persistent_notification",
                            "data": {
                                "title": "Media Playing",
                                "message": f"{friendly} started playing.",
                            },
                        },
                    ],
                ),
            })

    # Sort: high > medium > low
    priority_order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: priority_order.get(s["priority"], 9))

    return suggestions


def detect_conflicts(automations: list[dict]) -> list[dict]:
    """Detect potentially conflicting automations.

    Returns a list of conflict dicts, each containing:
        - type: str  ("same_trigger", "opposing_actions", "overlapping_time")
        - description: str
        - automation_ids: list[str]
        - severity: "warning" | "error"
    """
    conflicts: list[dict] = []

    # Build per-automation extracted data for comparison
    auto_data: list[dict] = []
    for auto in automations:
        auto_id = auto.get("id") or auto.get("alias") or "unknown"
        alias = auto.get("alias", auto_id)
        triggers = auto.get("triggers", auto.get("trigger", []))
        if isinstance(triggers, dict):
            triggers = [triggers]
        actions = auto.get("actions", auto.get("action", []))
        if isinstance(actions, dict):
            actions = [actions]

        trigger_entity_ids = set()
        for t in triggers:
            if isinstance(t, dict):
                te = t.get("entity_id")
                if isinstance(te, str):
                    trigger_entity_ids.add(te)
                elif isinstance(te, list):
                    trigger_entity_ids.update(te)

        action_targets: list[tuple[str, str]] = []  # (entity_id, service/action)
        for a in actions:
            if isinstance(a, dict):
                service = a.get("action") or a.get("service") or ""
                target_eid = None
                target_block = a.get("target", {})
                if isinstance(target_block, dict):
                    target_eid = target_block.get("entity_id")
                if target_eid is None:
                    data_block = a.get("data", a.get("service_data", {}))
                    if isinstance(data_block, dict):
                        target_eid = data_block.get("entity_id")
                if target_eid is None:
                    target_eid = a.get("entity_id")
                if isinstance(target_eid, str):
                    action_targets.append((target_eid, service))
                elif isinstance(target_eid, list):
                    for te in target_eid:
                        if isinstance(te, str):
                            action_targets.append((te, service))

        # Extract time triggers
        time_triggers: list[str] = []
        for t in triggers:
            if isinstance(t, dict) and t.get("trigger") == "time":
                at = t.get("at")
                if isinstance(at, str):
                    time_triggers.append(at)

        auto_data.append({
            "id": auto_id,
            "alias": alias,
            "trigger_entity_ids": trigger_entity_ids,
            "action_targets": action_targets,
            "time_triggers": time_triggers,
        })

    # ------------------------------------------------------------------
    # Check 1: Multiple automations triggered by the same entity state
    # ------------------------------------------------------------------
    for i in range(len(auto_data)):
        for j in range(i + 1, len(auto_data)):
            a = auto_data[i]
            b = auto_data[j]
            common_triggers = a["trigger_entity_ids"] & b["trigger_entity_ids"]
            if common_triggers:
                conflicts.append({
                    "type": "same_trigger",
                    "description": (
                        f"Automations '{a['alias']}' and '{b['alias']}' are both "
                        f"triggered by the same entity: {', '.join(sorted(common_triggers))}. "
                        "They may interfere with each other."
                    ),
                    "automation_ids": [a["id"], b["id"]],
                    "severity": "warning",
                })

    # ------------------------------------------------------------------
    # Check 2: Opposing actions on the same entity (turn_on vs turn_off)
    # ------------------------------------------------------------------
    _OPPOSING_PAIRS = {
        ("turn_on", "turn_off"),
        ("turn_off", "turn_on"),
        ("lock", "unlock"),
        ("unlock", "lock"),
        ("open", "close"),
        ("close", "open"),
    }

    def _service_verb(service: str) -> str:
        """Extract the verb from a service call like 'light.turn_on' -> 'turn_on'."""
        return service.split(".")[-1] if "." in service else service

    for i in range(len(auto_data)):
        for j in range(i + 1, len(auto_data)):
            a = auto_data[i]
            b = auto_data[j]
            for a_eid, a_svc in a["action_targets"]:
                for b_eid, b_svc in b["action_targets"]:
                    if a_eid == b_eid:
                        verb_a = _service_verb(a_svc)
                        verb_b = _service_verb(b_svc)
                        if (verb_a, verb_b) in _OPPOSING_PAIRS:
                            conflicts.append({
                                "type": "opposing_actions",
                                "description": (
                                    f"Automations '{a['alias']}' and '{b['alias']}' perform "
                                    f"opposing actions ({a_svc} vs {b_svc}) on entity {a_eid}. "
                                    "This may cause flickering or race conditions."
                                ),
                                "automation_ids": [a["id"], b["id"]],
                                "severity": "error",
                            })

    # ------------------------------------------------------------------
    # Check 3: Time-based automations with overlapping windows
    # ------------------------------------------------------------------
    def _time_to_minutes(t: str) -> int | None:
        """Convert 'HH:MM' or 'HH:MM:SS' to minutes since midnight."""
        parts = t.split(":")
        if len(parts) >= 2:
            try:
                return int(parts[0]) * 60 + int(parts[1])
            except (ValueError, IndexError):
                return None
        return None

    for i in range(len(auto_data)):
        for j in range(i + 1, len(auto_data)):
            a = auto_data[i]
            b = auto_data[j]
            if not a["time_triggers"] or not b["time_triggers"]:
                continue
            for t_a in a["time_triggers"]:
                for t_b in b["time_triggers"]:
                    m_a = _time_to_minutes(t_a)
                    m_b = _time_to_minutes(t_b)
                    if m_a is not None and m_b is not None:
                        diff = abs(m_a - m_b)
                        if diff <= 5:
                            # Check if they target overlapping entities
                            a_targets = {eid for eid, _ in a["action_targets"]}
                            b_targets = {eid for eid, _ in b["action_targets"]}
                            common = a_targets & b_targets
                            if common:
                                conflicts.append({
                                    "type": "overlapping_time",
                                    "description": (
                                        f"Automations '{a['alias']}' and '{b['alias']}' fire "
                                        f"within 5 minutes of each other ({t_a} vs {t_b}) and "
                                        f"both target: {', '.join(sorted(common))}."
                                    ),
                                    "automation_ids": [a["id"], b["id"]],
                                    "severity": "warning",
                                })

    return conflicts


def suggest_dashboard_layout(
    entities: list[dict],
    areas: list[dict],
    target_area_id: str | None = None,
) -> dict:
    """Suggest a Lovelace dashboard layout based on entities and areas.

    Returns a Lovelace-compatible config dict with views organized by area,
    using appropriate card types for each entity domain.
    """
    # Domain -> preferred card type mapping
    _CARD_MAP: dict[str, str] = {
        "light": "light",
        "climate": "thermostat",
        "sensor": "sensor",
        "binary_sensor": "entity",
        "camera": "picture-entity",
        "media_player": "media-control",
        "switch": "entities",
        "fan": "entities",
        "cover": "entities",
        "lock": "entities",
        "vacuum": "entities",
        "weather": "weather-forecast",
        "person": "entity",
        "automation": "entities",
        "scene": "entities",
        "script": "entities",
    }

    # Filter areas if target set
    working_areas = areas
    if target_area_id:
        working_areas = [a for a in areas if a.get("area_id") == target_area_id]

    views: list[dict] = []

    for area in working_areas:
        a_id = area.get("area_id", "")
        a_name = area.get("name", a_id)
        area_ents = _get_entities_in_area(entities, a_id)

        if not area_ents:
            continue

        # Group entities by domain
        by_domain: dict[str, list[str]] = {}
        for e in area_ents:
            eid = e.get("entity_id", "")
            domain = _get_entity_domain(eid)
            if domain:
                by_domain.setdefault(domain, []).append(eid)

        cards: list[dict] = []

        for domain, eids in sorted(by_domain.items()):
            card_type = _CARD_MAP.get(domain, "entities")

            if card_type == "light":
                # Individual light cards for each light
                for eid in eids:
                    cards.append({
                        "type": "light",
                        "entity": eid,
                    })

            elif card_type == "thermostat":
                for eid in eids:
                    cards.append({
                        "type": "thermostat",
                        "entity": eid,
                    })

            elif card_type == "sensor":
                # Group sensors into a single glance card
                cards.append({
                    "type": "glance",
                    "title": f"{a_name} Sensors",
                    "entities": eids,
                })

            elif card_type == "picture-entity":
                for eid in eids:
                    cards.append({
                        "type": "picture-entity",
                        "entity": eid,
                        "camera_image": eid,
                    })

            elif card_type == "media-control":
                for eid in eids:
                    cards.append({
                        "type": "media-control",
                        "entity": eid,
                    })

            elif card_type == "weather-forecast":
                for eid in eids:
                    cards.append({
                        "type": "weather-forecast",
                        "entity": eid,
                    })

            elif card_type == "entity":
                for eid in eids:
                    cards.append({
                        "type": "entity",
                        "entity": eid,
                    })

            else:
                # Generic entities card (switches, fans, covers, locks, etc.)
                cards.append({
                    "type": "entities",
                    "title": f"{a_name} {domain.replace('_', ' ').title()}",
                    "entities": eids,
                })

        views.append({
            "title": a_name,
            "path": a_id.replace(" ", "_"),
            "cards": cards,
        })

    # Handle entities with no area assignment
    unassigned = [
        e for e in entities
        if not e.get("area_id")
    ]
    if unassigned and not target_area_id:
        by_domain: dict[str, list[str]] = {}
        for e in unassigned:
            eid = e.get("entity_id", "")
            domain = _get_entity_domain(eid)
            if domain:
                by_domain.setdefault(domain, []).append(eid)

        cards = []
        for domain, eids in sorted(by_domain.items()):
            cards.append({
                "type": "entities",
                "title": domain.replace("_", " ").title(),
                "entities": eids,
            })
        if cards:
            views.append({
                "title": "Other",
                "path": "other",
                "cards": cards,
            })

    return {
        "title": "Home",
        "views": views,
    }


# ---------------------------------------------------------------------------
# Internal area-name helper
# ---------------------------------------------------------------------------

def _area_name(areas: list[dict], area_id: str | None) -> str:
    """Look up a human-readable area name, falling back to area_id or 'Unknown area'."""
    if not area_id:
        return "Unknown area"
    for a in areas:
        if a.get("area_id") == area_id:
            return a.get("name", area_id)
    return area_id
