"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AgentSummary, createAgent, listAgents, deleteAgent } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [goal, setGoal] = useState("");
  const [model, setModel] = useState("anthropic/claude-sonnet-4-5");
  const [mode, setMode] = useState("finite");
  const [creating, setCreating] = useState(false);

  const refresh = async () => {
    try {
      setAgents(await listAgents());
    } catch {}
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleCreate = async () => {
    if (!goal.trim()) return;
    setCreating(true);
    try {
      const agent = await createAgent(goal, model, mode);
      setGoal("");
      router.push(`/agents/${agent.id}`);
    } catch (err) {
      alert(`Failed to create agent: ${err}`);
    }
    setCreating(false);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this agent?")) return;
    try {
      await deleteAgent(id);
      refresh();
    } catch {}
  };

  const statusColor: Record<string, string> = {
    idle: "bg-gray-400",
    working: "bg-blue-500 animate-pulse",
    waiting_for_human: "bg-yellow-500",
    completed: "bg-green-500",
    paused: "bg-orange-400",
  };

  return (
    <div className="max-w-4xl mx-auto py-12 px-4">
      <h1 className="text-3xl font-bold mb-2 text-gray-900">Agiraph</h1>
      <p className="text-gray-500 mb-8">Autonomous AI Agent Framework</p>

      {/* Create Agent */}
      <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-6 mb-8">
        <h2 className="text-lg font-semibold mb-4 text-gray-800">New Agent</h2>
        <textarea
          className="w-full bg-white border border-gray-300 rounded-lg p-3 text-sm mb-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-400 text-gray-800 placeholder-gray-400"
          rows={3}
          placeholder="What's the goal? e.g. 'Research the competitive landscape of AI hardware companies'"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && e.metaKey) handleCreate();
          }}
        />
        <div className="flex gap-3 items-center">
          <select
            className="bg-white border border-gray-300 rounded px-3 py-2 text-sm text-gray-700"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            <option value="anthropic/claude-sonnet-4-5">Claude Sonnet 4.5</option>
            <option value="anthropic/claude-opus-4-6">Claude Opus 4.6</option>
            <option value="anthropic/claude-haiku-4-5">Claude Haiku 4.5</option>
            <option value="openai/gpt-4o">GPT-4o</option>
            <option value="openai/o3-mini">o3-mini</option>
          </select>
          <select
            className="bg-white border border-gray-300 rounded px-3 py-2 text-sm text-gray-700"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="finite">Finite (bounded task)</option>
            <option value="infinite">Infinite (ongoing)</option>
          </select>
          <button
            className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm font-medium text-white disabled:opacity-50"
            onClick={handleCreate}
            disabled={creating || !goal.trim()}
          >
            {creating ? "Creating..." : "Create Agent"}
          </button>
        </div>
      </div>

      {/* Agent List */}
      <div className="space-y-3">
        {agents.length === 0 && (
          <p className="text-gray-400 text-center py-8">No agents yet. Create one above.</p>
        )}
        {agents.map((a) => (
          <div
            key={a.id}
            className="bg-white border border-gray-200 rounded-lg p-4 hover:border-blue-300 hover:shadow-sm cursor-pointer transition-all"
            onClick={() => router.push(`/agents/${a.id}`)}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`w-2 h-2 rounded-full ${statusColor[a.status] || "bg-gray-400"}`} />
                  <span className="text-sm font-medium text-gray-600">{a.status}</span>
                  <span className="text-xs text-gray-400">{a.mode}</span>
                  <span className="text-xs text-gray-300">{a.id}</span>
                </div>
                <p className="text-sm text-gray-800">{a.goal}</p>
                <div className="flex gap-4 mt-2 text-xs text-gray-400">
                  <span>{a.node_count} nodes</span>
                  <span>{a.worker_count} workers</span>
                  <span>{a.model}</span>
                </div>
              </div>
              <button
                className="text-gray-300 hover:text-red-500 text-sm px-2"
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(a.id);
                }}
              >
                &times;
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
