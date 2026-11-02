# HTML/CSS template renderer methods

from datetime import datetime, timezone

from apiflask import APIBlueprint, Schema, fields
from flask import render_template, request, jsonify, current_app

from thermometry import config, store
from thermometry.flaskr.db import get_db

bp = APIBlueprint("dashboard", __name__, url_prefix="/dashboard")


@bp.route("/")
@bp.doc(summary="Get HTML page of the dashboard with javascript charts")
def dashboard():
    fridge = request.args.get('fridge', type=str)
    data_type = request.args.get('type', type=str)
    showPressures = data_type == "pressures"

    if fridge is None:
        # Render all the fridges at once
        return render_template("combined_dashboard.html", fridges=config.SIDEBAR_FRIDGES, menu="all", title="Fridge Status", url=config.EXTERNAL_WEBSITE_URL)
    else:
        # Render just one fridge
        return render_template("dashboard.html", fridges=config.SIDEBAR_FRIDGES, menu=fridge, fridge=fridge, title=f"{fridge.title()} Fridge Status", url=config.EXTERNAL_WEBSITE_URL, showPressures=showPressures)


#: How long the alarm evaluator may go silent before the website stops believing the alert
#: states it wrote. Two missed 30 s ticks plus slack.
HEARTBEAT_STALE_S = getattr(config, "ALERT_HEARTBEAT_STALE_S", 150)

#: The alert types that gate the experimental interlock. For these, "we do not know" is
#: reported as ALARM rather than as silence.
INTERLOCK_ALERTS = set(getattr(config, "INTERLOCK_ALERTS", ["Critical"]))

#: Fridges that must always appear in the interlock JSON, even before the evaluator has ever
#: run. Without this, an unconfigured fridge returns no entry at all, which a consumer reads
#: as "nothing wrong".
INTERLOCK_FRIDGES = getattr(config, "SIDEBAR_FRIDGES", [])


class DisabledSchema(Schema):
    """Schema for requesting an alert to be disabled or not"""
    name = fields.String(required=False)
    value = fields.String(required=True)
    checked = fields.Boolean(required=False)


class AcknowledgeSchema(Schema):
    """Schema for acknowledging a latched alarm"""
    value = fields.String(required=True)  # "AlertType.fridge"


def _split_target(value: str):
    """Split an "AlertType.fridge" form value."""
    splits = value.split(".")
    if len(splits) != 2:
        return None, None
    return splits[0], splits[1]


@bp.post("/alerts/action")
@bp.input(DisabledSchema)
@bp.doc(summary="Process an alert status change to be manually disabled or not. This is submitted by the HTML form")
def action_alert(json_data):
    # Apply the action of enabling or disabling the alert
    alert_type, fridge = _split_target(json_data["value"])
    if alert_type is None:
        return "Unknown action type", 500

    state = "MANUALLY_DISABLED" if json_data["checked"] else "DISABLED"

    # A single UPDATE against the alert's own row. This used to be a read-modify-write of a
    # shared JSON file from three Waitress threads, where simultaneous clicks lost each other
    # and the alarm process truncated the file out from under them.
    store.request_alert_action(get_db(), alert_type, fridge, state)
    return '', 204


@bp.post("/alerts/acknowledge")
@bp.input(AcknowledgeSchema)
@bp.doc(summary="Acknowledge a latched alarm, releasing the latch")
def acknowledge_alert(json_data):
    """Clear a latched alarm. Critical latches until a person confirms the fridge is safe."""
    alert_type, fridge = _split_target(json_data["value"])
    if alert_type is None:
        return "Unknown action type", 500

    store.request_alert_action(get_db(), alert_type, fridge, "ACKNOWLEDGE")
    return '', 204


def _evaluator_age():
    """Seconds since the alarm evaluator last reported in, or None if it never has."""
    beat = store.last_beat(get_db(), "watchtower")
    if beat is None:
        return None
    return (datetime.now(timezone.utc) - beat).total_seconds()


def _unavailable_rows(alert_type, reason: str) -> list:
    """The answer to give when the database cannot be read at all.

    Charizard only understands this JSON, and we agreed not to change its side. Returning a 500
    would leave "is this fridge safe?" to whatever its error handling happens to do; returning an
    explicit ALARM it already knows how to act on does not.
    """
    rows = []
    for type_name in sorted(INTERLOCK_ALERTS):
        if alert_type not in (None, "all", type_name):
            continue
        for fridge in INTERLOCK_FRIDGES:
            rows.append({
                "title": "Fridge in critical condition",
                "type": type_name,
                "fridge": fridge,
                "state": "ALARM",
                "description": f"The alert database could not be read ({reason}). Reported as "
                               f"critical so that experiments fail safe.",
                "now": "alert database unavailable",
                "condition": "",
                "updated": None,
                "data_age_s": None,
            })
    return rows


