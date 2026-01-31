"""DAG executor with parallel execution support."""
import asyncio
import json
import time
from collections import defaultdict, deque
from typing import Dict, List, Set
from .models import Node, Plan, NodeStatus
from .providers.factory import create_provider


class DAGExecutor:
    """Executes DAG plans with proper parallelization."""
    
    def __init__(self):
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.node_results: Dict[str, Dict] = {}
        self.execution_logs: List[str] = []
    
    def _log(self, message: str):
        """Add log message."""
        self.execution_logs.append(message)
        print(f"[EXEC] {message}")
    
    def _build_dependency_graph(self, plan: Plan) -> Dict[str, Set[str]]:
        """Build dependency graph: node_id -> set of nodes that depend on it."""
        dependents = defaultdict(set)
        for node in plan.nodes:
            for dep_id in node.dependencies:
                dependents[dep_id].add(node.id)
        return dependents
    
    def _get_ready_nodes(self, plan: Plan, completed: Set[str]) -> List[Node]:
        """Get nodes that are ready to execute (all dependencies completed)."""
        ready = []
        for node in plan.nodes:
            if node.id in completed or node.status == NodeStatus.COMPLETED:
                continue
            if node.status in [NodeStatus.PENDING, NodeStatus.READY]:
                # Check if all dependencies are completed
                if all(dep_id in completed for dep_id in node.dependencies):
                    ready.append(node)
        return ready
    
    def _prepare_node_inputs(self, node: Node, plan: Plan) -> Dict:
        """Prepare inputs for a node based on its dependencies."""
        inputs = {}
        
        # Collect outputs from dependency nodes
        for dep_id in node.dependencies:
            if dep_id in self.node_results:
                dep_result = self.node_results[dep_id]
                # Merge dependency results into inputs
                inputs.update(dep_result)
            else:
                raise ValueError(f"Dependency {dep_id} result not found for node {node.id}")
        
        # If no dependencies, return empty dict (node will work with its input contract)
        return inputs
    
    async def _execute_node(self, node: Node, plan: Plan) -> Dict:
        """Execute a single node."""
        node.status = NodeStatus.RUNNING
        self._log(f"Starting node {node.id}: {node.name}")
        
        start_time = time.time()
        
        try:
            # Prepare inputs
            inputs = self._prepare_node_inputs(node, plan)
            
            # Create provider
            provider = create_provider(node.provider)
            
            # Build execution prompt
            if inputs:
                inputs_str = json.dumps(inputs, indent=2)
            else:
                inputs_str = "No inputs (this is an independent task)"
            
            prompt = f"""Task: {node.description}

Input Contract: {json.dumps(node.input_contract, indent=2)}
Output Contract: {json.dumps(node.output_contract, indent=2)}

Current Inputs:
{inputs_str}

Execute this task and return the result as JSON matching the output contract."""
            
            # Execute
            response = await provider.generate(
                prompt=prompt,
                model=node.model,
                system_prompt=f"You are executing task: {node.name}. Follow the output contract exactly and return valid JSON."
            )
            
            # Parse response
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
            
            result = json.loads(response)
            
            execution_time = time.time() - start_time
            node.execution_time = execution_time
            node.status = NodeStatus.COMPLETED
            node.result = result
            
            self._log(f"Completed node {node.id}: {node.name} (took {execution_time:.2f}s)")
            return result
            
        except Exception as e:
            node.status = NodeStatus.FAILED
            node.error = str(e)
            execution_time = time.time() - start_time
            self._log(f"Failed node {node.id}: {node.name} - {e}")
            raise
    
    async def execute(self, plan: Plan) -> Dict:
        """Execute a plan with parallel execution."""
        # Validate all nodes have available providers
        from .config import Config
        available_providers = Config.get_available_provider_names()
        
        for node in plan.nodes:
            if node.provider not in available_providers:
                raise ValueError(f"Node {node.id} uses unavailable provider '{node.provider}'. Available: {', '.join(available_providers)}")
        
        self._log(f"Starting execution of plan {plan.plan_id}")
        plan.status = "executing"
        
        completed: Set[str] = set()
        dependents = self._build_dependency_graph(plan)
        
        # Initialize node results dict
        for node in plan.nodes:
            self.node_results[node.id] = {}
        
        # Execute nodes in waves of parallelism
        while len(completed) < len(plan.nodes):
            # Get all ready nodes
            ready_nodes = self._get_ready_nodes(plan, completed)
            
            if not ready_nodes:
                # Check if we're stuck (all remaining nodes have failed dependencies)
                remaining = [n for n in plan.nodes if n.id not in completed and n.status != NodeStatus.FAILED]
                if remaining:
                    failed_deps = []
                    for node in remaining:
                        failed_deps.extend([d for d in node.dependencies if d not in completed])
                    if failed_deps:
                        self._log(f"ERROR: Cannot proceed - dependencies failed: {failed_deps}")
                        break
                else:
                    break
            
            # Execute all ready nodes in parallel
            self._log(f"Executing {len(ready_nodes)} nodes in parallel: {[n.id for n in ready_nodes]}")
            
            tasks = []
            for node in ready_nodes:
                task = asyncio.create_task(self._execute_node(node, plan))
                tasks.append((node.id, task))
            
            # Wait for all tasks in this wave
            for node_id, task in tasks:
                try:
                    result = await task
                    self.node_results[node_id] = result
                    completed.add(node_id)
                except Exception as e:
                    self._log(f"Node {node_id} failed: {e}")
                    # Mark as failed but continue with other nodes if possible
        
        # Finalize
        plan.status = "completed" if len(completed) == len(plan.nodes) else "failed"
        self._log(f"Execution completed. Status: {plan.status}")
        
        # Aggregate results
        final_result = {
            "plan_id": plan.plan_id,
            "status": plan.status,
            "node_results": self.node_results,
            "execution_logs": self.execution_logs
        }
        
        return final_result
