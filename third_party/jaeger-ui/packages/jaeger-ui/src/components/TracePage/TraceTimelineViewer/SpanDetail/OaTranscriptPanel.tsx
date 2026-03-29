// Copyright (c) 2026 OpenAgentic Contributors.
// SPDX-License-Identifier: Apache-2.0

import React, { useEffect, useMemo, useState } from 'react';

import { IOtelSpan } from '../../../../types/otel';

import './OaTranscriptPanel.css';

type TranscriptMessage = {
  role: string;
  seq?: number;
  text: string;
  ts?: number;
};

type TranscriptPayload = {
  agent_name: string;
  error?: string;
  messages: TranscriptMessage[];
  session_id: string;
  source: string;
};

type TranscriptTarget = {
  agentName: string | null;
  cacheKey: string;
  endpoint: string;
  executionId: string | null;
  kind: 'child' | 'root';
  sessionId: string;
  targetNode: string | null;
};

type TranscriptEntry =
  | {
      payload: TranscriptPayload;
      status: 'ready';
    }
  | {
      detail: string;
      errorCode: string;
      status: 'error';
    };

const transcriptCache = new Map<string, TranscriptEntry>();
const transcriptInflight = new Map<string, Promise<TranscriptEntry>>();

function displayAgentMode(kind: TranscriptTarget['kind']): string {
  return kind === 'child' ? '远程子会话' : '主会话';
}

function displayMessageRole(role: string): string {
  if (role === 'user') {
    return '用户';
  }
  if (role === 'assistant') {
    return '助手';
  }
  return role;
}

function getAttributeText(span: IOtelSpan, key: string): string | null {
  const match = span.attributes.find(attr => attr.key === key);
  return match && typeof match.value === 'string' && match.value.trim() ? match.value.trim() : null;
}

function resolveTranscriptTarget(span: IOtelSpan): TranscriptTarget | null {
  const childSessionId = getAttributeText(span, 'oa.child_session_id');
  const targetNode = getAttributeText(span, 'oa.target_node');
  const sessionId = getAttributeText(span, 'oa.session_id');
  const executionId = getAttributeText(span, 'oa.execution.id');
  const agentName = getAttributeText(span, 'oa.agent.name');

  if (sessionId && childSessionId && sessionId !== childSessionId) {
    return {
      agentName,
      cacheKey: `root:${sessionId}`,
      endpoint: `/oa/transcript/session/${encodeURIComponent(sessionId)}`,
      executionId,
      kind: 'root',
      sessionId,
      targetNode: null,
    };
  }
  if (childSessionId && targetNode) {
    return {
      agentName,
      cacheKey: `child:${targetNode}:${childSessionId}`,
      endpoint: `/oa/transcript/child/${encodeURIComponent(targetNode)}/${encodeURIComponent(childSessionId)}`,
      executionId,
      kind: 'child',
      sessionId: childSessionId,
      targetNode,
    };
  }
  if (sessionId) {
    return {
      agentName,
      cacheKey: `root:${sessionId}`,
      endpoint: `/oa/transcript/session/${encodeURIComponent(sessionId)}`,
      executionId,
      kind: 'root',
      sessionId,
      targetNode: null,
    };
  }
  return null;
}

function normalizeMessages(raw: unknown): TranscriptMessage[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.flatMap(item => {
    if (!item || typeof item !== 'object') {
      return [];
    }
    const role = typeof (item as TranscriptMessage).role === 'string' ? (item as TranscriptMessage).role : 'assistant';
    const text = typeof (item as TranscriptMessage).text === 'string' ? (item as TranscriptMessage).text : '';
    const message: TranscriptMessage = { role, text };
    if (typeof (item as TranscriptMessage).seq === 'number') {
      message.seq = (item as TranscriptMessage).seq;
    }
    if (typeof (item as TranscriptMessage).ts === 'number') {
      message.ts = (item as TranscriptMessage).ts;
    }
    return [message];
  });
}

function normalizeEntry(status: number, raw: unknown): TranscriptEntry {
  if (!raw || typeof raw !== 'object') {
    return {
      detail: `HTTP ${status}`,
      errorCode: 'transcript_unavailable',
      status: 'error',
    };
  }
  const payload = raw as Partial<TranscriptPayload>;
  if (status >= 400) {
    const errorCode = typeof payload.error === 'string' && payload.error ? payload.error : 'transcript_unavailable';
    return {
      detail: `HTTP ${status}`,
      errorCode,
      status: 'error',
    };
  }
  const sessionId = typeof payload.session_id === 'string' ? payload.session_id : '';
  const source = typeof payload.source === 'string' ? payload.source : '';
  const agentName = typeof payload.agent_name === 'string' ? payload.agent_name : '';
  return {
    payload: {
      agent_name: agentName,
      messages: normalizeMessages(payload.messages),
      session_id: sessionId,
      source,
    },
    status: 'ready',
  };
}

