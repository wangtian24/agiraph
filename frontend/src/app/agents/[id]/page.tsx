"use client";

import { use, useState, useRef, useEffect, useMemo, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { useAgent } from "@/hooks/useAgent";
import {
  sendMessage,
  respondToQuestion,
  stopAgent,
  getWorkspace,
  getMemory,
  WorkspaceResult,
  FileEntry,
  ConversationMessage,
  AgentEvent,
  AgentSummary,
  WorkerView,
} from "@/lib/api";

type Tab = "chat" | "team" | "files";

// Deterministic human name from agent ID
const HUMAN_NAMES = [
  "Alice", "Bob", "Charlie", "Diana", "Eli", "Fiona", "George", "Hannah",
  "Ivan", "Julia", "Kevin", "Luna", "Marcus", "Nina", "Oscar", "Penny",
  "Quinn", "Rosa", "Sam", "Tara", "Uri", "Vera", "Wyatt", "Xena", "Yuri", "Zoe",
];

function humanName(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = ((hash << 5) - hash + id.charCodeAt(i)) | 0;
  }
  return HUMAN_NAMES[Math.abs(hash) % HUMAN_NAMES.length];
}

// Shorten role strings — keep only the first 1-2 words, max 20 chars
function shortRole(role: string): string {
  if (role.length <= 20) return role;
  const words = role.split(/\s+/);
  let result = words[0];
  if (words.length > 1 && (result.length + words[1].length + 1) <= 20) {
    result += " " + words[1];
  }
  return result;
}

