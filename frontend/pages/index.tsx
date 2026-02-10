import { useState, useEffect, useRef } from 'react';
import Head from 'next/head';
import ReactFlow, { Node, Edge } from 'reactflow';
import 'reactflow/dist/style.css';
import ReactMarkdown from 'react-markdown';
import axios from 'axios';

interface Provider {
  name: string;
  default_model: string;
  models: string[];
}

interface Plan {
  plan_id: string;
  user_prompt: string;
  title?: string;
  nodes: Array<{
    id: string;
    name: string;
    description: string;
    provider: string;
    model: string;
    input_description?: string;
    output_description?: string;
    dependencies: string[];
    status: string;
  }>;
  edges: Array<{ from: string; to: string }>;
  status: string;
}

interface NodeResult {
  node_id: string;
  name: string;
  status: string;
  result?: string;
  error?: string;
  execution_time?: number;
}

interface ExecutionResult {
  execution_id: string;
  plan_id: string;
  status: string;
  node_results: NodeResult[];
  execution_logs: string[];
  started_at: string;
  completed_at?: string;
}

const DEFAULT_PROVIDERS: Provider[] = [
  { name: 'openai', default_model: 'gpt-4.1', models: ['gpt-4.1', 'gpt-4.1-mini', 'gpt-4.1-nano', 'gpt-4o', 'gpt-4o-mini', 'o3', 'o3-mini', 'o4-mini', 'o1'] },
  { name: 'anthropic', default_model: 'claude-sonnet-4-5', models: ['claude-opus-4-6', 'claude-sonnet-4-5', 'claude-haiku-4-5', 'claude-sonnet-4-0', 'claude-opus-4-0', 'claude-3-7-sonnet-latest'] },
  { name: 'gemini', default_model: 'gemini-3-flash-preview', models: ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-pro'] },
  { name: 'minimax', default_model: 'MiniMax-M2.1', models: ['MiniMax-M2.1', 'MiniMax-M2.1-lightning', 'MiniMax-M2'] },
  { name: 'openrouter', default_model: 'openai/gpt-4.1', models: ['openai/gpt-4.1', 'openai/gpt-4.1-mini', 'anthropic/claude-sonnet-4-5', 'google/gemini-2.5-pro-preview', 'deepseek/deepseek-r1'] },
];

export default function Home() {
  const [prompt, setPrompt] = useState('');
  const [provider, setProvider] = useState(DEFAULT_PROVIDERS[0].name);
  const [model, setModel] = useState(DEFAULT_PROVIDERS[0].default_model);
  const [availableProviders, setAvailableProviders] = useState<Provider[]>(DEFAULT_PROVIDERS);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [executionStatus, setExecutionStatus] = useState<any>(null);
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [savedExecutions, setSavedExecutions] = useState<any[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'new' | 'past'>('new');
  const [viewingExecutionId, setViewingExecutionId] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Load available providers from backend (updates defaults if backend is running)
  useEffect(() => {
    axios.get('/api/providers')
      .then(response => {
        const modelLists = response.data.models || {};
        const defaultModels = response.data.default_models || {};

        const allProviderNames = Object.keys(modelLists);
        if (allProviderNames.length === 0) return;

        const providers: Provider[] = allProviderNames.map((p: string) => ({
          name: p,
          default_model: defaultModels[p] || (modelLists[p] && modelLists[p][0]) || '',
          models: modelLists[p] || [defaultModels[p] || ''],
        }));
        setAvailableProviders(providers);
        setProvider(providers[0].name);
        setModel(providers[0].default_model);
      })
      .catch(() => {
        // Keep defaults - already set in initial state
      });
  }, []);

  // Load saved executions
  useEffect(() => {
    loadSavedExecutions();
  }, []);

  // Connect WebSocket
  useEffect(() => {
    if (executionId && !wsRef.current) {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host.replace(':3000', ':8000')}/ws/${executionId}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        setExecutionStatus(data);
        if (data.logs) {
          setLogs(data.logs);
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
      };
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [executionId]);

  const loadSavedExecutions = async () => {
    try {
      const response = await axios.get('/api/executions');
      setSavedExecutions(response.data.executions || []);
    } catch (error) {
      console.error('Failed to load executions:', error);
    }
  };

  const createPlan = async () => {
    if (!prompt.trim() || !provider || !model) {
      alert('Please fill in all fields');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post('/api/plan', { prompt, provider, model });
      setPlan(response.data);
      setExecutionId(null);
      setExecutionStatus(null);
      setExecutionResult(null);
      setLogs([]);
      setViewingExecutionId(null); // Clear past execution view when creating new plan
      // Select last node by default
      if (response.data.nodes && response.data.nodes.length > 0) {
        setSelectedNodeId(response.data.nodes[response.data.nodes.length - 1].id);
      }
    } catch (error: any) {
      alert(`Error: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const executePlan = async () => {
    if (!plan) return;

    setLoading(true);
    try {
      const execResponse = await axios.post('/api/execute', {
        plan_id: plan.plan_id,
      });

      const execData = execResponse.data;
      setExecutionId(execData.execution_id);

      await axios.post(`/api/execute/${execData.execution_id}/start`);

      const pollInterval = setInterval(async () => {
        try {
          const statusResponse = await axios.get(`/api/execution/${execData.execution_id}/status`);
          const status = statusResponse.data;
          setExecutionStatus(status);

          if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(pollInterval);
            const resultResponse = await axios.get(`/api/execution/${execData.execution_id}/result`);
            setExecutionResult(resultResponse.data);
            setLoading(false);
            loadSavedExecutions();
          }
        } catch (e) {
          console.error('Polling error:', e);
        }
      }, 1000);
    } catch (error: any) {
      alert(`Error: ${error.response?.data?.detail || error.message}`);
      setLoading(false);
    }
  };

  const loadExecution = async (executionId: string) => {
    try {
      const response = await axios.get(`/api/execution/${executionId}/load`);
      const data = response.data;

      // Build edges from dependencies
      const edges: Array<{ from: string; to: string }> = [];
      data.nodes.forEach((node: any) => {
        if (node.dependencies && Array.isArray(node.dependencies)) {
          node.dependencies.forEach((depId: string) => {
            edges.push({ from: depId, to: node.id });
          });
        }
      });

      setPlan({
        plan_id: data.plan_id,
        nodes: data.nodes.map((n: any) => ({
          ...n,
          dependencies: n.dependencies || [],
        })),
        edges: edges,
        status: data.status,
        user_prompt: data.user_prompt,
      });

      setExecutionResult({
        execution_id: executionId,
        plan_id: data.plan_id,
        status: data.status,
        node_results: data.nodes.map((n: any) => ({
          node_id: n.id,
          name: n.name,
          status: n.status,
          result: n.result,
          error: n.error,
          execution_time: n.execution_time,
        })),
        execution_logs: data.execution_logs || [],
        started_at: data.timestamp,
        completed_at: data.timestamp,
      });

      setExecutionId(null);
      setExecutionStatus(null);
      setViewingExecutionId(executionId);
      // Select last node by default
      if (data.nodes && data.nodes.length > 0) {
        setSelectedNodeId(data.nodes[data.nodes.length - 1].id);
      }
    } catch (error: any) {
      alert(`Error loading execution: ${error.response?.data?.detail || error.message}`);
    }
  };

  // Update selected node when plan changes - select last node by default
  useEffect(() => {
    if (plan && plan.nodes && plan.nodes.length > 0) {
      if (!selectedNodeId || !plan.nodes.find(n => n.id === selectedNodeId)) {
        const lastNodeId = plan.nodes[plan.nodes.length - 1].id;
        setSelectedNodeId(lastNodeId);
      }
    }
  }, [plan, selectedNodeId]);

  return (
    <div className="min-h-screen bg-dark-bg text-dark-text">
      <Head>
        <title>Agiraph</title>
      </Head>
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        <h1 className="text-4xl font-bold text-center mb-8">Agiraph</h1>

        {/* Tab Navigation */}
        <div className="flex gap-2 mb-6 border-b border-dark-border">
          <button
            onClick={() => setActiveTab('new')}
            className={`px-6 py-3 font-medium transition-colors ${
              activeTab === 'new'
                ? 'bg-blue-600 text-white border-b-2 border-blue-400'
                : 'text-dark-text-muted hover:text-dark-text'
            }`}
          >
            New Task
          </button>
          <button
            onClick={() => setActiveTab('past')}
            className={`px-6 py-3 font-medium transition-colors ${
              activeTab === 'past'
                ? 'bg-blue-600 text-white border-b-2 border-blue-400'
                : 'text-dark-text-muted hover:text-dark-text'
            }`}
          >
            Past Tasks
          </button>
        </div>

        {/* New Task Tab */}
        {activeTab === 'new' && (
          <>
            {/* Input Section */}
        <div className="bg-dark-surface rounded-lg p-6 mb-6">
          <h2 className="text-2xl font-semibold mb-4">Create Task</h2>
          <div className="space-y-4">
            <div>
              <label className="block mb-2 text-sm font-medium">Task Prompt</label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Enter your task description..."
                className="w-full bg-dark-bg border border-dark-border rounded px-4 py-2 min-h-[100px] focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block mb-2 text-xs font-medium text-dark-text-muted">Provider - Model</label>
              <div className="flex gap-2">
                <select
                  value={provider}
                  onChange={(e) => {
                    const selectedProvider = e.target.value;
                    setProvider(selectedProvider);
                    // Update model to default for selected provider
                    const providerInfo = availableProviders.find(p => p.name === selectedProvider);
                    if (providerInfo) {
                      setModel(providerInfo.default_model);
                    }
                  }}
                  className="flex-1 bg-dark-bg border border-dark-border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {availableProviders.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <span className="text-sm text-dark-text-muted self-center">-</span>
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="flex-1 bg-dark-bg border border-dark-border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {(availableProviders.find(p => p.name === provider)?.models || []).map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <button
              onClick={createPlan}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed px-6 py-2 rounded font-medium transition-colors"
            >
              {loading ? 'Creating Plan...' : 'Create Plan'}
            </button>
          </div>
        </div>

        {/* DAG Visualization - Only show if not viewing a past execution */}
        {plan && !viewingExecutionId && (
          <div className="bg-dark-surface rounded-lg p-6 mb-6">
            <h2 className="text-2xl font-semibold mb-4">Execution Plan DAG</h2>
            <DAGVisualization plan={plan} executionStatus={executionStatus} executionResult={executionResult} />
          </div>
        )}

        {/* Execution Controls */}
        {plan && !executionId && !viewingExecutionId && (
          <div className="bg-dark-surface rounded-lg p-6 mb-6">
            <button
              onClick={executePlan}
              disabled={loading}
              className="bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed px-6 py-2 rounded font-medium transition-colors"
            >
              Execute Plan
            </button>
          </div>
        )}

        {/* Execution Status - Only show if not viewing a past execution */}
        {executionStatus && !viewingExecutionId && (
          <div className="bg-dark-surface rounded-lg p-6 mb-6">
            <h2 className="text-2xl font-semibold mb-4">Execution Status</h2>
            <div className="mb-4">
              Status:{' '}
              <span
                className={`inline-block px-3 py-1 rounded-full text-sm font-medium ${
                  executionStatus.status === 'completed'
                    ? 'bg-green-600'
                    : executionStatus.status === 'failed'
                    ? 'bg-red-600'
                    : executionStatus.status === 'executing'
                    ? 'bg-blue-600'
                    : 'bg-gray-600'
                }`}
              >
                {executionStatus.status}
              </span>
            </div>
            {logs.length > 0 && (
              <div className="bg-dark-bg p-4 rounded max-h-48 overflow-y-auto font-mono text-sm">
                {logs.map((log, i) => (
                  <div key={i} className="text-dark-text-muted mb-1">
                    {log}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Node Details - Tabbed View - Only show if not viewing a past execution */}
        {(plan || executionResult) && !viewingExecutionId && (
          <NodeDetailsView
            plan={plan}
            executionResult={executionResult}
            executionStatus={executionStatus}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
          />
        )}
          </>
        )}

        {/* Past Tasks Tab */}
        {activeTab === 'past' && (
          <div className="bg-dark-surface rounded-lg p-6">
            <h2 className="text-2xl font-semibold mb-4">Past Tasks</h2>
            {savedExecutions.length === 0 ? (
              <div className="text-center py-12 text-dark-text-muted">
                No past executions found. Create a new task to get started.
              </div>
            ) : (
              <div className="space-y-2">
                {savedExecutions.map((exec) => (
                  <div
                    key={exec.execution_id}
                    onClick={() => window.open(`/execution/${exec.execution_id}`, '_blank')}
                    className="bg-dark-bg border border-dark-border rounded p-4 cursor-pointer hover:border-blue-500 transition-colors"
                  >
                    <div className="text-xl font-bold mb-2">
                      {exec.title || 'No Title'}
                    </div>
                    <div className="text-sm text-dark-text-muted mb-2">
                      {exec.user_prompt ? (exec.user_prompt.length > 100 ? exec.user_prompt.substring(0, 100) + '...' : exec.user_prompt) : ''}
                    </div>
                    <div className="text-sm text-dark-text-muted">
                      {exec.timestamp ? new Date(exec.timestamp).toLocaleString() : ''} -{' '}
                      <span
                        className={`inline-block px-2 py-1 rounded text-xs ${
                          exec.status === 'completed'
                            ? 'bg-green-600'
                            : exec.status === 'failed'
                            ? 'bg-red-600'
                            : 'bg-gray-600'
                        }`}
                      >
                        {exec.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function NodeDetailsView({
  plan,
  executionResult,
  executionStatus,
  selectedNodeId,
  onSelectNode,
}: {
  plan: Plan | null;
  executionResult: ExecutionResult | null;
  executionStatus: any;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}) {
  // Merge plan nodes with execution results
  const nodesWithResults = plan?.nodes.map((node) => {
    const result = executionResult?.node_results.find((r) => r.node_id === node.id);
    const currentStatus = executionStatus?.node_states?.[node.id] || result?.status || node.status;
    return {
      ...node,
      result: result?.result,
      error: result?.error,
      execution_time: result?.execution_time,
      status: currentStatus,
    };
  }) || [];

  if (nodesWithResults.length === 0) return null;

  const selectedNode = nodesWithResults.find((n) => n.id === selectedNodeId) || nodesWithResults[nodesWithResults.length - 1];
  const isRunning = selectedNode.status === 'running' || selectedNode.status === 'ready';
  const isFinished = selectedNode.status === 'completed' || selectedNode.status === 'failed';

  return (
    <div className="bg-dark-surface rounded-lg p-6 mb-6">
      <h2 className="text-2xl font-semibold mb-4">Node Details</h2>
      
      {/* Tabs */}
      <div className="flex flex-wrap gap-2 mb-6 border-b border-dark-border pb-4">
        {nodesWithResults.map((node, index) => {
          const isLast = index === nodesWithResults.length - 1;
          const isSelected = node.id === selectedNodeId;
          const statusColors: Record<string, string> = {
            pending: 'bg-gray-600',
            ready: 'bg-yellow-600',
            running: 'bg-blue-600',
            completed: 'bg-green-600',
            failed: 'bg-red-600',
          };

          return (
            <button
              key={node.id}
              onClick={() => onSelectNode(node.id)}
              className={`px-4 py-2 rounded-t-lg font-medium transition-all ${
                isSelected
                  ? 'bg-blue-600 text-white border-b-2 border-blue-400 shadow-lg'
                  : isLast
                  ? 'bg-blue-900/30 text-blue-300 border border-blue-500/50 hover:bg-blue-900/50'
                  : 'bg-dark-bg text-dark-text-muted hover:bg-dark-border'
              }`}
            >
              <div className="flex items-center gap-2">
                <span>{node.name}</span>
                <span className={`w-2 h-2 rounded-full ${statusColors[node.status] || 'bg-gray-600'}`} />
              </div>
            </button>
          );
        })}
      </div>

      {/* Selected Node Details */}
      {selectedNode && (
        <div className="space-y-4">
          {/* Status Badge */}
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium">Status:</span>
            <span
              className={`px-3 py-1 rounded-full text-sm font-medium ${
                selectedNode.status === 'completed'
                  ? 'bg-green-600'
                  : selectedNode.status === 'failed'
                  ? 'bg-red-600'
                  : selectedNode.status === 'running'
                  ? 'bg-blue-600'
                  : 'bg-gray-600'
              }`}
            >
              {selectedNode.status}
            </span>
            {selectedNode.execution_time && (
              <span className="text-sm text-dark-text-muted">
                Execution time: {selectedNode.execution_time.toFixed(2)}s
              </span>
            )}
          </div>

          {/* Dependencies */}
          {selectedNode.dependencies && selectedNode.dependencies.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold mb-2">Dependencies:</h3>
              <div className="flex flex-wrap gap-2">
                {selectedNode.dependencies.map((depId) => {
                  const depNode = nodesWithResults.find((n) => n.id === depId);
                  return (
                    <button
                      key={depId}
                      onClick={() => onSelectNode(depId)}
                      className="px-3 py-1 bg-dark-bg border border-dark-border rounded text-sm hover:border-blue-500 transition-colors"
                    >
                      {depNode?.name || depId}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Prompt/Description - Show when running or pending, hide when finished */}
          {!isFinished && (
            <div>
              <h3 className="text-sm font-semibold mb-2">Task Description:</h3>
              <div className="bg-dark-bg p-4 rounded border border-dark-border">
                <p className="text-sm">{selectedNode.description}</p>
                {selectedNode.input_description && (
                  <div className="mt-3 pt-3 border-t border-dark-border">
                    <p className="text-xs text-dark-text-muted mb-1">Input Requirements:</p>
                    <p className="text-sm">{selectedNode.input_description}</p>
                  </div>
                )}
                {selectedNode.output_description && (
                  <div className="mt-3 pt-3 border-t border-dark-border">
                    <p className="text-xs text-dark-text-muted mb-1">Expected Output:</p>
                    <p className="text-sm">{selectedNode.output_description}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Results - Show when finished */}
          {isFinished && (
            <div>
              <h3 className="text-sm font-semibold mb-2">Result:</h3>
              {selectedNode.error ? (
                <div className="bg-red-900/20 border border-red-600 rounded p-4">
                  <p className="text-red-400 font-medium mb-2">Error:</p>
                  <p className="text-sm">{selectedNode.error}</p>
                </div>
              ) : selectedNode.result ? (
                <div className="markdown-content bg-dark-bg p-4 rounded border border-dark-border">
                  <ReactMarkdown>{selectedNode.result}</ReactMarkdown>
                </div>
              ) : (
                <div className="bg-dark-bg p-4 rounded border border-dark-border text-dark-text-muted text-sm">
                  No result available
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DAGVisualization({ plan, executionStatus, executionResult }: { plan: Plan; executionStatus: any; executionResult?: ExecutionResult | null }) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  useEffect(() => {
    // Build node map for quick lookup
    const nodeMap = new Map(plan.nodes.map(node => [node.id, node]));
    
    // Calculate topological levels (depth from root)
    const nodeLevels = new Map<string, number>();
    const visited = new Set<string>();
    
    const calculateLevel = (nodeId: string): number => {
      if (nodeLevels.has(nodeId)) {
        return nodeLevels.get(nodeId)!;
      }
      
      if (visited.has(nodeId)) {
        // Cycle detected, assign level 0
        return 0;
      }
      
      visited.add(nodeId);
      const node = nodeMap.get(nodeId);
      
      if (!node || node.dependencies.length === 0) {
        // Root node (no dependencies)
        nodeLevels.set(nodeId, 0);
        return 0;
      }
      
      // Level is max of all dependency levels + 1
      const maxDepLevel = Math.max(
        ...node.dependencies.map(depId => calculateLevel(depId))
      );
      const level = maxDepLevel + 1;
      nodeLevels.set(nodeId, level);
      return level;
    };
    
    // Calculate levels for all nodes
    plan.nodes.forEach(node => {
      calculateLevel(node.id);
    });
    
    // Group nodes by level
    const nodesByLevel = new Map<number, typeof plan.nodes>();
    plan.nodes.forEach(node => {
      const level = nodeLevels.get(node.id) || 0;
      if (!nodesByLevel.has(level)) {
        nodesByLevel.set(level, []);
      }
      nodesByLevel.get(level)!.push(node);
    });
    
    // Sort levels
    const sortedLevels = Array.from(nodesByLevel.keys()).sort((a, b) => a - b);
    
    // Position nodes: top to bottom by level, left to right within level
    const nodePositions = new Map<string, { x: number; y: number }>();
    const HORIZONTAL_SPACING = 250;
    const VERTICAL_SPACING = 180;
    const START_X = 150;
    const START_Y = 100;
    
    sortedLevels.forEach((level, levelIndex) => {
      const levelNodes = nodesByLevel.get(level)!;
      const levelWidth = levelNodes.length * HORIZONTAL_SPACING;
      const startX = START_X - (levelWidth - HORIZONTAL_SPACING) / 2;
      
      levelNodes.forEach((node, nodeIndex) => {
        nodePositions.set(node.id, {
          x: startX + nodeIndex * HORIZONTAL_SPACING,
          y: START_Y + levelIndex * VERTICAL_SPACING,
        });
      });
    });
    
    // Create ReactFlow nodes with topologically sorted positions
    const dagNodes: Node[] = plan.nodes.map((node) => {
      const status = executionStatus?.node_states?.[node.id] || node.status;
      const statusColors: Record<string, string> = {
        pending: '#475569',
        running: '#3b82f6',
        completed: '#059669', // Darker green for better text readability
        failed: '#ef4444',
      };
      
      // Get execution time from executionResult
      const nodeResult = executionResult?.node_results.find(r => r.node_id === node.id);
      const executionTime = nodeResult?.execution_time;
      
      const position = nodePositions.get(node.id) || { x: 0, y: 0 };

      return {
        id: node.id,
        type: 'default',
        position,
        data: {
          label: (
            <div className="text-center">
              <div className="text-lg font-bold mb-1">{node.name}</div>
              <div className="text-xs text-gray-400 mb-1">{node.id}</div>
              {executionTime && (status === 'completed' || status === 'failed') && (
                <div className="text-xs text-gray-300 mt-1">
                  {executionTime.toFixed(2)}s
                </div>
              )}
            </div>
          ),
        },
        style: {
          background: statusColors[status] || '#334155',
          border: `2px solid ${statusColors[status] || '#475569'}`,
          color: '#e2e8f0',
          width: 200,
          padding: '10px',
        },
      };
    });

    // Create edges
    const dagEdges: Edge[] = [];
    plan.nodes.forEach((node) => {
      node.dependencies.forEach((depId) => {
        dagEdges.push({
          id: `${depId}-${node.id}`,
          source: depId,
          target: node.id,
          type: 'smoothstep',
          animated: executionStatus?.node_states?.[node.id] === 'running',
        });
      });
    });

    setNodes(dagNodes);
    setEdges(dagEdges);
  }, [plan, executionStatus, executionResult]);

  if (!plan) return <div className="text-center py-8">No plan to visualize</div>;

  return (
    <div className="h-[500px] bg-dark-bg border border-dark-border rounded">
      <ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={true} />
    </div>
  );
}