async function fetchTranscript(target: TranscriptTarget): Promise<TranscriptEntry> {
  const cached = transcriptCache.get(target.cacheKey);
  if (cached) {
    return cached;
  }
  const pending = transcriptInflight.get(target.cacheKey);
  if (pending) {
    return pending;
  }
  const request = (async () => {
    try {
      const response = await fetch(target.endpoint, {
        headers: {
          Accept: 'application/json',
        },
      });
      const raw = await response.json().catch(() => null);
      const entry = normalizeEntry(response.status, raw);
      transcriptCache.set(target.cacheKey, entry);
      return entry;
    } catch (error) {
      const entry: TranscriptEntry = {
        detail: error instanceof Error ? error.message : 'network failure',
        errorCode: 'transcript_unavailable',
        status: 'error',
      };
      transcriptCache.set(target.cacheKey, entry);
      return entry;
    } finally {
      transcriptInflight.delete(target.cacheKey);
    }
  })();
  transcriptInflight.set(target.cacheKey, request);
  return request;
}

function TranscriptMeta({ target }: { target: TranscriptTarget }) {
  return (
    <div className="OaTranscriptPanel--meta">
      <span className="OaTranscriptPanel--metaItem">模式：{displayAgentMode(target.kind)}</span>
      <span className="OaTranscriptPanel--metaItem">会话：{target.sessionId}</span>
      {target.targetNode ? <span className="OaTranscriptPanel--metaItem">节点：{target.targetNode}</span> : null}
      {target.agentName ? <span className="OaTranscriptPanel--metaItem">代理：{target.agentName}</span> : null}
      {target.executionId ? <span className="OaTranscriptPanel--metaItem">执行：{target.executionId}</span> : null}
    </div>
  );
}

export default function OaTranscriptPanel({ span }: { span: IOtelSpan }) {
  const target = useMemo(() => resolveTranscriptTarget(span), [span]);
  const [entry, setEntry] = useState<TranscriptEntry | null>(() =>
    target ? transcriptCache.get(target.cacheKey) ?? null : null
  );
  const [isLoading, setIsLoading] = useState<boolean>(Boolean(target && !transcriptCache.has(target.cacheKey)));

  useEffect(() => {
    if (!target) {
      setEntry(null);
      setIsLoading(false);
      return undefined;
    }
    const cached = transcriptCache.get(target.cacheKey);
    if (cached) {
      setEntry(cached);
      setIsLoading(false);
      return undefined;
    }
    let cancelled = false;
    setIsLoading(true);
    fetchTranscript(target).then(result => {
      if (!cancelled) {
        setEntry(result);
        setIsLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [target]);

  if (!target) {
    return null;
  }

  return (
    <section className="OaTranscriptPanel">
      <div className="OaTranscriptPanel--header">
        <div>
          <h3 className="OaTranscriptPanel--title">会话正文</h3>
          <p className="OaTranscriptPanel--subtitle">
            当前 Span 暴露了 `oa.session_id` / `oa.child_session_id`，因此界面可以按需拉取会话正文。
          </p>
        </div>
      </div>
      <TranscriptMeta target={target} />
      {isLoading ? <div className="OaTranscriptPanel--state">正在加载会话正文...</div> : null}
      {!isLoading && entry?.status === 'error' ? (
        <div className="OaTranscriptPanel--error">
          <div className="OaTranscriptPanel--errorCode">会话正文暂不可用</div>
          <div className="OaTranscriptPanel--errorDetail">{entry.detail}</div>
        </div>
      ) : null}
      {!isLoading && entry?.status === 'ready' ? (
        <div className="OaTranscriptPanel--messages">
          {entry.payload.messages.length ? (
            entry.payload.messages.map((message, index) => (
              <article className={`OaTranscriptPanel--message is-${message.role}`} key={`${message.role}-${index}`}>
                <div className="OaTranscriptPanel--messageMeta">
                  <span className="OaTranscriptPanel--role">{displayMessageRole(message.role)}</span>
                  {typeof message.seq === 'number' ? (
                    <span className="OaTranscriptPanel--seq">序号 {message.seq}</span>
                  ) : null}
                </div>
                <pre className="OaTranscriptPanel--text">{message.text}</pre>
              </article>
            ))
          ) : (
            <div className="OaTranscriptPanel--state">当前会话还没有可显示的 user/assistant 正文。</div>
          )}
        </div>
      ) : null}
    </section>
  );
}
