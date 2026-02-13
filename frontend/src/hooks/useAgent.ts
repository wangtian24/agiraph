"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AgentSummary,
  BoardView,
  ConversationMessage,
  WorkerView,
  AgentEvent,
  getAgent,
  getBoard,
  getConversation,
  getWorkers,
  getEvents,
  listAgents,
  createEventSocket,
} from "@/lib/api";

const POLL_OK = 3000;
const POLL_ALL_OK = 5000;
const POLL_ERR = 30000; // back off to 30s when backend is down
const EVENT_BATCH_MS = 300; // batch WebSocket events before updating state
const REFRESH_DEBOUNCE_MS = 1000; // debounce refresh() calls from WS events

/**
 * Hook to poll and subscribe to a single agent's state.
 */
export function useAgent(agentId: string) {
  const [agent, setAgent] = useState<AgentSummary | null>(null);
  const [board, setBoard] = useState<BoardView | null>(null);
  const [workers, setWorkers] = useState<WorkerView[]>([]);
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [allAgents, setAllAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [backendError, setBackendError] = useState<string | null>(null);
  const seenEventTs = useRef<Set<string>>(new Set());
  const failCount = useRef(0);

  // Debounced refresh: coalesce rapid WebSocket-triggered refresh() calls
  const refreshPending = useRef(false);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshInFlight = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const [a, b, w, c] = await Promise.all([
        getAgent(agentId),
        getBoard(agentId),
        getWorkers(agentId),
        getConversation(agentId),
      ]);
      setAgent(a);
      setBoard(b);
      setWorkers(w);
      setConversation(c);
      failCount.current = 0;
      setBackendError(null);
    } catch {
      failCount.current++;
      if (failCount.current >= 2) {
        setBackendError("Backend unreachable — is the server running? Check config.toml for port config.");
      }
    }
    setLoading(false);
  }, [agentId]);

  // Debounced version of refresh — at most once per REFRESH_DEBOUNCE_MS
  const debouncedRefresh = useCallback(() => {
    if (refreshInFlight.current) {
      refreshPending.current = true;
      return;
    }
    if (refreshTimer.current) return; // already scheduled
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = null;
      refreshInFlight.current = true;
      refresh().finally(() => {
        refreshInFlight.current = false;
        if (refreshPending.current) {
          refreshPending.current = false;
          debouncedRefresh();
        }
      });
    }, REFRESH_DEBOUNCE_MS);
  }, [refresh]);

  const refreshAllAgents = useCallback(async () => {
    try {
      setAllAgents(await listAgents());
    } catch {}
  }, []);

  // Initial load — fetch existing events via HTTP before WebSocket connects
  useEffect(() => {
    refresh();
    refreshAllAgents();

    // Backfill historical events
    getEvents(agentId, 500).then((historical) => {
      if (historical.length > 0) {
        for (const ev of historical) {
          seenEventTs.current.add(`${ev.type}:${ev.ts}`);
        }
        setEvents(historical);
      }
    }).catch(() => {});
  }, [agentId, refresh, refreshAllAgents]);

  // Poll with backoff: 3s when healthy, 30s when backend is down
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      refresh().then(() => {
        const delay = failCount.current >= 2 ? POLL_ERR : POLL_OK;
        timer = setTimeout(tick, delay);
      });
    };
    timer = setTimeout(tick, POLL_OK);
    return () => clearTimeout(timer);
  }, [refresh]);

  // Poll all agents with same backoff
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      refreshAllAgents().then(() => {
        const delay = failCount.current >= 2 ? POLL_ERR : POLL_ALL_OK;
        timer = setTimeout(tick, delay);
      });
    };
    timer = setTimeout(tick, POLL_ALL_OK);
    return () => clearTimeout(timer);
  }, [refreshAllAgents]);

  // WebSocket for live events — skip when backend is known down
  // Batches incoming events to avoid per-event re-renders.
  useEffect(() => {
    if (failCount.current >= 2) return;

    let ws: WebSocket;
    let eventBuffer: AgentEvent[] = [];
    let batchTimer: ReturnType<typeof setTimeout> | null = null;
    let needsRefresh = false;

    const flushBatch = () => {
      batchTimer = null;
      if (eventBuffer.length > 0) {
        const batch = eventBuffer;
        eventBuffer = [];
        setEvents((prev) => [...prev.slice(-(500 - batch.length)), ...batch]);
      }
      if (needsRefresh) {
        needsRefresh = false;
        debouncedRefresh();
      }
    };

    try {
      ws = createEventSocket(agentId);
      ws.onmessage = (e) => {
        try {
          const event: AgentEvent = JSON.parse(e.data);
          const key = `${event.type}:${event.ts}`;
          if (seenEventTs.current.has(key)) return;
          seenEventTs.current.add(key);
          eventBuffer.push(event);
          if (
            event.type.startsWith("node.") ||
            event.type.startsWith("worker.") ||
            event.type.startsWith("agent.") ||
            event.type === "message.sent"
          ) {
            needsRefresh = true;
          }
          // Schedule batch flush if not already scheduled
          if (!batchTimer) {
            batchTimer = setTimeout(flushBatch, EVENT_BATCH_MS);
          }
        } catch {}
      };
      ws.onerror = () => {};
    } catch {}
    return () => {
      if (batchTimer) clearTimeout(batchTimer);
      if (ws) ws.close();
    };
  }, [agentId, debouncedRefresh, backendError]);

  return { agent, board, workers, conversation, events, allAgents, loading, backendError, refresh };
}
