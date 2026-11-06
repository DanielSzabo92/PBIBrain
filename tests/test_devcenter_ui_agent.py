"""Step U9 (ticket 24): the Agent and Log replies of the fake server follow the S10 contract schemas.

The Agent and Log e2e specs run on the fake server, so its GET session lists, its GET log filters,
its GET plan?include_proposals=ready read, and its question_answer and proposal calls must have the S10 shapes.
"""

from __future__ import annotations

import unittest

from tests import devcenter_ui_server as fake
from tests.test_devcenter_ui_contract import _contract_validator


class FakeAgentContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = fake.FakeDevCenter()
        self.state.agent_review({})

    def validate(self, name: str, value: object) -> None:
        errors = sorted(_contract_validator(name).iter_errors(value), key=lambda error: list(error.path))
        self.assertEqual([f"{list(error.path)}: {error.message}"[:300] for error in errors], [], name)

    def get(self, path: str, query: dict[str, list[str]] | None = None) -> dict:
        return self.state.read("GET", f"/api/devcenter/{path}", query or {}, {})

    def call(self, method: str, payload: dict) -> dict:
        request = {"base_revision": self.state.revision, **payload}
        self.validate(f"jsapi/{method}.request.json", request)
        reply = self.state.call(method, request)
        self.validate(f"jsapi/{method}.reply.json", reply)
        return reply

    def test_session_has_each_proposal_status_and_open_and_answered_questions(self) -> None:
        session = self.get("session")
        self.validate("http/session.reply.json", session)
        blocked = [item["blocked"] for item in session["proposals"]["open"]]
        self.assertEqual(sorted(blocked, key=str), sorted([None, None, "user_choice_conflict", "source_changed"], key=str))
        self.assertEqual([item["id"] for item in session["questions"]["open"]], ["q-1", "q-2"])
        self.assertEqual([item["id"] for item in session["questions"]["answered"]], ["q-0"])

    def test_question_answer_moves_the_question_to_answered(self) -> None:
        reply = self.call("question_answer", {"question_id": "q-1", "option_id": "a"})
        self.assertTrue(reply["applied"])
        session = self.get("session")
        self.validate("http/session.reply.json", session)
        self.assertEqual([item["id"] for item in session["questions"]["open"]], ["q-2"])
        answered = {item["id"]: item for item in session["questions"]["answered"]}
        self.assertEqual(answered["q-1"]["selected_option"], "a")
        with self.assertRaises(fake.FakeError) as caught:
            self.state.call("question_answer", {"base_revision": self.state.revision, "question_id": "q-1", "option_id": "a"})
        self.assertEqual(caught.exception.code, "not_found")

    def test_plan_with_ready_proposals_is_the_plan_after_accept(self) -> None:
        now = self.get("plan")
        after = self.get("plan", {"include_proposals": ["ready"]})
        self.validate("http/plan.reply.json", now)
        self.validate("http/plan.reply.json", after)
        self.assertEqual((now["status"], len(now["blocking"])), ("invalid", 1))
        self.assertEqual((after["status"], len(after["blocking"])), ("valid_with_warnings", 0))

    def test_accept_all_skips_the_blocked_proposals(self) -> None:
        reply = self.call("proposal_accept_all", {})
        self.assertEqual(sorted(reply["accepted_ids"]), ["p-1", "p-2"])
        self.assertEqual(sorted(item["reason"] for item in reply["skipped"]), ["source_changed", "user_choice_conflict"])

    def test_log_filters_apply_before_the_paging(self) -> None:
        full = self.get("log", {"limit": ["50"]})
        self.validate("http/log.reply.json", full)
        self.assertEqual(full["total"], 62)
        self.assertTrue(full["has_more"])
        self.assertEqual(len(full["entries"]), 50)
        agent = self.get("log", {"author": ["agent"]})
        self.assertEqual([entry["proposal_id"] for entry in agent["entries"]], ["p-1"])
        by_proposal = self.get("log", {"proposal_id": ["p-1"]})
        self.assertEqual(by_proposal["total"], 1)
        by_target = self.get("log", {"target": ["row-gross-margin"], "action": ["merge_choice_set"]})
        self.assertEqual(by_target["total"], 1)
        self.assertFalse(by_target["has_more"])

    def test_an_agent_question_through_post_questions_has_the_schema(self) -> None:
        options = [{"id": "a", "label": "Keep target"}, {"id": "b", "label": "Take from Finance model"}]
        reply = self.state.read("POST", "/api/devcenter/questions", {}, {
            "base_revision": self.state.revision, "target_id": "row-date", "text": "Keep Date?", "options": options,
            "recommended_option": "a", "reason": "The Date tables are the same.",
        })
        self.assertEqual(reply["question"]["status"], "open")
        session = self.get("session")
        self.validate("http/session.reply.json", session)
        self.assertEqual(session["questions"]["open"][-1]["recommended_option"], "a")


if __name__ == "__main__":
    unittest.main()
