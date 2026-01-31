"""DAG executor with parallel execution support."""
import asyncio
import time
from collections import defaultdict, deque
from typing import Dict, List, Set
from .models import Node, Plan, NodeStatus
from .providers.factory import create_provider


class DAGExecutor:
    """Executes DAG plans with proper parallelization."""
    
    def __init__(self):
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.node_results: Dict[str, str] = {}  # node_id -> natural language result
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
    
    def _prepare_node_inputs(self, node: Node, plan: Plan) -> str:
        """Prepare inputs for a node based on its dependencies in natural language."""
        if not node.dependencies:
            return ""
        
        # Collect outputs from dependency nodes
        input_parts = []
        for dep_id in node.dependencies:
            if dep_id in self.node_results:
                dep_result = self.node_results[dep_id]
                # Get the dependency node name for context
                dep_node = next((n for n in plan.nodes if n.id == dep_id), None)
                dep_name = dep_node.name if dep_node else dep_id
                
                # Add dependency result as natural language
                input_parts.append(f"From {dep_name} ({dep_id}):\n{dep_result}")
            else:
                raise ValueError(f"Dependency {dep_id} result not found for node {node.id}")
        
        return "\n\n".join(input_parts)
    
    async def _execute_node(self, node: Node, plan: Plan) -> str:
        """Execute a single node and return natural language result."""
        node.status = NodeStatus.RUNNING
        self._log(f"Starting node {node.id}: {node.name}")
        
        start_time = time.time()
        
        try:
            # Prepare inputs in natural language
            inputs_text = self._prepare_node_inputs(node, plan)
            
            # Create provider
            provider = create_provider(node.provider)
            
            # Build execution prompt in natural language
            prompt_parts = [f"Task: {node.description}"]
            
            if node.output_description:
                prompt_parts.append(f"\nWhat you need to produce: {node.output_description}")
            
            if node.input_description:
                prompt_parts.append(f"\nWhat you need as input: {node.input_description}")
            
            if inputs_text:
                prompt_parts.append(f"\n\nInputs from previous tasks:\n{inputs_text}")
            elif node.dependencies:
                prompt_parts.append("\n\nNote: You have dependencies but their results are not yet available.")
            
            prompt_parts.append("\n\nExecute this task and provide your result in clear, natural language.")
            
            prompt = "\n".join(prompt_parts)
            
            # Execute with natural language system prompt
            system_prompt = f"""You are executing the task: {node.name}

Your job is to complete this task and provide the result in clear, natural language.
Be thorough and complete. Do not use JSON or structured formats unless absolutely necessary.
Just provide your work and results in natural, readable text."""
            
            response = await provider.generate(
                prompt=prompt,
                model=node.model,
                system_prompt=system_prompt
            )
            
            # Response is already natural language, no JSON parsing needed
            result = response.strip()
            
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
        
        # Initialize node results dict (will store natural language strings)
        for node in plan.nodes:
            self.node_results[node.id] = ""
        
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
                    # Store natural language result
                    self.node_results[node_id] = result if isinstance(result, str) else str(result)
                    completed.add(node_id)
                except Exception as e:
                    self._log(f"Node {node_id} failed: {e}")
                    # Mark as failed but continue with other nodes if possible
        
        # Finalize
        plan.status = "completed" if len(completed) == len(plan.nodes) else "failed"
        self._log(f"Execution completed. Status: {plan.status}")
        
        # Aggregate results (all in natural language)
        final_result = {
            "plan_id": plan.plan_id,
            "status": plan.status,
            "node_results": self.node_results,  # Dict of node_id -> natural language result
            "execution_logs": self.execution_logs
        }
        
        return final_result
