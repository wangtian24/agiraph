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
  useEffect(() => {
    if (failCount.current >= 2) return;

    let ws: WebSocket;
    try {
      ws = createEventSocket(agentId);
      ws.onmessage = (e) => {
        try {
          const event: AgentEvent = JSON.parse(e.data);
          const key = `${event.type}:${event.ts}`;
          if (seenEventTs.current.has(key)) return;
          seenEventTs.current.add(key);
          setEvents((prev) => [...prev.slice(-500), event]);
          if (
            event.type.startsWith("node.") ||
            event.type.startsWith("worker.") ||
            event.type.startsWith("agent.") ||
            event.type === "message.sent"
          ) {
            refresh();
          }
        } catch {}
      };
      ws.onerror = () => {};
    } catch {}
    return () => {
      if (ws) ws.close();
    };
  }, [agentId, refresh, backendError]);

  return { agent, board, workers, conversation, events, allAgents, loading, backendError, refresh };
}
