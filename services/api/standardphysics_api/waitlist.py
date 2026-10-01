"""Public beta signups and a private list of addresses for TestFlight invites."""

from __future__ import annotations

import csv
import hmac
import io
from datetime import UTC, datetime
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, Header, Response
from pydantic import BaseModel, EmailStr

from .accounts import normalize_email
from .db import Database
from .errors import ApiProblem
from .settings import Settings
from .team_alerts import send_team_alert


class WaitlistSignup(BaseModel):
    email: EmailStr
    role: Literal["student", "shop_owner"]


ROLE_WORDS = {"student": "A student", "shop_owner": "A shop owner"}
ALERT_TITLE = "New TestFlight waitlist signup"


def _alert_message(role: str, on_the_list: int) -> str:
    """Who joined and how many are waiting, never the address: an ntfy topic can be read by anyone who knows it,
    and the privacy page promises the address is used only for the invite."""
    people = "1 person is" if on_the_list == 1 else f"{on_the_list} people are"
    return f"{ROLE_WORDS[role]} joined the TestFlight waitlist. {people} on it now."


def _record(database: Database, email: str, role: str) -> int | None:
    """Saves the signup, and returns how many are on the list when this address is new, or None when it was
    already there and only its role changed."""
    with database.transaction() as connection:
        known = connection.execute("SELECT 1 FROM beta_waitlist WHERE email = ?", (email,)).fetchone()
        connection.execute(
            "INSERT INTO beta_waitlist (email, role, created_at) VALUES (?, ?, ?)"
            " ON CONFLICT(email) DO UPDATE SET role = excluded.role",
            (email, role, datetime.now(UTC).isoformat()),
        )
        if known is not None:
            return None
        return int(connection.execute("SELECT COUNT(*) FROM beta_waitlist").fetchone()[0])


def _csv_export(database: Database) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(("email", "role", "joined_at"))
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT email, role, created_at FROM beta_waitlist ORDER BY created_at, email"
        ).fetchall()
    writer.writerows((row["email"], row["role"], row["created_at"]) for row in rows)
    return output.getvalue()


def install_waitlist_routes(app: FastAPI, database: Database, settings: Settings) -> None:
    @app.post("/api/waitlist", status_code=202)
    def join_waitlist(body: WaitlistSignup, background: BackgroundTasks) -> Response:
        """A new address also tells the team, after the answer is sent, so a slow webhook never slows a signup."""
        on_the_list = _record(database, normalize_email(body.email), body.role)
        if on_the_list is not None:
            background.add_task(send_team_alert, settings, ALERT_TITLE, _alert_message(body.role, on_the_list))
        return Response(status_code=202)

    @app.get("/api/waitlist.csv", include_in_schema=False)
    def export_waitlist(authorization: str | None = Header(default=None)) -> Response:
        token = settings.waitlist_admin_token
        if not token:
            raise ApiProblem(404, "not found")
        if not authorization or not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise ApiProblem(401, "admin token required")
        return Response(
            content=_csv_export(database),
            media_type="text/csv",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'attachment; filename="standardphysics-waitlist.csv"',
            },
        )
