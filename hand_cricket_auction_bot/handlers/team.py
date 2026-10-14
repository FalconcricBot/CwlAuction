"""
handlers/team.py
-----------------
Team viewing commands: /teams (admin/anyone), /team and /mypurse (captains).
"""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from database import queries as q
from services import captain_service
from utils.helpers import fmt_money, player_display_name

TEAM_NUM_ICONS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def _mention(telegram_id: int, name: str) -> str:
    """Renders a clickable Telegram mention that opens the user's profile,
    with their display name as the link text (HTML parse mode)."""
    from html import escape
    return f"<a href='tg://user?id={telegram_id}'>{escape(name)}</a>"


async def _format_team_block(team, squad, detailed: bool = False) -> str:
    captain = await q.get_captain_by_id(team["captain_id"])
    captain_name = captain["captain_name"] if captain else "Unknown"

    lines = [
        f"🏳️ <b>{team['name']}</b> ({team['short_name']})",
        f"👑 Captain: {_mention(team['captain_telegram_id'], captain_name)}",
    ]
    if team["vice_captain_telegram_id"]:
        lines.append(f"🎖️ Vice-captain: {_mention(team['vice_captain_telegram_id'], 'view profile')}")
    lines += [
        f"💰 Total Purse: {fmt_money(team['starting_purse'])}",
        f"💸 Spent: {fmt_money(team['starting_purse'] - team['remaining_purse'])}",
        f"💰 Remaining: {fmt_money(team['remaining_purse'])}",
        f"👥 Squad: {len(squad)}/{team['max_squad_size']}",
    ]
    if detailed and squad:
        lines.append("")
        for p in squad:
            name = player_display_name(p["first_name"], p["last_name"])
            lines.append(f"  • {_mention(p['telegram_id'], name)} — {fmt_money(p['sold_price'])}")
    return "\n".join(lines)


async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    teams_data = await captain_service.list_teams_with_squad()
    if not teams_data:
        await update.effective_message.reply_text("🏳️ No teams have been created yet.")
        return

    lines = ["🏳️ <b>TEAMS</b>", "━━━━━━━━━━━━━━━━━━━━", ""]
    for i, entry in enumerate(teams_data):
        team, squad = entry["team"], entry["squad"]
        captain = await q.get_captain_by_id(team["captain_id"])
        captain_name = captain["captain_name"] if captain else "Unknown"
        icon = TEAM_NUM_ICONS[i] if i < len(TEAM_NUM_ICONS) else f"{i+1}."
        lines.append(f"{icon} <b>{team['name']}</b>")
        lines.append(f"   👑 {_mention(team['captain_telegram_id'], captain_name)}")
        lines.append(f"   💰 {fmt_money(team['remaining_purse'])} remaining")
        lines.append(f"   👥 {len(squad)}/{team['max_squad_size']} players")
        lines.append("")

    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def my_team_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    team = await captain_service.get_my_team(user.id)
    if team is None:
        await update.effective_message.reply_text(
            "❌ You do not have a team. Register as a captain first with /becomecaptain."
        )
        return

    squad = await q.get_team_squad(team["id"])
    text = await _format_team_block(team, squad, detailed=True)
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def my_purse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    team = await captain_service.get_my_team(user.id)
    if team is None:
        await update.effective_message.reply_text(
            "❌ You do not have a team. Register as a captain first with /becomecaptain."
        )
        return

    text = (
        f"💰 <b>{team['name']} PURSE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Starting Purse: {fmt_money(team['starting_purse'])}\n"
        f"Spent: {fmt_money(team['starting_purse'] - team['remaining_purse'])}\n"
        f"Remaining: <b>{fmt_money(team['remaining_purse'])}</b>"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# /setvicecaptain - primary captain sets/clears their team's vice-captain
# ---------------------------------------------------------------------------

async def setvicecaptain_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not context.args:
        await update.effective_message.reply_text(
            "Usage: /setvicecaptain <telegram_id>  or  /setvicecaptain off\n\n"
            "The vice-captain can place bids on your team's behalf. Only "
            "the primary captain can set or clear this."
        )
        return

    from utils.helpers import safe_int

    if context.args[0].lower() in ("off", "none", "clear", "remove"):
        try:
            team = await captain_service.set_vice_captain(user.id, None)
        except captain_service.CaptainServiceError as e:
            await update.effective_message.reply_text(f"❌ {e}")
            return
        await update.effective_message.reply_text(f"✅ Vice-captain removed for {team['name']}.")
        return

    vice_id = safe_int(context.args[0])
    if vice_id is None:
        await update.effective_message.reply_text("❌ Invalid Telegram ID.")
        return

    try:
        team = await captain_service.set_vice_captain(user.id, vice_id)
    except captain_service.CaptainServiceError as e:
        await update.effective_message.reply_text(f"❌ {e}")
        return

    await update.effective_message.reply_text(
        f"✅ Vice-captain set for {team['name']}. They can now bid on your team's behalf."
    )
    try:
        await context.bot.send_message(
            vice_id,
            f"🎖️ You've been made vice-captain of {team['name']}! "
            "You can now place bids for this team using /bid and /allin."
        )
    except Exception:
        pass

