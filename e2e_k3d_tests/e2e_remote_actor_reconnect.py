from __future__ import annotations

import json
import unittest
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from e2e_k3d_tests._harness import (
    AGENT_A_NODE,
    authoritative_repo_root,
    current_git_head,
    ensure_cluster_ready,
    port_forward_worker,
)
from openagentic_sdk.options import AgentDefinition, AgentExecutorDefinition, AgentWorkspaceDefinition
from openagentic_sdk.subagents.actor_protocol import ActorEnvelope
from openagentic_sdk.subagents.remote_http import _request_to_dict
from openagentic_sdk.subagents.remote_types import RemoteTaskRequest


class TestRemoteActorReconnect(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_cluster_ready()

    def test_worker_stream_replay_resumes_after_client_disconnect_without_reordering(self) -> None:
        repo_root = authoritative_repo_root()
        request = RemoteTaskRequest(
            parent_session_id="r" * 32,
            parent_tool_use_id="call_task",
            agent_name="research",
            prompt="RESEARCH_SLICE::direction-1",
            definition=AgentDefinition(
                description="k3d actor replay worker",
                prompt="REMOTE_RESEARCH_DEF",
                tools=("Read", "WebSearch"),
                executor=AgentExecutorDefinition(kind="k3s", node_name=AGENT_A_NODE),
                workspace=AgentWorkspaceDefinition(mode="readonly"),
            ),
            cwd=str(repo_root),
            project_dir=str(repo_root),
            git_revision=current_git_head(),
        )

        with port_forward_worker(AGENT_A_NODE) as base_url:
            dispatch_response = urllib_request.urlopen(
                urllib_request.Request(
                    url=f"{base_url}/dispatch",
                    data=json.dumps(_request_to_dict(request), ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=10.0,
            )
            try:
                execution_id = dispatch_response.headers.get("X-OA-Execution-ID") or ""
                self.assertTrue(execution_id)
                first = self._read_envelope_line(dispatch_response)
            finally:
                dispatch_response.close()

            replay_query = urllib_parse.urlencode({"execution_id": execution_id, "after_seq": str(first.seq)})
            replay_response = urllib_request.urlopen(
                urllib_request.Request(
                    url=f"{base_url}/stream?{replay_query}",
                    method="GET",
                ),
                timeout=15.0,
            )
            try:
                replayed = self._read_all_envelopes(replay_response)
            finally:
                replay_response.close()

        all_envelopes = [first, *replayed]
        self.assertGreaterEqual(len(all_envelopes), 3)
        self.assertEqual([envelope.seq for envelope in all_envelopes], sorted(envelope.seq for envelope in all_envelopes))
        self.assertEqual(len({envelope.message_id for envelope in all_envelopes}), len(all_envelopes))
        self.assertEqual(replayed[0].seq, first.seq + 1)
        self.assertEqual(all_envelopes[-1].kind, "down")

    def _read_envelope_line(self, response) -> ActorEnvelope:  # noqa: ANN001
        line = response.readline()
        if not line:
            raise AssertionError("expected at least one replayable actor envelope")
        return ActorEnvelope.from_dict(json.loads(line.decode("utf-8")))

    def _read_all_envelopes(self, response) -> list[ActorEnvelope]:  # noqa: ANN001
        items: list[ActorEnvelope] = []
        while True:
            line = response.readline()
            if not line:
                return items
            text = line.decode("utf-8").strip()
            if not text:
                continue
            items.append(ActorEnvelope.from_dict(json.loads(text)))


if __name__ == "__main__":
    unittest.main()
