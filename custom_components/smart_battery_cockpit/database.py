"""SQLite lifecycle database & telemetry engine for Smart Battery Cockpit."""

from __future__ import annotations

import datetime
import logging
import sqlite3
from typing import Any

from .const import DEFAULT_BASELINE_GLITCH_THRESHOLD, RECHARGEABLE_MODEL_KEYWORDS

_LOGGER = logging.getLogger(__name__)


def parse_float(val: Any) -> float | None:
    """Safely parse a numeric state into float."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def is_rechargeable_device(
    entity_id: str,
    friendly_name: str,
    manufacturer: str,
    model: str,
    platform: str,
) -> bool:
    """Heuristically identify smartphones, tablets, laptops, and robot vacuums."""
    if platform in ("mobile_app", "hass_agent", "roborock", "dreame_vacuum"):
        return True
    haystack = f"{entity_id} {friendly_name} {manufacturer} {model}".lower()
    return any(kw in haystack for kw in RECHARGEABLE_MODEL_KEYWORDS)


def infer_battery_type(
    entity_id: str,
    model: str,
    manufacturer: str,
    explicit_type: str | None = None,
) -> str:
    """Infer common smart-home battery type from device metadata."""
    if explicit_type and explicit_type not in ("-", "unknown", "unavailable", ""):
        return explicit_type
    eid = entity_id.lower()
    mod = (model or "").lower()
    mfg = (manufacturer or "").lower()

    if "thermostat" in mod or "trv" in mod or "srts-a01" in mod or "termostat" in eid:
        return "2× AA (1.5V)"
    if "fp300" in mod or "fp300" in eid:
        return "2× CR2450"
    if "curtain" in mod or "roller shade" in mod or "blind" in mod:
        return "Li-Ion Akku (USB-C)"
    if "smart lock" in mod or "nuki" in mfg:
        return "Akku / 4× AA"
    if "soil" in mod or "meter" in mod or "hobeian" in mfg:
        return "2× AAA (1.5V)"
    if "shelly h&t" in mod or "shellyht" in mod:
        return "4× AA (1.5V)"
    if "sonoff" in mfg or "snzb" in mod:
        return "1× CR2450"
    if "fingerbot" in mod or "wohand" in mod or "bot" in mod:
        return "1× CR2 (3V)"
    if "esp32" in mod or "espressif" in mfg:
        return "1× 18650 Li-Ion"
    if any(k in mfg for k in ("aqara", "xiaomi", "lumi", "shelly", "tuya", "ikea", "hombli", "meross")):
        return "1× CR2032"
    return "Battery"


class BatteryDatabase:
    """Thread-safe SQLite wrapper (intended to be called via hass.async_add_executor_job)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Create tables if they do not exist."""
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    entity_id TEXT PRIMARY KEY,
                    friendly_name TEXT,
                    room TEXT,
                    manufacturer TEXT,
                    model TEXT,
                    battery_type TEXT,
                    voltage_entity_id TEXT,
                    last_level REAL,
                    last_voltage_mv REAL,
                    last_updated TEXT,
                    last_replaced_at TEXT,
                    previous_cycle_days INTEGER,
                    avg_cycle_days REAL,
                    swap_count INTEGER DEFAULT 0,
                    pending_swap_from REAL,
                    pending_swap_to REAL,
                    pending_swap_at TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS daily_roundtrip (
                    date TEXT,
                    entity_id TEXT,
                    battery_pct REAL,
                    voltage_mv REAL,
                    delta_24h REAL,
                    days_since_swap INTEGER,
                    PRIMARY KEY (date, entity_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS swap_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT,
                    friendly_name TEXT,
                    battery_type TEXT,
                    swapped_at TEXT,
                    old_level_pct REAL,
                    new_level_pct REAL,
                    cycle_days INTEGER,
                    confirmed_by TEXT,
                    notes TEXT
                )
            """)
            conn.commit()

    def sync_devices_and_roundtrip(
        self,
        snapshots: list[dict[str, Any]],
        jump_threshold: float = 25.0,
        detect_jumps: bool = True,
    ) -> list[dict[str, Any]]:
        """Sync device metadata, write daily roundtrip snapshot, and return newly detected jumps."""
        today_str = datetime.date.today().isoformat()
        yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        now_iso = datetime.datetime.now().isoformat(timespec="seconds")
        detected_jumps: list[dict[str, Any]] = []

        active_ids = {s["entity_id"] for s in snapshots}

        with self._connect() as conn:
            cur = conn.cursor()
            # Remove devices that were excluded or deleted in HA
            if active_ids:
                cur.execute("SELECT entity_id FROM devices")
                existing_ids = {r["entity_id"] for r in cur.fetchall()}
                for stale_id in existing_ids - active_ids:
                    cur.execute("DELETE FROM devices WHERE entity_id = ?", (stale_id,))

            for s in snapshots:
                eid = s["entity_id"]
                pct = s.get("battery_pct")
                volt_mv = s.get("voltage_mv")

                cur.execute(
                    "SELECT last_level, last_replaced_at, pending_swap_to FROM devices WHERE entity_id = ?",
                    (eid,),
                )
                row = cur.fetchone()

                if row is None:
                    cur.execute(
                        """
                        INSERT INTO devices (
                            entity_id, friendly_name, room, manufacturer, model,
                            battery_type, voltage_entity_id, last_level, last_voltage_mv, last_updated
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            eid,
                            s["friendly_name"],
                            s["room"],
                            s["manufacturer"],
                            s["model"],
                            s["battery_type"],
                            s["voltage_entity_id"],
                            pct,
                            volt_mv,
                            now_iso,
                        ),
                    )
                    last_replaced_at = None
                else:
                    prev_level = row["last_level"]
                    last_replaced_at = row["last_replaced_at"]
                    pending_to = row["pending_swap_to"]

                    if (
                        detect_jumps
                        and pct is not None
                        and prev_level is not None
                        and prev_level < DEFAULT_BASELINE_GLITCH_THRESHOLD
                        and (pct - prev_level) >= jump_threshold
                        and pct >= 80.0
                        and pending_to is None
                    ):
                        cur.execute(
                            """
                            UPDATE devices
                            SET pending_swap_from = ?, pending_swap_to = ?, pending_swap_at = ?
                            WHERE entity_id = ?
                            """,
                            (prev_level, pct, now_iso, eid),
                        )
                        detected_jumps.append(
                            {
                                "entity_id": eid,
                                "friendly_name": s["friendly_name"],
                                "battery_type": s["battery_type"],
                                "old_pct": prev_level,
                                "new_pct": pct,
                            }
                        )

                    cur.execute(
                        """
                        UPDATE devices
                        SET friendly_name = ?, room = ?, manufacturer = ?, model = ?,
                            battery_type = ?, voltage_entity_id = ?,
                            last_level = COALESCE(?, last_level),
                            last_voltage_mv = COALESCE(?, last_voltage_mv),
                            last_updated = ?
                        WHERE entity_id = ?
                        """,
                        (
                            s["friendly_name"],
                            s["room"],
                            s["manufacturer"],
                            s["model"],
                            s["battery_type"],
                            s["voltage_entity_id"],
                            pct,
                            volt_mv,
                            now_iso,
                            eid,
                        ),
                    )

                if pct is not None:
                    cur.execute(
                        "SELECT battery_pct FROM daily_roundtrip WHERE entity_id = ? AND date <= ? ORDER BY date DESC LIMIT 1",
                        (eid, yesterday_str),
                    )
                    y_row = cur.fetchone()
                    delta_24h = (
                        round(pct - y_row["battery_pct"], 1)
                        if (y_row and y_row["battery_pct"] is not None)
                        else 0.0
                    )

                    days_since_swap = None
                    if last_replaced_at:
                        try:
                            dt_rep = datetime.date.fromisoformat(last_replaced_at[:10])
                            days_since_swap = (datetime.date.today() - dt_rep).days
                        except ValueError:
                            pass

                    cur.execute(
                        """
                        INSERT INTO daily_roundtrip (date, entity_id, battery_pct, voltage_mv, delta_24h, days_since_swap)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(date, entity_id) DO UPDATE SET
                            battery_pct = excluded.battery_pct,
                            voltage_mv = COALESCE(excluded.voltage_mv, daily_roundtrip.voltage_mv),
                            delta_24h = excluded.delta_24h,
                            days_since_swap = excluded.days_since_swap
                        """,
                        (today_str, eid, pct, volt_mv, delta_24h, days_since_swap),
                    )

            conn.commit()
        return detected_jumps

    def check_and_flag_jump(
        self, entity_id: str, old_val: float, new_val: float
    ) -> dict[str, Any] | None:
        """Apply SQLite Baseline Glitch-Filter; flag jump and return device info if genuine."""
        now_iso = datetime.datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT friendly_name, battery_type, last_level, pending_swap_to FROM devices WHERE entity_id = ?",
                (entity_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            fn = row["friendly_name"] or entity_id
            btype = row["battery_type"] or "Battery"
            db_last_level = row["last_level"]

            # Check last 3 daily roundtrip snapshots for baseline glitch filtering
            cur.execute(
                "SELECT battery_pct FROM daily_roundtrip WHERE entity_id = ? ORDER BY date DESC LIMIT 3",
                (entity_id,),
            )
            recent_days = [r["battery_pct"] for r in cur.fetchall() if r["battery_pct"] is not None]
            recent_baseline = max(recent_days) if recent_days else db_last_level

            if (
                db_last_level is not None and db_last_level >= DEFAULT_BASELINE_GLITCH_THRESHOLD
            ) or (
                recent_baseline is not None and recent_baseline >= DEFAULT_BASELINE_GLITCH_THRESHOLD
            ):
                _LOGGER.debug(
                    "Glitch filtered for %s (%s): %s%% -> %s%%, SQLite baseline=%s%%",
                    entity_id,
                    fn,
                    old_val,
                    new_val,
                    recent_baseline,
                )
                return None

            cur.execute(
                """
                UPDATE devices
                SET pending_swap_from = ?, pending_swap_to = ?, pending_swap_at = ?, last_level = ?
                WHERE entity_id = ?
                """,
                (old_val, new_val, now_iso, new_val, entity_id),
            )
            conn.commit()
            return {
                "entity_id": entity_id,
                "friendly_name": fn,
                "battery_type": btype,
                "old_pct": old_val,
                "new_pct": new_val,
            }

    def confirm_swap(
        self,
        entity_id: str,
        old_val: float | None = None,
        new_val: float | None = None,
        notes: str = "Confirmed battery replacement",
    ) -> bool:
        """Record a confirmed battery swap in swap_history and reset cycle."""
        now_iso = datetime.datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT friendly_name, battery_type, last_level, last_replaced_at,
                       pending_swap_from, pending_swap_to, swap_count, avg_cycle_days
                FROM devices WHERE entity_id = ?
                """,
                (entity_id,),
            )
            row = cur.fetchone()
            if not row:
                return False

            old_pct = (
                old_val
                if old_val is not None
                else (row["pending_swap_from"] if row["pending_swap_from"] is not None else row["last_level"])
            )
            new_pct = (
                new_val
                if new_val is not None
                else (row["pending_swap_to"] if row["pending_swap_to"] is not None else 100.0)
            )

            cycle_days = None
            last_rep = row["last_replaced_at"]
            if last_rep and last_rep[:10] != now_iso[:10]:
                try:
                    d1 = datetime.date.fromisoformat(last_rep[:10])
                    d2 = datetime.date.fromisoformat(now_iso[:10])
                    if (d2 - d1).days > 0:
                        cycle_days = (d2 - d1).days
                except ValueError:
                    pass

            new_swap_count = (row["swap_count"] or 0) + 1
            avg_cycle = row["avg_cycle_days"]
            if cycle_days is not None:
                new_avg = round(
                    ((avg_cycle or cycle_days) * (new_swap_count - 1) + cycle_days) / new_swap_count,
                    1,
                )
            else:
                new_avg = avg_cycle

            cur.execute(
                """
                INSERT INTO swap_history (
                    entity_id, friendly_name, battery_type, swapped_at,
                    old_level_pct, new_level_pct, cycle_days, confirmed_by, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'user', ?)
                """,
                (
                    entity_id,
                    row["friendly_name"],
                    row["battery_type"],
                    now_iso,
                    old_pct,
                    new_pct,
                    cycle_days,
                    notes,
                ),
            )
            cur.execute(
                """
                UPDATE devices
                SET last_replaced_at = ?,
                    last_level = ?,
                    previous_cycle_days = COALESCE(?, previous_cycle_days),
                    avg_cycle_days = ?,
                    swap_count = ?,
                    pending_swap_from = NULL,
                    pending_swap_to = NULL,
                    pending_swap_at = NULL
                WHERE entity_id = ?
                """,
                (now_iso, new_pct, cycle_days, new_avg, new_swap_count, entity_id),
            )
            cur.execute(
                """
                UPDATE daily_roundtrip
                SET days_since_swap = 0, battery_pct = ?
                WHERE date = ? AND entity_id = ?
                """,
                (new_pct, now_iso[:10], entity_id),
            )
            conn.commit()
            return True

    def dismiss_swap(self, entity_id: str) -> bool:
        """Clear a pending swap confirmation without logging a replacement."""
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE devices
                SET pending_swap_from = NULL, pending_swap_to = NULL, pending_swap_at = NULL
                WHERE entity_id = ?
                """,
                (entity_id,),
            )
            conn.commit()
            return True

    def get_dashboard_data(self) -> dict[str, Any]:
        """Return full JSON-serializable payload for WebSocket API and status sensor."""
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM devices ORDER BY COALESCE(last_level, 999) ASC, friendly_name ASC"
            )
            devices = [dict(r) for r in cur.fetchall()]

            for d in devices:
                eid = d["entity_id"]
                cur.execute(
                    """
                    SELECT date, battery_pct, voltage_mv, delta_24h, days_since_swap
                    FROM daily_roundtrip
                    WHERE entity_id = ?
                    ORDER BY date DESC
                    LIMIT 90
                    """,
                    (eid,),
                )
                history = [dict(r) for r in cur.fetchall()][::-1]
                d["history"] = history
                d["delta_24h"] = history[-1]["delta_24h"] if history else 0.0

                rep_date = d["last_replaced_at"][:10] if d.get("last_replaced_at") else None
                valid_pts = [
                    h
                    for h in history
                    if h.get("battery_pct") is not None
                    and (not rep_date or h["date"] >= rep_date)
                ]
                recent_pts = valid_pts[-8:]
                avg_7d = 0.0
                if len(recent_pts) >= 2:
                    try:
                        d_start = datetime.date.fromisoformat(recent_pts[0]["date"])
                        d_end = datetime.date.fromisoformat(recent_pts[-1]["date"])
                        span = (d_end - d_start).days
                        if span > 0:
                            avg_7d = round(
                                (recent_pts[-1]["battery_pct"] - recent_pts[0]["battery_pct"]) / span,
                                2,
                            )
                    except ValueError:
                        avg_7d = 0.0
                d["avg_7d_drain"] = avg_7d

                cur_pct = d.get("last_level")
                if cur_pct is not None and avg_7d <= -0.1:
                    d["est_days_left"] = min(999, max(0, int(round(cur_pct / abs(avg_7d)))))
                else:
                    d["est_days_left"] = None

                if rep_date:
                    try:
                        d["days_since_swap"] = (
                            datetime.date.today() - datetime.date.fromisoformat(rep_date)
                        ).days
                    except ValueError:
                        d["days_since_swap"] = None
                else:
                    d["days_since_swap"] = None

            cur.execute("SELECT * FROM swap_history ORDER BY swapped_at DESC, id DESC LIMIT 100")
            swaps = [dict(r) for r in cur.fetchall()]

        pending = [d for d in devices if d.get("pending_swap_to") is not None]
        low_devices = [
            d for d in devices if d.get("last_level") is not None and d["last_level"] <= 20.0
        ]

        anomalies = []
        for d in devices:
            avg_7d = d.get("avg_7d_drain", 0.0)
            d24 = d.get("delta_24h", 0.0)
            hist = d.get("history", [])
            prev_d24 = (
                hist[-2]["delta_24h"]
                if len(hist) >= 2 and hist[-2].get("delta_24h") is not None
                else 0.0
            )
            if avg_7d <= -3.0 or d24 <= -10.0 or (d24 <= -5.0 and prev_d24 < 0):
                anomalies.append(d)

        type_counts: dict[str, dict[str, int]] = {}
        for d in devices:
            bt = d["battery_type"] or "Battery"
            if bt not in type_counts:
                type_counts[bt] = {"total": 0, "low": 0}
            type_counts[bt]["total"] += 1
            if d.get("last_level") is not None and d["last_level"] <= 20.0:
                type_counts[bt]["low"] += 1

        now_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        return {
            "generated_at": now_str,
            "total_devices": len(devices),
            "low_battery_count": len(low_devices),
            "pending_confirmations_count": len(pending),
            "anomaly_count": len(anomalies),
            "battery_type_summary": type_counts,
            "pending_confirmations": pending,
            "anomalies": anomalies,
            "devices": devices,
            "swap_history": swaps,
        }