def _alert_rows(alert_type=None):
    """Build the alert list the website and its consumers see, applying fail-safe overrides.

    The alarm evaluator writes what it believes; this decides whether that belief is still
    trustworthy. If the evaluator has gone quiet, an interlock alert is reported as ALARM
    rather than frozen at its last value -- a dead evaluator should ground devices, not leave
    experiments running against a stale "all clear".
    """
    try:
        records = store.fetch_alert_states_for_display(get_db(), alert_type)
        evaluator_age = _evaluator_age()
    except Exception as e:
        # Missing tables (upgrade-db not run yet) or the database being down both land here
        current_app.logger.error("Could not read alert state: %r", e)
        reason = "run `flask --app thermometry.flaskr upgrade-db`" \
            if "does not exist" in str(e) else type(e).__name__
        return _unavailable_rows(alert_type, reason), None, True

    evaluator_stale = evaluator_age is None or evaluator_age > HEARTBEAT_STALE_S

    alerts = []
    seen_interlock = set()
    for record in records:
        display = dict(record["detail"].get("display") or {})
        display.setdefault("type", record["type"])
        display.setdefault("fridge", record["fridge"])
        display.setdefault("title", record["type"])
        display.setdefault("description", "")
        display.setdefault("now", "?")
        display.setdefault("condition", "")
        display["state"] = record["state"]

        updated = record["updated"]
        display["updated"] = updated.astimezone().isoformat(sep=" ", timespec="seconds") if updated else None
        display["data_age_s"] = round(evaluator_age) if evaluator_age is not None else None

        is_interlock = record["type"] in INTERLOCK_ALERTS
        if is_interlock:
            seen_interlock.add((record["type"], record["fridge"]))

        if evaluator_stale and is_interlock and display["state"] != "MANUALLY_DISABLED":
            display["state"] = "ALARM"
            display["now"] = "alert evaluator is not responding"
            display["description"] = (
                "The alarm evaluator has stopped reporting, so the state of this fridge is "
                "unknown. Reported as critical so that experiments fail safe. Check that the "
                "thermometry service is running.")
        elif display["state"] == "UNKNOWN" and is_interlock:
            # The evaluator is alive but cannot see this fridge
            display["state"] = "ALARM"

        alerts.append(display)

    # Never let a missing row read as "safe" for an interlock alert
    for type_name in sorted(INTERLOCK_ALERTS):
        if alert_type not in (None, "all", type_name):
            continue
        for fridge in INTERLOCK_FRIDGES:
            if (type_name, fridge) in seen_interlock:
                continue
            alerts.append({
                "title": "Fridge in critical condition",
                "type": type_name,
                "fridge": fridge,
                "state": "ALARM",
                "description": (f"No {type_name} alert is configured or has ever run for "
                                f"{fridge}. Reported as critical because an absent alert is "
                                f"indistinguishable from a safe one."),
                "now": "alert not configured",
                "condition": "",
                "updated": None,
                "data_age_s": None,
            })

    return alerts, evaluator_age, evaluator_stale


@bp.route("/alerts")
@bp.doc(summary="Get a HTML page of all the alerts")
def view_alerts():
    # Display the alert view
    alerts, evaluator_age, evaluator_stale = _alert_rows()
    last_updated = datetime.now().astimezone().isoformat(sep=" ", timespec="seconds")
    return render_template("alerts.html", fridges=config.SIDEBAR_FRIDGES, menu="alerts",
                           alerts=alerts, last_updated=last_updated,
                           evaluator_age=evaluator_age, evaluator_stale=evaluator_stale)


@bp.get("/alerts/<string:alert_type>.json")
@bp.doc(summary="Get JSON status for a specific type of alert. Use 'all' to get all alerts")
def view_alert(alert_type: str):
    """Serve alert state.

    Charizard polls this for `Critical` and grounds devices when it sees state == "ALARM", so
    the response shape is fixed. What changed is where it comes from -- the database rather
    than a JSON file written by another process -- and that staleness is now evaluated on every
    request instead of being invisible to the caller.
    """
    alerts, evaluator_age, evaluator_stale = _alert_rows(alert_type)

    response = jsonify({
        "alerts": alerts,
        "last_updated": datetime.now().astimezone().isoformat(sep=" ", timespec="seconds"),
        "evaluator_age_s": round(evaluator_age) if evaluator_age is not None else None,
        "evaluator_stale": evaluator_stale,
    })
    # A cached answer about whether a fridge is safe is worse than no answer
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.route("/gauges")
@bp.doc(summary="Get HTML page of fridge gauges")
def gauges():
    # Work out the gauges to show for each fridge
    return render_template("gauges.html", fridges=config.SIDEBAR_FRIDGES, menu="gauges", title="Gauges", url=config.EXTERNAL_WEBSITE_URL)
