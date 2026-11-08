"""Telegram approvals ("Phone buzz"). Long polling, so no public webhook is needed.

Each approver sends /start to the bot once; the bot answers with their Telegram id,
which goes into TELEGRAM_APPROVERS="<id>:<name>,...". A button press is checked
against that list, then goes through the same approval rules as the dashboard
(approver != requester, single use, bound to the request hash, expiry).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from .money import fmt_tnd

log = logging.getLogger("thiqa.telegram")


class TelegramApprovals:
    def __init__(self, app, client: httpx.AsyncClient | None = None):
        self.app = app
        self.approvers: dict[int, str] = app.settings.telegram_approvers
        self.base = f"https://api.telegram.org/bot{app.settings.telegram_bot_token}"
        self.client = client
        self.offset = 0
        self.cards: dict[str, list[tuple[int, int, str]]] = {}  # approval_id -> [(chat_id, message_id, text)]

    async def call(self, method: str, **params: Any) -> dict:
        if self.client is None:
            raise RuntimeError("telegram client not started")
        r = await self.client.post(f"{self.base}/{method}", json=params)
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else {}

    async def run(self) -> None:
        q = self.app.bus.subscribe(None)
        async with httpx.AsyncClient(timeout=40) as client:
            self.client = client
            await asyncio.gather(self._notify_loop(q), self._poll_loop())

    # ------------------------------------------------------------ outgoing cards
    @staticmethod
    def card_text(a: dict) -> str:
        reasons = ", ".join(r.get("code", "") for r in a.get("reasons", []))
        return (f"🔐 Thiqa · validation demandée\n{fmt_tnd(a['amount_millimes'])} · {a['product_name']}\n"
                f"client {a['customer_ref']} · risque {a['risk_score']}\n{reasons}\n"
                f"{a['required_approvals']} validateur(s) · paiement SIMULÉ")

    async def send_card(self, a: dict) -> None:
        text = self.card_text(a)
        kb = {"inline_keyboard": [[{"text": "✅ Valider", "callback_data": f"ap:{a['approval_id']}"},
                                   {"text": "❌ Refuser", "callback_data": f"rj:{a['approval_id']}"}]]}
        for chat_id in self.approvers:
            res = await self.call("sendMessage", chat_id=chat_id, text=text, reply_markup=kb)
            msg = res.get("result") or {}
            if msg.get("message_id"):
                self.cards.setdefault(a["approval_id"], []).append((chat_id, msg["message_id"], text))

    async def close_cards(self, approval_id: str, outcome: str) -> None:
        for chat_id, message_id, text in self.cards.pop(approval_id, []):
            await self.call("editMessageText", chat_id=chat_id, message_id=message_id, text=f"{text}\n\n{outcome}")

    async def _notify_loop(self, q: asyncio.Queue) -> None:
        while True:
            ev = await q.get()
            try:
                if (ev.get("run_id") or "").startswith("run_"):
                    continue
                if ev["type"] == "approval.requested":
                    await self.send_card(ev["payload"])
                elif ev["type"] in ("approval.granted", "approval.rejected") and ev["payload"].get("approval_id"):
                    await self.close_cards(ev["payload"]["approval_id"], ev["summary"])
            except Exception:  # one bad card must not stop the bot
                log.exception("telegram notify failed")
                continue

    # ------------------------------------------------------------ incoming buttons
    async def _poll_loop(self) -> None:
        while True:
            try:
                if self.client is None:
                    raise RuntimeError("telegram client not started")
                r = await self.client.get(f"{self.base}/getUpdates", params={
                    "timeout": 25, "offset": self.offset, "allowed_updates": json.dumps(["callback_query", "message"])})
                for upd in r.json().get("result", []):
                    self.offset = upd["update_id"] + 1
                    await self.handle(upd)
            except Exception:
                log.warning("telegram polling failed, retrying in 3 s")
                await asyncio.sleep(3)

    async def handle(self, upd: dict) -> str | None:
        msg = upd.get("message")
        if msg and str(msg.get("text", "")).startswith("/start"):
            uid = msg["from"]["id"]
            known = self.approvers.get(uid)
            await self.call("sendMessage", chat_id=msg["chat"]["id"], text=(
                f"Salam {known} ✅ tu reçois les validations Thiqa." if known else
                f"Ton id Telegram est {uid}. Ajoute-le dans .env : TELEGRAM_APPROVERS={uid}:<ton_nom> puis redémarre."))
            return "start"
        cq = upd.get("callback_query")
        if not cq:
            return None
        approver = self.approvers.get(cq["from"]["id"])
        action, _, approval_id = str(cq.get("data", "")).partition(":")
        if approver is None:
            await self.call("answerCallbackQuery", callback_query_id=cq["id"], text="Tu n'es pas validateur.", show_alert=True)
            return "not_an_approver"
        if action == "ap":
            res, _ = await self.app.orch.vote(approval_id, approver, channel="telegram")
        elif action == "rj":
            res = await self.app.orch.reject(approval_id, approver)
        else:
            return None
        text = ("✅ " + res.message) if res.ok else ("⛔ " + res.message)
        await self.call("answerCallbackQuery", callback_query_id=cq["id"], text=text[:190], show_alert=not res.ok)
        return "ok" if res.ok else (res.refusal or "refused")