function SpinnerIcon({ className = "w-3 h-3" }: { className?: string }) {
  return (
    <svg className={`${className} animate-spin`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function SidebarTeamMember({ name, role, status, model }: { name: string; role: string; status: string; model?: string }) {
  const isBusy = status === "busy" || status === "working" || status === "active";
  const dotColor: Record<string, string> = {
    active: "bg-blue-500",
    idle: "bg-gray-400",
    busy: "bg-blue-500",
    working: "bg-blue-500",
    completed: "bg-green-500",
    failed: "bg-red-500",
  };
  // Shorten model string for display
  const shortModel = model ? model.replace("anthropic/", "").replace("openai/", "").replace("claude-code/", "cc:") : "";
  return (
    <div className="px-2 py-1">
      <div className="flex items-center gap-1.5 text-[11px] text-gray-600">
        {isBusy ? (
          <SpinnerIcon className="w-2.5 h-2.5 text-blue-500 shrink-0" />
        ) : (
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor[status] || "bg-gray-400"}`} />
        )}
        <span className="truncate font-medium">{name}</span>
        <span className="text-[9px] text-gray-400 ml-auto capitalize">{status}</span>
      </div>
      <div className="ml-3.5 text-[9px] text-gray-400 truncate">
        {role}{shortModel ? ` · ${shortModel}` : ""}
      </div>
    </div>
  );
}

export default function AgentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: agentId } = use(params);
  const { agent, conversation, events, workers, allAgents, loading } = useAgent(agentId);
  const [tab, setTab] = useState<Tab>("chat");
  const [messageInput, setMessageInput] = useState("");
  const [sending, setSending] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Check if any worker is busy
  const anyWorkerBusy = workers.some((w) => w.status === "busy") ||
    (agent?.status === "working" || agent?.status === "busy");

  // Build team members list for @mention (coordinator + workers)
  const teamMembers = useMemo(() => {
    const members: TeamMemberOption[] = [
      { display: humanName(agentId), busName: "coordinator", role: "Coordinator" },
    ];
    for (const w of workers) {
      members.push({ display: humanName(w.id), busName: w.name, role: shortRole(w.role || "Generalist") });
    }
    return members;
  }, [agentId, workers]);

  const handleSend = async () => {
    if (!messageInput.trim()) return;
    setSending(true);
    // Parse @mention to determine message target
    let to = "coordinator";
    const mentionMatch = messageInput.match(/@(\w+)/);
    if (mentionMatch) {
      const mentioned = mentionMatch[1].toLowerCase();
      const target = teamMembers.find(
        (m) => m.display.toLowerCase() === mentioned
      );
      if (target) to = target.busName;
    }
    try {
      await sendMessage(agentId, messageInput, to);
      setMessageInput("");
    } catch {}
    setSending(false);
  };

  const handleRespond = async (response: string) => {
    try {
      await respondToQuestion(agentId, response);
    } catch {}
  };

  const handleStop = async () => {
    try {
      await stopAgent(agentId);
    } catch {}
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-400">Loading agent...</div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-400">Agent not found.</div>
      </div>
    );
  }

  const statusColor: Record<string, string> = {
    idle: "bg-gray-400",
    working: "bg-blue-500",
    busy: "bg-blue-500",
    waiting_for_human: "bg-yellow-500",
    completed: "bg-green-500",
    stopped: "bg-gray-400",
  };

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: "chat", label: "Chat", icon: "💬" },
    { key: "team", label: "Team", icon: "👥" },
    { key: "files", label: "Files", icon: "📁" },
  ];

  return (
    <div className="flex h-screen">
      {/* Narrow Sidebar */}
      <div className="w-52 bg-slate-50 border-r border-gray-200 flex flex-col shrink-0">
        <div className="p-4 border-b border-gray-200">
          <div className="text-lg font-bold text-gray-900 mb-1">Agiraph</div>
          <Link href="/" className="text-blue-500 text-xs hover:text-blue-700">
            &larr; Back to agents
          </Link>
          <div className="mt-3 flex items-center gap-2">
            {anyWorkerBusy ? (
              <SpinnerIcon className="w-3 h-3 text-blue-500" />
            ) : (
              <span className={`w-2 h-2 rounded-full ${statusColor[agent.status] || "bg-gray-400"}`} />
            )}
            <span className="text-xs font-medium text-gray-600 capitalize">{agent.status.replace(/_/g, " ")}</span>
          </div>
          <p className="text-xs text-gray-400 mt-1 line-clamp-2">{agent.goal}</p>
        </div>

        <div className="flex-1 p-3 space-y-1 overflow-y-auto">
          {tabs.map((t) => (
            <div key={t.key}>
              <button
                className={`w-full text-left px-3 py-2.5 rounded-lg text-sm flex items-center gap-2.5 transition-colors ${
                  tab === t.key
                    ? "bg-blue-100 text-blue-800 font-medium"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
                onClick={() => setTab(t.key)}
              >
                <span className="text-base">{t.icon}</span>
                {t.label}
              </button>
              {/* Inline team member list under Team tab */}
              {t.key === "team" && (
                <div className="ml-6 mt-1 space-y-0.5">
                  <SidebarTeamMember
                    name={`🧑‍💼 ${humanName(agentId)}`}
                    role="Coordinator"
                    status={agent.status === "working" ? "active" : agent.status}
                    model={agent.model}
                  />
                  {workers.map((w) => (
                    <SidebarTeamMember
                      key={w.id}
                      name={humanName(w.id)}
                      role={shortRole(w.role || "Generalist")}
                      status={w.status}
                      model={w.model || undefined}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="p-3 border-t border-gray-200">
          <div className="text-xs text-gray-400 mb-1">Model</div>
          <div className="text-xs text-gray-600 bg-white border border-gray-200 rounded px-2 py-1.5 truncate">
            {agent.model}
          </div>
        </div>
      </div>

      {/* Right Content Area */}
      <div className="flex-1 flex flex-col bg-white min-w-0">
        {tab === "chat" && (
          <EventFlowPanel
            agentId={agentId}
            agentStatus={agent.status}
            conversation={conversation}
            events={events}
            workers={workers}
            teamMembers={teamMembers}
            messageInput={messageInput}
            setMessageInput={setMessageInput}
            sending={sending}
            onSend={handleSend}
            onRespond={handleRespond}
            onStop={handleStop}
            onFileLink={() => setTab("files")}
            chatEndRef={chatEndRef}
          />
        )}
        {tab === "team" && (
          <TeamPanel
            agentId={agentId}
            workers={workers}
            model={agent.model}
            onSelectMember={() => setTab("files")}
          />
        )}
        {tab === "files" && (
          <FilesPanel agentId={agentId} />
        )}
      </div>
    </div>
  );
}

// =============================================================================
// Log entry + grouping
// =============================================================================

interface LogEntry {
  ts: number;
  level: "info" | "human" | "assistant" | "tool" | "result" | "error" | "system" | "warn";
  tag: string;
  source: string; // grouping key: "human", "coordinator", worker name, "system"
  message: string;
  detail?: string;
  files?: { path: string; preview?: string }[]; // file links for node.completed / file.written
}

interface LogGroup {
  source: string;
  level: string;
  entries: LogEntry[];
}

function buildLog(conversation: ConversationMessage[], events: AgentEvent[]): LogEntry[] {
  const entries: LogEntry[] = [];

  for (const msg of conversation) {
    if (msg.role === "human") {
      entries.push({
        ts: msg.ts, level: "human", tag: "HUMAN", source: "human",
        message: msg.content,
      });
    } else {
      entries.push({
        ts: msg.ts, level: "assistant", tag: msg.role.toUpperCase(), source: msg.role,
        message: msg.content,
      });
    }
  }

  for (const ev of events) {
    const d = ev.data;
    if (ev.type === "message.sent" && d.from_id === "human") continue;

    const workerSource = (d.worker as string) || (d.worker_name as string) || "";

    switch (ev.type) {
      case "agent.started":
        entries.push({ ts: ev.ts, level: "system", tag: "AGENT", source: "system", message: `Agent started — goal: ${d.goal || ""}` });
        break;
      case "agent.completed":
        entries.push({ ts: ev.ts, level: "system", tag: "AGENT", source: "system", message: `Agent completed — ${d.summary || "done"}` });
        break;
      case "node.created":
        entries.push({ ts: ev.ts, level: "info", tag: "NODE", source: "coordinator", message: `Created node [${d.node_id}]: ${d.task || ""}` });
        break;
      case "node.assigned":
        entries.push({ ts: ev.ts, level: "info", tag: "NODE", source: "coordinator", message: `Assigned [${d.node_id}] → "${d.worker_name || d.worker_id}"` });
        break;
      case "node.started":
        entries.push({ ts: ev.ts, level: "info", tag: "NODE", source: workerSource || "worker", message: `Node [${d.node_id}] started by "${d.worker_name || d.worker_id}"` });
        break;
      case "node.completed": {
        const pubFiles = Array.isArray(d.published_files) ? (d.published_files as string[]).map((p) => ({ path: p })) : undefined;
        entries.push({
          ts: ev.ts, level: "result", tag: "NODE", source: workerSource || "worker",
          message: `Node [${d.node_id || ""}] completed` + (pubFiles?.length ? ` — ${pubFiles.length} file(s)` : ""),
          detail: d.summary ? String(d.summary) : undefined,
          files: pubFiles,
        });
        break;
      }
      case "node.checkpoint":
        entries.push({ ts: ev.ts, level: "info", tag: "NODE", source: workerSource || "worker", message: `Checkpoint [${d.node_id || ""}]: ${d.summary || ""}` });
        break;
      case "node.failed":
        entries.push({ ts: ev.ts, level: "error", tag: "NODE", source: workerSource || "worker", message: `Node failed: ${d.error || "unknown"}`, detail: JSON.stringify(d, null, 2) });
        break;
      case "worker.spawned":
        entries.push({ ts: ev.ts, level: "info", tag: "WORKER", source: "coordinator", message: `Spawned worker "${d.name || d.worker_id}" (${d.role || d.type || "harnessed"})` });
        break;
      case "worker.launched":
        entries.push({ ts: ev.ts, level: "info", tag: "WORKER", source: "coordinator", message: `Launched autonomous "${d.worker || ""}" — ${d.command || ""}` });
        break;
      case "tool.called":
        entries.push({ ts: ev.ts, level: "tool", tag: workerSource ? `TOOL:${workerSource}` : "TOOL", source: workerSource || "coordinator", message: `${d.tool}(${formatArgs(d.args)})`, detail: d.args ? JSON.stringify(d.args, null, 2) : undefined });
        break;
      case "tool.result":
        entries.push({ ts: ev.ts, level: "result", tag: workerSource ? `RESULT:${workerSource}` : "RESULT", source: workerSource || "coordinator", message: `${d.tool} → ${String(d.result || "").slice(0, 120)}`, detail: d.result ? String(d.result) : undefined });
        break;
      case "tool.error":
        entries.push({ ts: ev.ts, level: "error", tag: "ERROR", source: (d.source as string) || workerSource || "coordinator", message: `Error: ${d.error || d.tool || "unknown"}`, detail: JSON.stringify(d, null, 2) });
        break;
      case "human.question":
        entries.push({ ts: ev.ts, level: "warn", tag: "QUESTION", source: "system", message: String(d.question || "") });
        break;
      case "human.response":
        entries.push({ ts: ev.ts, level: "human", tag: "RESPONSE", source: "human", message: String(d.response || "") });
        break;
      case "message.sent":
        entries.push({ ts: ev.ts, level: "info", tag: "MSG", source: (d.from_id as string) || "system", message: `${d.from_id} → ${d.to_id}: ${String(d.content || "").slice(0, 200)}`, detail: d.content ? String(d.content) : undefined });
        break;
      case "file.written":
        entries.push({
          ts: ev.ts, level: "result", tag: "FILE", source: workerSource || "coordinator",
          message: `Wrote file: ${d.path || ""}`,
          detail: d.preview ? String(d.preview) : undefined,
          files: d.path ? [{ path: String(d.path), preview: d.preview ? String(d.preview) : undefined }] : undefined,
        });
        break;
      case "memory.written":
        entries.push({ ts: ev.ts, level: "info", tag: "MEMORY", source: workerSource || "coordinator", message: `Wrote memory: ${d.path || ""}` });
        break;
      case "trigger.created":
        entries.push({ ts: ev.ts, level: "info", tag: "TRIGGER", source: "coordinator", message: `Created trigger [${d.trigger_id}] type=${d.type}` });
        break;
      case "stage.reconvened":
        entries.push({ ts: ev.ts, level: "system", tag: "STAGE", source: "coordinator", message: `Stage reconvened: ${d.assessment || ""}` });
        break;
      default:
        entries.push({ ts: ev.ts, level: "info", tag: ev.type.toUpperCase(), source: (d.entity as string) || "system", message: JSON.stringify(d) });
        break;
    }
  }

  entries.sort((a, b) => a.ts - b.ts);
  return entries;
}

function groupEntries(entries: LogEntry[]): LogGroup[] {
  const groups: LogGroup[] = [];
  for (const entry of entries) {
    const last = groups[groups.length - 1];
    if (last && last.source === entry.source) {
      last.entries.push(entry);
      // update group level to highest priority
      if (entry.level === "error") last.level = "error";
      else if (entry.level === "human" && last.level !== "error") last.level = "human";
      else if (entry.level === "assistant" && last.level !== "error" && last.level !== "human") last.level = "assistant";
    } else {
      groups.push({ source: entry.source, level: entry.level, entries: [entry] });
    }
  }
  return groups;
}

function formatArgs(args: unknown): string {
  if (!args || typeof args !== "object") return "";
  const entries = Object.entries(args as Record<string, unknown>);
  if (entries.length === 0) return "";
  return entries.map(([k, v]) => `${k}=${String(v).slice(0, 60)}`).join(", ");
}

// =============================================================================
// EventFlowPanel — grouped log view
// =============================================================================

const sourceColors: Record<string, string> = {
  human: "border-l-green-500",
  coordinator: "border-l-indigo-500",
  system: "border-l-yellow-500",
};

function getSourceColor(source: string): string {
  return sourceColors[source] || "border-l-cyan-500";
}

const sourceLabels: Record<string, string> = {
  human: "You",
  coordinator: "Coordinator",
  system: "System",
};

function getSourceLabel(source: string): string {
  return sourceLabels[source] || source;
}

interface TeamMemberOption {
  display: string;
  busName: string;
  role: string;
}

function EventFlowPanel({
  agentId,
  agentStatus,
  conversation,
  events,
  workers,
  teamMembers,
  messageInput,
  setMessageInput,
  sending,
  onSend,
  onRespond,
  onStop,
  onFileLink,
  chatEndRef,
}: {
  agentId: string;
  agentStatus: string;
  conversation: ConversationMessage[];
  events: AgentEvent[];
  workers: WorkerView[];
  teamMembers: TeamMemberOption[];
  messageInput: string;
  setMessageInput: (v: string) => void;
  sending: boolean;
  onSend: () => void;
  onRespond: (r: string) => void;
  onStop: () => void;
  onFileLink: () => void;
  chatEndRef: React.RefObject<HTMLDivElement | null>;
}) {
  const [responseInput, setResponseInput] = useState("");
  const [resultsOnly, setResultsOnly] = useState(false);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionFilter, setMentionFilter] = useState("");
  const [mentionIndex, setMentionIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const log = useMemo(() => buildLog(conversation, events), [conversation, events]);
  const groups = useMemo(() => groupEntries(log), [log]);

  // Build source info map: source key -> { name, role }
  const sourceInfo = useMemo(() => {
    const info: Record<string, { name: string; role: string }> = {
      human: { name: "You", role: "" },
      coordinator: { name: `🧑‍💼 ${humanName(agentId)}`, role: "Coordinator" },
      system: { name: "System", role: "" },
    };
    for (const w of workers) {
      info[w.name] = { name: humanName(w.id), role: shortRole(w.role || "Generalist") };
      info[w.id] = { name: humanName(w.id), role: shortRole(w.role || "Generalist") };
    }
    return info;
  }, [agentId, workers]);

  // Filter groups for results-only mode: only actual text answers and things needing human attention.
  // Hide ALL tool calls, tool results, internal node events, worker lifecycle events.
  const filteredGroups = useMemo(() => {
    if (!resultsOnly) return groups;
    return groups
      .map((g) => ({
        ...g,
        entries: g.entries.filter((e) => {
          if (e.level === "human") return true;           // user messages
          if (e.level === "assistant") return true;       // actual LLM text answers
          if (e.level === "error") return true;           // errors need attention
          if (e.level === "warn") return true;            // questions need attention
          if (e.level === "system") return true;          // agent started/completed banners
          if (e.level === "result" && e.tag === "NODE") return true; // final node results
          return false; // hide tool calls, tool results, info events, etc.
        }),
      }))
      .filter((g) => g.entries.length > 0);
  }, [groups, resultsOnly]);

  // Build compact worker status summary for results-only mode (Claude Code style)
  const workerStatusLines = useMemo(() => {
    if (!resultsOnly) return [];
    return workers.map((w) => {
      const name = humanName(w.id);
      const role = shortRole(w.role || "Generalist");
      const toolCalls = events.filter(
        (e) => e.type === "tool.called" && (e.data.worker === w.name || e.data.worker === w.id)
      ).length;
      const statusLabel = w.status === "busy" ? "working..." : w.status;
      return { name, role, status: w.status, statusLabel, toolCalls };
    });
  }, [resultsOnly, workers, events]);

  const pendingQuestion = events.findLast(
    (e) => e.type === "human.question" && !events.some((r) => r.type === "human.response" && r.ts > e.ts)
  );

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log, chatEndRef]);

  const isRunning = agentStatus === "working" || agentStatus === "busy" || agentStatus === "waiting_for_human";

  // @mention logic: detect @ followed by partial name
  const filteredMembers = useMemo(() => {
    if (!mentionOpen) return [];
    const f = mentionFilter.toLowerCase();
    return teamMembers.filter((m) => m.display.toLowerCase().startsWith(f));
  }, [mentionOpen, mentionFilter, teamMembers]);

  const handleMentionInput = (value: string) => {
    setMessageInput(value);
    // Check if the cursor is after an @ that starts a mention
    const atMatch = value.match(/@(\w*)$/);
    if (atMatch) {
      setMentionOpen(true);
      setMentionFilter(atMatch[1]);
      setMentionIndex(0);
    } else {
      setMentionOpen(false);
    }
  };

  const insertMention = (member: TeamMemberOption) => {
    // Replace @partial with @Name
    const newValue = messageInput.replace(/@\w*$/, `@${member.display} `);
    setMessageInput(newValue);
    setMentionOpen(false);
    textareaRef.current?.focus();
  };

  const handleMentionKeyDown = (e: React.KeyboardEvent) => {
    if (mentionOpen && filteredMembers.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionIndex((i) => Math.min(i + 1, filteredMembers.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
        e.preventDefault();
        insertMention(filteredMembers[mentionIndex]);
        return;
      } else if (e.key === "Escape") {
        setMentionOpen(false);
        return;
      }
    }
    if (!mentionOpen && e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Chat area — goes all the way to the top */}
      <div className="flex-1 overflow-y-auto bg-gray-900 p-2 space-y-1.5">
        {filteredGroups.length === 0 && (
          <div className="text-gray-500 p-4 text-sm">Waiting for events... Send a message to start the agent.</div>
        )}
        {filteredGroups.map((group, gi) => (
          <GroupBlock key={gi} group={group} sourceInfo={sourceInfo} onFileLink={onFileLink} />
        ))}
        {/* Compact worker status lines — visible in results-only mode (Claude Code style) */}
        {workerStatusLines.length > 0 && (
          <div className="px-3 py-2 space-y-0.5">
            {workerStatusLines.map((ws) => (
              <div key={ws.name} className="flex items-center gap-2 text-xs text-gray-400 font-mono">
                {ws.status === "busy" ? (
                  <SpinnerIcon className="w-3 h-3 text-blue-400" />
                ) : (
                  <span className={`w-1.5 h-1.5 rounded-full ${ws.status === "idle" ? "bg-gray-500" : "bg-green-500"}`} />
                )}
                <span className="text-gray-300">{ws.name}</span>
                <span className="text-gray-600">({ws.role})</span>
                <span className="text-gray-500">— {ws.statusLabel}</span>
                {ws.toolCalls > 0 && (
                  <span className="text-gray-600">· {ws.toolCalls} tool calls</span>
                )}
              </div>
            ))}
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Pending question banner */}
      {pendingQuestion && (
        <div className="bg-amber-900/50 border-t border-amber-700 px-4 py-3">
          <div className="text-sm text-amber-200 mb-2">
            Agent asks: {String(pendingQuestion.data.question)}
          </div>
          <div className="flex gap-2">
            <input
              className="flex-1 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
              value={responseInput}
              onChange={(e) => setResponseInput(e.target.value)}
              placeholder="Your response..."
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  onRespond(responseInput);
                  setResponseInput("");
                }
              }}
            />
            <button
              className="bg-amber-600 hover:bg-amber-500 px-3 py-1 rounded text-sm text-white"
              onClick={() => { onRespond(responseInput); setResponseInput(""); }}
            >
              Respond
            </button>
          </div>
        </div>
      )}

      {/* Message input bar */}
      <div className="p-3 border-t border-gray-200 bg-gray-50 relative">
        {/* @mention dropdown */}
        {mentionOpen && filteredMembers.length > 0 && (
          <div className="absolute bottom-full left-12 mb-1 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-20 min-w-48">
            {filteredMembers.map((m, i) => (
              <button
                key={m.busName}
                className={`w-full text-left px-3 py-1.5 text-sm flex items-center gap-2 ${
                  i === mentionIndex ? "bg-blue-50 text-blue-700" : "text-gray-700 hover:bg-gray-50"
                }`}
                onMouseDown={(e) => { e.preventDefault(); insertMention(m); }}
                onMouseEnter={() => setMentionIndex(i)}
              >
                <span className="font-medium">@{m.display}</span>
                <span className="text-xs text-gray-400">{m.role}</span>
              </button>
            ))}
          </div>
        )}
        <div className="flex gap-2 items-center">
          {/* Verbose toggle (cog icon) */}
          <button
            className={`p-2 rounded-lg border transition-colors shrink-0 ${
              resultsOnly
                ? "bg-gray-200 text-gray-500 border-gray-300"
                : "bg-blue-100 text-blue-600 border-blue-300"
            }`}
            onClick={() => setResultsOnly(!resultsOnly)}
            title={resultsOnly ? "Showing results only — click for all events" : "Showing all events — click for results only"}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
          <textarea
            ref={textareaRef}
            className="flex-1 bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400 placeholder-gray-400 resize-none"
            rows={1}
            value={messageInput}
            onChange={(e) => handleMentionInput(e.target.value)}
            placeholder="Send a message... (type @ to mention)"
            onKeyDown={handleMentionKeyDown}
            onBlur={() => setTimeout(() => setMentionOpen(false), 150)}
          />
          <button
            className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm text-white disabled:opacity-50 shrink-0"
            onClick={onSend}
            disabled={sending || !messageInput.trim()}
          >
            Send
          </button>
          {/* Stop button — only visible when agent is running */}
          {isRunning && (
            <button
              className="bg-red-600 hover:bg-red-700 px-3 py-2 rounded-lg text-sm text-white shrink-0"
              onClick={onStop}
              title="Stop agent — kills all workers, keeps outputs"
            >
              Stop
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// GroupBlock — a group of log entries from same source
// =============================================================================

function GroupBlock({ group, sourceInfo, onFileLink }: { group: LogGroup; sourceInfo: Record<string, { name: string; role: string }>; onFileLink: () => void }) {
  const borderColor = getSourceColor(group.source);
  const info = sourceInfo[group.source];
  const label = info ? (info.role ? `${info.name} (${info.role})` : info.name) : getSourceLabel(group.source);
  const firstTs = group.entries[0].ts;
  const time = new Date(firstTs * 1000).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const isError = group.level === "error";
  // Lighter background for assistant/human/result groups (the "real" content)
  const isResultContent = group.level === "assistant" || group.level === "human" || group.level === "result";
  const bgClass = isError
    ? "bg-red-950/20"
    : isResultContent
      ? "bg-gray-700/60"
      : "bg-gray-800/50";

  return (
    <div className={`border-l-2 ${borderColor} ${bgClass} rounded-r`}>
      {/* Group header */}
      <div className="flex items-center gap-2 px-3 py-1 text-[10px]">
        <span className="font-semibold text-gray-400 uppercase">{label}</span>
        <span className="text-gray-600">{time}</span>
        {group.entries.length > 1 && (
          <span className="text-gray-600">({group.entries.length} events)</span>
        )}
      </div>
      {/* Entries */}
      <div className={`text-xs leading-relaxed ${isResultContent ? "font-sans" : "font-mono"}`}>
        {group.entries.map((entry, i) => (
          <LogLine key={`${entry.ts}-${i}`} entry={entry} onFileLink={onFileLink} />
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// LogLine — single log entry
// =============================================================================

const levelColors: Record<string, string> = {
  info: "text-blue-400",
  human: "text-green-400",
  assistant: "text-purple-300",
  tool: "text-cyan-400",
  result: "text-gray-400",
  error: "text-red-400",
  system: "text-yellow-400",
  warn: "text-amber-400",
};

const tagBg: Record<string, string> = {
  info: "bg-blue-900/40 text-blue-300",
  human: "bg-green-900/40 text-green-300",
  assistant: "bg-purple-900/40 text-purple-300",
  tool: "bg-cyan-900/40 text-cyan-300",
  result: "bg-gray-800 text-gray-400",
  error: "bg-red-900/60 text-red-300",
  system: "bg-yellow-900/40 text-yellow-300",
  warn: "bg-amber-900/40 text-amber-300",
};

function LogLine({ entry, onFileLink }: { entry: LogEntry; onFileLink: () => void }) {
  // Auto-expand tool results so users always see what happened
  const autoExpand = entry.level === "result" || entry.level === "error";
  const [expanded, setExpanded] = useState(autoExpand);
  const time = new Date(entry.ts * 1000).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const hasDetail = entry.detail && entry.detail.length > 0;
  const hasFiles = entry.files && entry.files.length > 0;
  const isAssistant = entry.level === "assistant";
  const isHuman = entry.level === "human";

  return (
    <div className="px-3 py-0.5 hover:bg-gray-800/50">
      <div className="flex items-start gap-2">
        <span className="text-gray-600 shrink-0 select-none">{time}</span>
        <span className={`px-1.5 py-0 rounded text-[10px] font-semibold uppercase shrink-0 ${tagBg[entry.level] || "bg-gray-800 text-gray-400"}`}>
          {entry.tag}
        </span>
        {isAssistant ? (
          <div className="flex-1 min-w-0 text-purple-200 font-sans prose prose-invert prose-sm max-w-none [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0 [&_pre]:bg-gray-950 [&_pre]:p-2 [&_pre]:rounded [&_pre]:font-mono [&_code]:text-pink-300 [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-xs">
            <ReactMarkdown>{entry.message}</ReactMarkdown>
          </div>
        ) : isHuman ? (
          <span className="flex-1 min-w-0 text-green-400 font-sans whitespace-pre-wrap">
            {entry.message}
          </span>
        ) : (
          <span className={`flex-1 min-w-0 ${levelColors[entry.level] || "text-gray-300"}`}>
            {entry.message}
          </span>
        )}
        {(hasDetail || hasFiles) && (
          <button
            className="text-gray-600 hover:text-gray-400 shrink-0 text-[10px]"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "[-]" : "[+]"}
          </button>
        )}
      </div>
      {/* File links */}
      {hasFiles && (
        <div className="ml-16 mt-1 space-y-1">
          {entry.files!.map((f, fi) => (
            <div key={fi}>
              <button
                className="text-blue-400 hover:text-blue-300 text-xs underline flex items-center gap-1"
                onClick={onFileLink}
              >
                <span>📄</span>
                <span>{f.path}</span>
                <span className="text-gray-600 no-underline ml-1">→ Files tab</span>
              </button>
              {/* Inline content preview */}
              {expanded && f.preview && (
                <pre className="mt-1 text-[11px] text-gray-400 whitespace-pre-wrap break-all border-l-2 border-gray-700 pl-2 max-h-64 overflow-y-auto bg-gray-950/50 rounded-r p-2">
                  {f.preview}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
      {expanded && hasDetail && (
        <pre className="mt-1 ml-16 text-[11px] text-gray-500 whitespace-pre-wrap break-all border-l-2 border-gray-700 pl-2 max-h-96 overflow-y-auto">
          {entry.detail}
        </pre>
      )}
    </div>
  );
}

// =============================================================================
// TeamPanel (Tab 2) — coordinator + workers with human names
// =============================================================================

interface TeamMember {
  id: string;
  name: string;
  humanLabel: string;
  type: string;
  role: string;
  model: string | null;
  status: string;
  capabilities: string[];
}

function TeamPanel({
  agentId,
  workers,
  model,
  onSelectMember,
}: {
  agentId: string;
  workers: WorkerView[];
  model: string;
  onSelectMember: (memberId: string) => void;
}) {
  // Build team: coordinator + all workers
  const team: TeamMember[] = useMemo(() => {
    const coordinator: TeamMember = {
      id: "coordinator",
      name: "coordinator",
      humanLabel: `🧑‍💼 ${humanName(agentId)}`,
      type: "coordinator",
      role: "Coordinator",
      model: model,
      status: "active",
      capabilities: ["planning", "delegation", "tool-use"],
    };
    const workerMembers: TeamMember[] = workers.map((w) => ({
      id: w.id,
      name: w.name,
      humanLabel: humanName(w.id),
      type: w.type,
      role: shortRole(w.role || "Generalist"),
      model: w.model,
      status: w.status,
      capabilities: w.capabilities,
    }));
    return [coordinator, ...workerMembers];
  }, [agentId, workers, model]);

  const statusDot: Record<string, string> = {
    active: "bg-blue-500 animate-pulse",
    idle: "bg-gray-400",
    busy: "bg-blue-500 animate-pulse",
    completed: "bg-green-500",
    failed: "bg-red-500",
  };

  const typeBadge: Record<string, string> = {
    coordinator: "bg-indigo-100 text-indigo-700",
    harnessed: "bg-cyan-100 text-cyan-700",
    autonomous: "bg-amber-100 text-amber-700",
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-gray-200 text-sm font-medium text-gray-700">
        Team ({team.length} members)
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {team.map((m) => (
          <div
            key={m.id}
            className="border border-gray-200 rounded-lg p-4 cursor-pointer hover:border-blue-200 hover:shadow-sm transition-all"
            onClick={() => onSelectMember(m.id)}
          >
            <div className="flex items-start gap-3">
              <span className={`mt-1 w-2.5 h-2.5 rounded-full shrink-0 ${statusDot[m.status] || "bg-gray-400"}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-semibold text-gray-900">{m.humanLabel}</span>
                  <span className={`text-[10px] rounded px-1.5 py-0.5 font-medium ${typeBadge[m.type] || "bg-gray-100 text-gray-600"}`}>
                    {m.role}
                  </span>
                  <span className="text-xs text-gray-400 capitalize">{m.status}</span>
                </div>
                {m.model && (
                  <div className="text-xs text-gray-400">Model: {m.model}</div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// FilesPanel (Tab 3) — auto-expanded recursive tree
// =============================================================================

type FileSubTab = "workspace" | "memory";

interface TreeNode {
  name: string;
  path: string;
  type: "file" | "dir";
  size?: number;
  children?: TreeNode[];
}

function FilesPanel({ agentId }: { agentId: string }) {
  const [subTab, setSubTab] = useState<FileSubTab>("workspace");
  const [workspaceTree, setWorkspaceTree] = useState<TreeNode[] | null>(null);
  const [memoryTree, setMemoryTree] = useState<TreeNode[] | null>(null);
  const [selectedFile, setSelectedFile] = useState<{ path: string; content: string } | null>(null);
  const [loadingFile, setLoadingFile] = useState(false);

  const fetchFn = subTab === "workspace" ? getWorkspace : getMemory;

  const buildTree = useCallback(async (
    fetcher: (id: string, path: string) => Promise<WorkspaceResult>,
    basePath: string,
  ): Promise<TreeNode[]> => {
    try {
      const result = await fetcher(agentId, basePath);
      if (result.type !== "dir" || !result.entries) return [];
      const nodes: TreeNode[] = [];
      for (const entry of result.entries) {
        const childPath = basePath ? `${basePath}/${entry.name}` : entry.name;
        const node: TreeNode = { name: entry.name, path: childPath, type: entry.type, size: entry.size };
        if (entry.type === "dir") {
          node.children = await buildTree(fetcher, childPath);
        }
        nodes.push(node);
      }
      return nodes;
    } catch {
      return [];
    }
  }, [agentId]);

  useEffect(() => {
    buildTree(getWorkspace, "").then(setWorkspaceTree);
    buildTree(getMemory, "").then(setMemoryTree);
  }, [agentId, buildTree]);

  const handleFileClick = async (path: string) => {
    setLoadingFile(true);
    try {
      const result = await fetchFn(agentId, path);
      if (result.type === "file") {
        setSelectedFile({ path, content: result.content || "" });
      }
    } catch {
      setSelectedFile({ path, content: "(failed to load)" });
    }
    setLoadingFile(false);
  };

  const tree = subTab === "workspace" ? workspaceTree : memoryTree;

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-gray-200 flex items-center gap-4">
        <button
          className={`text-sm font-medium pb-0.5 ${subTab === "workspace" ? "text-blue-600 border-b-2 border-blue-600" : "text-gray-500 hover:text-gray-700"}`}
          onClick={() => { setSubTab("workspace"); setSelectedFile(null); }}
        >
          Workspace Files
        </button>
        <button
          className={`text-sm font-medium pb-0.5 ${subTab === "memory" ? "text-blue-600 border-b-2 border-blue-600" : "text-gray-500 hover:text-gray-700"}`}
          onClick={() => { setSubTab("memory"); setSelectedFile(null); }}
        >
          Agent Memory
        </button>
      </div>

      <div className="flex-1 flex min-h-0">
        <div className="w-64 border-r border-gray-200 overflow-y-auto p-2 shrink-0">
          {tree === null ? (
            <p className="text-gray-400 text-xs p-2">Loading...</p>
          ) : tree.length === 0 ? (
            <p className="text-gray-400 text-xs p-2">(empty)</p>
          ) : (
            tree.map((node) => (
              <FileTreeNode key={node.path} node={node} depth={0} onFileClick={handleFileClick} selectedPath={selectedFile?.path || null} />
            ))
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-4 min-w-0">
          {loadingFile ? (
            <p className="text-gray-400 text-sm">Loading file...</p>
          ) : selectedFile ? (
            <div>
              <div className="text-xs text-gray-500 mb-2 font-mono">{selectedFile.path}</div>
              <pre className="text-sm text-gray-700 whitespace-pre-wrap font-mono bg-slate-50 border border-gray-200 rounded-lg p-4 overflow-x-auto">
                {selectedFile.content}
              </pre>
            </div>
          ) : (
            <p className="text-gray-400 text-sm">Select a file to view its contents.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function FileTreeNode({ node, depth, onFileClick, selectedPath }: {
  node: TreeNode; depth: number; onFileClick: (path: string) => void; selectedPath: string | null;
}) {
  const isSelected = node.path === selectedPath;
  const isDir = node.type === "dir";
  const indent = depth * 16;

  return (
    <div>
      <button
        className={`w-full text-left py-1 px-2 rounded text-xs flex items-center gap-1.5 ${
          isSelected ? "bg-blue-100 text-blue-800" : "text-gray-700 hover:bg-gray-100"
        }`}
        style={{ paddingLeft: `${indent + 8}px` }}
        onClick={() => { if (!isDir) onFileClick(node.path); }}
      >
        <span className="text-gray-400 shrink-0">{isDir ? "📂" : "📄"}</span>
        <span className="truncate">{node.name}</span>
        {node.size != null && <span className="ml-auto text-gray-400 shrink-0">{node.size}B</span>}
      </button>
      {isDir && node.children && node.children.map((child) => (
        <FileTreeNode key={child.path} node={child} depth={depth + 1} onFileClick={onFileClick} selectedPath={selectedPath} />
      ))}
    </div>
  );
}
