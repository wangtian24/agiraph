"use client";

import { use, useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useAgent } from "@/hooks/useAgent";
import {
  sendMessage,
  respondToQuestion,
  getWorkspace,
  getMemory,
  WorkspaceResult,
  NodeView,
  WorkerView,
  ConversationMessage,
  AgentEvent,
} from "@/lib/api";

type Tab = "chat" | "board" | "files" | "memory" | "events";
type EntitySelection = { type: "coordinator" } | { type: "worker"; id: string; name: string };

export default function AgentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: agentId } = use(params);
  const { agent, board, workers, conversation, events, loading } = useAgent(agentId);
  const [tab, setTab] = useState<Tab>("chat");
  const [selectedEntity, setSelectedEntity] = useState<EntitySelection>({ type: "coordinator" });
  const [messageInput, setMessageInput] = useState("");
  const [sending, setSending] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // File browser state
  const [filePath, setFilePath] = useState("");
  const [fileContent, setFileContent] = useState<WorkspaceResult | null>(null);
  const [memoryPath, setMemoryPath] = useState("");
  const [memoryContent, setMemoryContent] = useState<WorkspaceResult | null>(null);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation]);

  const handleSend = async () => {
    if (!messageInput.trim()) return;
    setSending(true);
    try {
      const to =
        selectedEntity.type === "worker" ? selectedEntity.name : "coordinator";
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

  const loadFiles = async (path: string) => {
    setFilePath(path);
    try {
      setFileContent(await getWorkspace(agentId, path));
    } catch {
      setFileContent(null);
    }
  };

  const loadMemory = async (path: string) => {
    setMemoryPath(path);
    try {
      setMemoryContent(await getMemory(agentId, path));
    } catch {
      setMemoryContent(null);
    }
  };

  useEffect(() => {
    if (tab === "files") loadFiles("");
    if (tab === "memory") loadMemory("");
  }, [tab]);

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

  const hasQuestion = events.some(
    (e) => e.type === "human.question" && !events.some((r) => r.type === "human.response" && r.ts > e.ts)
  );

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <div className="w-64 bg-slate-50 border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-200">
          <Link href="/" className="text-blue-500 text-xs hover:text-blue-700">
            &larr; All Agents
          </Link>
          <div className="mt-2 flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${statusColor[agent.status] || "bg-gray-400"}`} />
            <span className="text-sm font-medium text-gray-700">{agent.status}</span>
          </div>
          <p className="text-xs text-gray-500 mt-1 line-clamp-2">{agent.goal}</p>
        </div>

        {/* Entity List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          <button
            className={`w-full text-left px-3 py-2 rounded text-sm flex items-center gap-2 ${
              selectedEntity.type === "coordinator" && tab === "chat"
                ? "bg-blue-100 text-blue-800"
                : "text-gray-600 hover:bg-gray-100"
            }`}
            onClick={() => {
              setSelectedEntity({ type: "coordinator" });
              setTab("chat");
            }}
          >
            <span className="text-amber-500">&#9733;</span>
            Coordinator
            {hasQuestion && <span className="ml-auto w-2 h-2 rounded-full bg-yellow-500" />}
          </button>

          {workers.map((w) => (
            <button
              key={w.id}
              className={`w-full text-left px-3 py-2 rounded text-sm flex items-center gap-2 ${
                selectedEntity.type === "worker" && selectedEntity.id === w.id && tab === "chat"
                  ? "bg-blue-100 text-blue-800"
                  : "text-gray-600 hover:bg-gray-100"
              }`}
              onClick={() => {
                setSelectedEntity({ type: "worker", id: w.id, name: w.name });
                setTab("chat");
              }}
            >
              <span className={`w-2 h-2 rounded-full ${statusColor[w.status] || "bg-gray-400"}`} />
              {w.name}
              <span className="ml-auto text-xs text-gray-400">{w.type === "autonomous" ? "auto" : ""}</span>
            </button>
          ))}

          <div className="border-t border-gray-200 my-2" />

          {/* Tab buttons */}
          {(["board", "files", "memory", "events"] as Tab[]).map((t) => (
            <button
              key={t}
              className={`w-full text-left px-3 py-2 rounded text-sm ${
                tab === t ? "bg-blue-100 text-blue-800" : "text-gray-600 hover:bg-gray-100"
              }`}
              onClick={() => setTab(t)}
            >
              {t === "board" && "Work Board"}
              {t === "files" && "Files"}
              {t === "memory" && "Memory"}
              {t === "events" && "Events"}
            </button>
          ))}
        </div>
      </div>

      {/* Main Panel */}
      <div className="flex-1 flex flex-col bg-white">
        {tab === "chat" && (
          <ChatPanel
            conversation={conversation}
            events={events}
            selectedEntity={selectedEntity}
            messageInput={messageInput}
            setMessageInput={setMessageInput}
            sending={sending}
            onSend={handleSend}
            onRespond={handleRespond}
            chatEndRef={chatEndRef}
          />
        )}
        {tab === "board" && <BoardPanel nodes={board?.nodes || []} workers={workers} />}
        {tab === "files" && (
          <FileBrowserPanel
            content={fileContent}
            path={filePath}
            onNavigate={loadFiles}
            title="Workspace"
          />
        )}
        {tab === "memory" && (
          <FileBrowserPanel
            content={memoryContent}
            path={memoryPath}
            onNavigate={loadMemory}
            title="Memory"
          />
        )}
        {tab === "events" && <EventsPanel events={events} />}
      </div>
    </div>
  );
}

