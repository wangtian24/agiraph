import { useState, useEffect } from 'react';
import { useRouter } from 'next/router';
import ReactFlow, { Node, Edge } from 'reactflow';
import 'reactflow/dist/style.css';
import ReactMarkdown from 'react-markdown';
import axios from 'axios';

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

export default function ExecutionView() {
  const router = useRouter();
  const { id } = router.query;
  const [plan, setPlan] = useState<Plan | null>(null);
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id || typeof id !== 'string') return;

    const loadExecution = async () => {
      try {
        setLoading(true);
        const response = await axios.get(`/api/execution/${id}/load`);
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
          title: data.title,
        });

        setExecutionResult({
          execution_id: id,
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

        // Select last node by default
        if (data.nodes && data.nodes.length > 0) {
          setSelectedNodeId(data.nodes[data.nodes.length - 1].id);
        }
      } catch (err: any) {
        setError(err.response?.data?.detail || err.message || 'Failed to load execution');
      } finally {
        setLoading(false);
      }
    };

    loadExecution();
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-bg text-dark-text flex items-center justify-center">
        <div className="text-center">
          <div className="text-xl mb-4">Loading execution...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-dark-bg text-dark-text flex items-center justify-center">
        <div className="text-center">
          <div className="text-xl text-red-400 mb-4">Error: {error}</div>
          <button
            onClick={() => router.push('/')}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded"
          >
            Back to Home
          </button>
        </div>
      </div>
    );
  }

  if (!plan || !executionResult) {
    return null;
  }

  return (
    <div className="min-h-screen bg-dark-bg text-dark-text">
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        <div className="mb-6">
          <button
            onClick={() => router.push('/')}
            className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded text-sm transition-colors mb-4"
          >
            ← Back to Home
          </button>
        </div>

        {/* Prompt Display */}
        <div className="bg-dark-surface rounded-lg p-6 mb-6">
          <h1 className="text-3xl font-bold mb-4">{plan.title || 'No Title'}</h1>
          <h2 className="text-xl font-semibold mb-4">Original Task</h2>
          <div className="bg-dark-bg border border-dark-border rounded p-4 mb-4">
            <p className="text-dark-text">{plan.user_prompt}</p>
          </div>
          <div className="text-sm text-dark-text-muted">
            {executionResult.started_at ? new Date(executionResult.started_at).toLocaleString() : ''}
            {' - '}
            <span
              className={`inline-block px-2 py-1 rounded text-xs ${
                executionResult.status === 'completed'
                  ? 'bg-green-600'
                  : executionResult.status === 'failed'
                  ? 'bg-red-600'
                  : 'bg-gray-600'
              }`}
            >
              {executionResult.status}
            </span>
          </div>
        </div>

        {/* DAG Visualization */}
        <div className="bg-dark-surface rounded-lg p-6 mb-6">
          <h2 className="text-2xl font-semibold mb-4">Execution Plan DAG</h2>
          <DAGVisualization plan={plan} executionStatus={null} executionResult={executionResult} />
        </div>

        {/* Node Details */}
        <NodeDetailsView
          plan={plan}
          executionResult={executionResult}
          executionStatus={null}
          selectedNodeId={selectedNodeId}
          onSelectNode={setSelectedNodeId}
        />
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
