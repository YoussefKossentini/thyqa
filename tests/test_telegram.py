import json

import httpx

from thiqa.schemas import JourneyState
from thiqa.telegram_bot import TelegramApprovals

from .conftest import run


def test_telegram_button_goes_through_the_same_approval_rules(make_app):
    app = make_app(telegram_bot_token="TEST", telegram_approvers={111: "mouna", 222: "youssef"})
    sent = []

    def handler(request: httpx.Request):
        sent.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content or b"{}")))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent)}})

    async def scenario():
        bot = TelegramApprovals(app, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        r = await app.orch.manual_order("9antra", "ai_bootcamp", "full", requested_by="youssef")
        apr = app.repo.get_case(r.case_id).pending_approval_id
        await bot.send_card(app.repo.get_approval(apr).model_dump(mode="json"))
        stranger = await bot.handle({"callback_query": {"id": "1", "from": {"id": 999}, "data": f"ap:{apr}"}})
        self_vote = await bot.handle({"callback_query": {"id": "2", "from": {"id": 222}, "data": f"ap:{apr}"}})
        ok = await bot.handle({"callback_query": {"id": "3", "from": {"id": 111}, "data": f"ap:{apr}"}})
        return r.case_id, stranger, self_vote, ok

    case_id, stranger, self_vote, ok = run(scenario())
    assert stranger == "not_an_approver" and self_vote == "self_approval" and ok == "ok"
    assert app.repo.get_case(case_id).state == JourneyState.PAID
    assert [m for m, _ in sent].count("sendMessage") == 2  # one card per approver