// --- Chat Panel ---
function ChatPanel({
  conversation,
  events,
  selectedEntity,
  messageInput,
  setMessageInput,
  sending,
  onSend,
  onRespond,
  chatEndRef,
}: {
  conversation: ConversationMessage[];
  events: AgentEvent[];
  selectedEntity: EntitySelection;
  messageInput: string;
  setMessageInput: (v: string) => void;
  sending: boolean;
  onSend: () => void;
  onRespond: (r: string) => void;
  chatEndRef: React.RefObject<HTMLDivElement | null>;
}) {
  const [responseInput, setResponseInput] = useState("");

  const pendingQuestion = events.findLast(
    (e) => e.type === "human.question" && !events.some((r) => r.type === "human.response" && r.ts > e.ts)
  );

  const entityName =
    selectedEntity.type === "coordinator" ? "Coordinator" : selectedEntity.name;

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 text-sm font-medium text-gray-700">
        Chat with {entityName}
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50">
        {conversation.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "human" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                msg.role === "human"
                  ? "bg-blue-500 text-white"
                  : "bg-white border border-gray-200 text-gray-800"
              }`}
            >
              {msg.role !== "human" && (
                <div className="text-xs text-gray-400 mb-1">{msg.role}</div>
              )}
              <div className="whitespace-pre-wrap">{msg.content}</div>
              <div className={`text-xs mt-1 ${msg.role === "human" ? "text-blue-200" : "text-gray-400"}`}>
                {new Date(msg.ts * 1000).toLocaleTimeString()}
              </div>
            </div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Pending question banner */}
      {pendingQuestion && (
        <div className="mx-4 mb-2 bg-amber-50 border border-amber-200 rounded-lg p-3">
          <div className="text-sm text-amber-800 mb-2">
            Agent is asking: {String(pendingQuestion.data.question)}
          </div>
          <div className="flex gap-2">
            <input
              className="flex-1 bg-white border border-gray-300 rounded px-2 py-1 text-sm text-gray-800"
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
              className="bg-amber-500 hover:bg-amber-600 px-3 py-1 rounded text-sm text-white"
              onClick={() => {
                onRespond(responseInput);
                setResponseInput("");
              }}
            >
              Respond
            </button>
          </div>
        </div>
      )}

      {/* Message input */}
      <div className="p-4 border-t border-gray-200">
        <div className="flex gap-2">
          <input
            className="flex-1 bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400 placeholder-gray-400"
            value={messageInput}
            onChange={(e) => setMessageInput(e.target.value)}
            placeholder={`Message ${entityName}...`}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
          />
          <button
            className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm text-white disabled:opacity-50"
            onClick={onSend}
            disabled={sending || !messageInput.trim()}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

// --- Board Panel ---
function BoardPanel({ nodes, workers }: { nodes: NodeView[]; workers: WorkerView[] }) {
  const workerMap = Object.fromEntries(workers.map((w) => [w.id, w]));

  const statusIcon: Record<string, string> = {
    pending: "○",
    assigned: "◐",
    running: "●",
    completed: "✓",
    failed: "✗",
  };

  const statusClass: Record<string, string> = {
    pending: "text-gray-400",
    assigned: "text-blue-500",
    running: "text-blue-500 animate-pulse",
    completed: "text-green-500",
    failed: "text-red-500",
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 text-sm font-medium text-gray-700">
        Work Board ({nodes.length} nodes)
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {nodes.length === 0 ? (
          <p className="text-gray-400 text-center py-8">No work nodes yet.</p>
        ) : (
          <div className="space-y-2">
            {nodes.map((node) => (
              <div key={node.id} className="bg-white border border-gray-200 rounded-lg p-3">
                <div className="flex items-start gap-2">
                  <span className={`text-lg ${statusClass[node.status] || "text-gray-400"}`}>
                    {statusIcon[node.status] || "?"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400 font-mono">{node.id}</span>
                      {node.assigned_worker && (
                        <span className="text-xs text-blue-500">
                          {workerMap[node.assigned_worker]?.name || node.assigned_worker}
                        </span>
                      )}
                    </div>
                    <p className="text-sm mt-1 text-gray-700 line-clamp-2">{node.task}</p>
                    {node.result && (
                      <p className="text-xs text-gray-400 mt-1 line-clamp-2">{node.result}</p>
                    )}
                    {node.children.length > 0 && (
                      <div className="text-xs text-gray-400 mt-1">
                        Children: {node.children.join(", ")}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// --- File Browser Panel ---
function FileBrowserPanel({
  content,
  path,
  onNavigate,
  title,
}: {
  content: WorkspaceResult | null;
  path: string;
  onNavigate: (path: string) => void;
  title: string;
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 text-sm font-medium text-gray-700 flex items-center gap-2">
        {title}
        {path && (
          <>
            <span className="text-gray-300">/</span>
            <button className="text-blue-500 hover:text-blue-700" onClick={() => onNavigate("")}>
              root
            </button>
            {path.split("/").map((part, i, arr) => (
              <span key={i}>
                <span className="text-gray-300">/</span>
                <button
                  className="text-blue-500 hover:text-blue-700"
                  onClick={() => onNavigate(arr.slice(0, i + 1).join("/"))}
                >
                  {part}
                </button>
              </span>
            ))}
          </>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {!content ? (
          <p className="text-gray-400">Loading...</p>
        ) : content.type === "dir" ? (
          <div className="space-y-1">
            {content.entries?.map((entry) => (
              <button
                key={entry.name}
                className="w-full text-left px-3 py-2 rounded text-sm text-gray-700 hover:bg-blue-50 flex items-center gap-2"
                onClick={() => onNavigate(path ? `${path}/${entry.name}` : entry.name)}
              >
                <span>{entry.type === "dir" ? "📁" : "📄"}</span>
                <span>{entry.name}</span>
                {entry.size != null && <span className="ml-auto text-xs text-gray-400">{entry.size}B</span>}
              </button>
            ))}
            {(!content.entries || content.entries.length === 0) && (
              <p className="text-gray-400 text-sm">(empty)</p>
            )}
          </div>
        ) : (
          <pre className="text-sm text-gray-700 whitespace-pre-wrap font-mono bg-slate-50 border border-gray-200 rounded-lg p-4 overflow-x-auto">
            {content.content}
          </pre>
        )}
      </div>
    </div>
  );
}

// --- Events Panel ---
function EventsPanel({ events }: { events: AgentEvent[] }) {
  const reversed = [...events].reverse();
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 text-sm font-medium text-gray-700">
        Events ({events.length})
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-1">
        {reversed.map((e, i) => (
          <div key={i} className="text-xs font-mono flex gap-2 py-1">
            <span className="text-gray-400 w-20 shrink-0">
              {new Date(e.ts * 1000).toLocaleTimeString()}
            </span>
            <span className="text-blue-600 w-32 shrink-0">{e.type}</span>
            <span className="text-gray-500 truncate">
              {Object.entries(e.data)
                .map(([k, v]) => `${k}=${String(v).substring(0, 60)}`)
                .join(" ")}
            </span>
          </div>
        ))}
        {events.length === 0 && <p className="text-gray-400 text-sm">No events yet.</p>}
      </div>
    </div>
  );
}
