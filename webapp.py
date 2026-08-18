"""Browser-based admin panel for the Atlon Group bot.

Runs in the same process as the bot (see main.py) so that approving a
payment here can immediately notify the applicant on Telegram.

Built on Starlette + Jinja2. Every route except /login and /healthz is
behind a signed session cookie.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from functools import wraps

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.applications import Starlette
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    Response,
)
from starlette.routing import Route
from starlette.templating import Jinja2Templates

import config
import db
import texts

logger = logging.getLogger("atlon-bot.web")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

COOKIE_NAME = "atlon_session"
_signer = URLSafeTimedSerializer(config.SESSION_SECRET, salt="atlon-admin")

STATUS_LABEL = {
    db.PENDING: "Kutilmoqda",
    db.APPROVED: "Tasdiqlangan",
    db.REJECTED: "Rad etilgan",
}


# ── Auth ─────────────────────────────────────────────────────────

def _is_logged_in(request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        _signer.loads(token, max_age=config.SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def login_required(handler):
    """Redirect anonymous visitors to the login page."""

    @wraps(handler)
    async def wrapper(request):
        if not _is_logged_in(request):
            return RedirectResponse("/login", status_code=303)
        return await handler(request)

    return wrapper


def _render(request, template: str, **context) -> HTMLResponse:
    context.setdefault("cities", config.CITIES)
    context.setdefault("status_label", STATUS_LABEL)
    context.setdefault("path", request.url.path)
    if template != "login.html":
        # Badge in the sidebar showing how many receipts still need review.
        context.setdefault("pending_badge", db.count_registrations(db.PENDING))
    return templates.TemplateResponse(request, template, context)


async def login_page(request):
    if _is_logged_in(request):
        return RedirectResponse("/", status_code=303)
    return _render(request, "login.html", error=None)


async def login_submit(request):
    form = await request.form()
    password = (form.get("password") or "").strip()

    if not config.ADMIN_PASSWORD:
        return _render(
            request,
            "login.html",
            error="Panel sozlanmagan: ADMIN_PASSWORD o‘rnatilmagan.",
        )

    # Constant-time comparison so the password can't be guessed by timing.
    import hmac

    if not hmac.compare_digest(password, config.ADMIN_PASSWORD):
        return _render(request, "login.html", error="Parol noto‘g‘ri.")

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        _signer.dumps({"t": datetime.utcnow().isoformat()}),
        max_age=config.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


async def logout(request):
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


async def healthz(request):
    return Response("ok", media_type="text/plain")


# ── Dashboard ────────────────────────────────────────────────────

@login_required
async def dashboard(request):
    pending = db.pending_registrations()
    events = {e.id: e for e in db.all_events()}

    stats = {
        "users": db.count_users(),
        "volunteers": db.count_applications(),
        "pending": db.count_registrations(db.PENDING),
        "approved": db.count_registrations(db.APPROVED),
        "rejected": db.count_registrations(db.REJECTED),
    }

    # Per-region subscriber counts, biggest first.
    by_region = [
        {"name": c["name"], "count": len(db.user_ids_for_city(c["key"]))}
        for c in config.CITIES
    ]
    by_region.sort(key=lambda r: r["count"], reverse=True)
    top = max((r["count"] for r in by_region), default=0)

    return _render(
        request,
        "dashboard.html",
        stats=stats,
        pending=pending[:6],
        pending_total=len(pending),
        events=events,
        by_region=by_region,
        region_max=top,
    )


# ── Registrations queue ──────────────────────────────────────────

@login_required
async def registrations(request):
    status = request.query_params.get("status", db.PENDING)
    if status == "all":
        rows = db.all_registrations()
    else:
        rows = [r for r in db.all_registrations() if r.status == status]
    rows.reverse()  # newest first

    events = {e.id: e for e in db.all_events()}
    return _render(
        request,
        "registrations.html",
        rows=rows,
        events=events,
        status=status,
        counts={
            db.PENDING: db.count_registrations(db.PENDING),
            db.APPROVED: db.count_registrations(db.APPROVED),
            db.REJECTED: db.count_registrations(db.REJECTED),
        },
    )


async def _decide(request, approved: bool):
    reg_id = int(request.path_params["reg_id"])
    status = db.APPROVED if approved else db.REJECTED
    changed, reg = db.review_registration(reg_id, status, admin_id=0)

    if changed and reg is not None:
        bot = request.app.state.bot
        event = db.get_event(reg.event_id) if approved else None
        try:
            await bot.send_message(
                chat_id=reg.user_id,
                text=texts.decision_message(approved, event),
                parse_mode="HTML",
            )
        except Exception as exc:  # noqa: BLE001 — user may have blocked the bot
            logger.info("Could not notify applicant %s: %s", reg.user_id, exc)

    back = request.query_params.get("next") or "/registrations"
    return RedirectResponse(back, status_code=303)


@login_required
async def approve(request):
    return await _decide(request, True)


@login_required
async def reject(request):
    return await _decide(request, False)


@login_required
async def receipt_image(request):
    """Stream a receipt from Telegram without exposing the bot token.

    Handles both photos and uploaded files (images or PDFs).
    """
    reg_id = int(request.path_params["reg_id"])
    reg = db.get_registration(reg_id)
    if reg is None or not reg.receipt_file_id:
        return Response("Chek topilmadi", status_code=404)

    try:
        f = await request.app.state.bot.get_file(reg.receipt_file_id)
        data = await f.download_as_bytearray()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch receipt for %s: %s", reg_id, exc)
        return Response("Chekni yuklab bo‘lmadi", status_code=502)

    # Rows created before file receipts existed have no stored mime.
    media_type = reg.receipt_mime or "image/jpeg"
    return Response(
        bytes(data),
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="chek-{reg_id}"',
        },
    )


# ── Events ───────────────────────────────────────────────────────

@login_required
async def events_page(request):
    city = request.query_params.get("city", "")
    rows = []
    for c in config.CITIES:
        if city and c["key"] != city:
            continue
        for ev in db.events_for_city(c["key"]):
            rows.append({"event": ev, "city": c["name"],
                         "regs": db.count_registrations_for_event(ev.id)})
    return _render(request, "events.html", rows=rows, city=city, event=None)


@login_required
async def event_new(request):
    return _render(request, "event_form.html", event=None, error=None)


@login_required
async def event_edit(request):
    ev = db.get_event(int(request.path_params["event_id"]))
    if ev is None:
        return RedirectResponse("/events", status_code=303)
    return _render(request, "event_form.html", event=ev, error=None)


@login_required
async def event_save(request):
    form = await request.form()
    title = (form.get("title") or "").strip()
    city = (form.get("city") or "").strip()
    date = (form.get("date") or "").strip() or None
    description = (form.get("description") or "").strip() or None
    price = (form.get("price") or "").strip() or None
    raw_id = form.get("event_id")

    if not title or city not in config.CITY_BY_KEY:
        existing = db.get_event(int(raw_id)) if raw_id else None
        return _render(
            request,
            "event_form.html",
            event=existing,
            error="Tadbir nomi va viloyat majburiy.",
        )

    if raw_id:
        event_id = int(raw_id)
        for field, value in (
            ("title", title), ("date", date),
            ("description", description), ("price", price),
        ):
            db.update_event(event_id, field, value)
    else:
        event_id = db.add_event(city, title, date, description, price)
        # Tell everyone following that region about the new event.
        bot = request.app.state.bot
        notice = f"🔔 <b>{config.CITY_BY_KEY[city]['name']}da yangi tadbir!</b>\n\n🎉 <b>{title}</b>"
        if date:
            notice += f"\n🗓 {date}"
        if description:
            notice += f"\n{description}"
        if price:
            notice += f"\n💰 To‘lov: {price}"
        for uid in db.user_ids_for_city(city):
            try:
                await bot.send_message(chat_id=uid, text=notice, parse_mode="HTML")
            except Exception:  # noqa: BLE001
                pass

    return RedirectResponse("/events", status_code=303)


@login_required
async def event_delete(request):
    db.delete_event(int(request.path_params["event_id"]))
    return RedirectResponse("/events", status_code=303)


# ── Volunteers ───────────────────────────────────────────────────

@login_required
async def volunteers(request):
    rows = db.all_applications()
    rows.reverse()

    city = request.query_params.get("city", "")
    if city:
        rows = [r for r in rows if r.city == city]

    # Because the form stores a canonical label, a plain match is enough.
    interest = request.query_params.get("interest", "")
    if interest:
        rows = [
            r for r in rows
            if interest.lower() in (r.interests or "").lower()
        ]

    return _render(
        request,
        "volunteers.html",
        rows=rows,
        city=city,
        interest=interest,
        interests=config.INTERESTS,
    )


# ── Broadcast ────────────────────────────────────────────────────

@login_required
async def broadcast_page(request):
    return _render(request, "broadcast.html", sent=None, error=None)


@login_required
async def broadcast_send(request):
    form = await request.form()
    message = (form.get("message") or "").strip()
    target = form.get("target") or "all"

    if not message:
        return _render(request, "broadcast.html", sent=None, error="Xabar bo‘sh.")

    user_ids = db.all_user_ids() if target == "all" else db.user_ids_for_city(target)

    bot = request.app.state.bot
    sent = 0
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=message)
            sent += 1
        except Exception:  # noqa: BLE001 — blocked the bot, deactivated, etc.
            pass

    return _render(request, "broadcast.html", sent=sent, error=None)


# ── Export ───────────────────────────────────────────────────────

@login_required
async def export_xlsx(request):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Volontyorlar"
    ws.append(["ID", "Sana", "Ism-familiya", "Yosh", "Telefon", "Viloyat",
               "Qiziqishlar", "Bio", "Username", "User ID"])
    for a in db.all_applications():
        ws.append([a.id,
                   a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
                   a.full_name, a.age, a.phone, a.city_name, a.interests, a.bio,
                   f"@{a.username}" if a.username else "", a.user_id])

    events = {e.id: e for e in db.all_events()}
    ws2 = wb.create_sheet("Tadbir arizalari")
    ws2.append(["ID", "Sana", "Tadbir", "Viloyat", "Ism-familiya", "Yosh",
                "Telefon", "Holat", "Username", "User ID"])
    for r in db.all_registrations():
        ev = events.get(r.event_id)
        city = config.CITY_BY_KEY.get(ev.city) if ev else None
        ws2.append([r.id,
                    r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
                    ev.title if ev else f"#{r.event_id}",
                    city["name"] if city else "",
                    r.full_name, r.age, r.phone,
                    STATUS_LABEL.get(r.status, r.status),
                    f"@{r.username}" if r.username else "", r.user_id])

    os.makedirs("exports", exist_ok=True)
    path = os.path.join(
        "exports", f"atlon_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    wb.save(path)
    return FileResponse(path, filename=os.path.basename(path))


# ── App factory ──────────────────────────────────────────────────

def create_app(bot) -> Starlette:
    """Build the panel. `bot` is the live PTB Bot used to message users."""
    routes = [
        Route("/login", login_page, methods=["GET"]),
        Route("/login", login_submit, methods=["POST"]),
        Route("/logout", logout, methods=["GET", "POST"]),
        Route("/healthz", healthz, methods=["GET"]),

        Route("/", dashboard, methods=["GET"]),
        Route("/registrations", registrations, methods=["GET"]),
        Route("/registrations/{reg_id:int}/approve", approve, methods=["POST"]),
        Route("/registrations/{reg_id:int}/reject", reject, methods=["POST"]),
        Route("/receipt/{reg_id:int}", receipt_image, methods=["GET"]),

        Route("/events", events_page, methods=["GET"]),
        Route("/events/new", event_new, methods=["GET"]),
        Route("/events/save", event_save, methods=["POST"]),
        Route("/events/{event_id:int}/edit", event_edit, methods=["GET"]),
        Route("/events/{event_id:int}/delete", event_delete, methods=["POST"]),

        Route("/volunteers", volunteers, methods=["GET"]),
        Route("/broadcast", broadcast_page, methods=["GET"]),
        Route("/broadcast", broadcast_send, methods=["POST"]),
        Route("/export.xlsx", export_xlsx, methods=["GET"]),
    ]

    app = Starlette(routes=routes)
    app.state.bot = bot
    return app
