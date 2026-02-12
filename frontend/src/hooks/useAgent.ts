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
  const seenEventTs = useRef<Set<string>>(new Set());

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
    } catch (err) {
      console.error("Failed to refresh agent:", err);
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

  // Poll every 3 seconds
  useEffect(() => {
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [refresh]);

  // Poll all agents every 5 seconds
  useEffect(() => {
    const interval = setInterval(refreshAllAgents, 5000);
    return () => clearInterval(interval);
  }, [refreshAllAgents]);

  // WebSocket for live events
  useEffect(() => {
    let ws: WebSocket;
    try {
      ws = createEventSocket(agentId);
      ws.onmessage = (e) => {
        try {
          const event: AgentEvent = JSON.parse(e.data);
          const key = `${event.type}:${event.ts}`;
          // Deduplicate against historical events
          if (seenEventTs.current.has(key)) return;
          seenEventTs.current.add(key);
          setEvents((prev) => [...prev.slice(-500), event]);
          // Refresh on important events
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
  }, [agentId, refresh]);

  return { agent, board, workers, conversation, events, allAgents, loading, refresh };
}
