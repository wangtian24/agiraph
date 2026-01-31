"""AI planner that creates DAG from user prompts."""
import json
import uuid
from typing import List
from .models import Node, Plan, NodeStatus
from .providers.factory import create_provider
from .config import Config


def get_planner_system_prompt(available_providers: List[str]) -> str:
    """Generate planner system prompt with available providers."""
    providers_str = "|".join(available_providers) if available_providers else "openai"
    
    return f"""You are an expert task planner for AI agent orchestration. Your job is to break down complex tasks into a Directed Acyclic Graph (DAG) of independent, parallelizable components.

CRITICAL PRINCIPLES:
1. **Maximize Parallelism**: Split tasks so that as many nodes as possible can run in parallel. Think about what can be done independently.
2. **Clear Contracts**: Each node must have explicit input and output contracts. Define exactly what data each node needs and produces.
3. **Minimal Dependencies**: Only create dependencies when absolutely necessary. If two tasks can run independently, they should have no dependency.
4. **Atomic Components**: Each node should be a single, well-defined task that can be completed by an AI agent independently.
5. **Reusability**: Design outputs that can be consumed by multiple downstream nodes when needed.

IMPORTANT: You can ONLY use these available providers: {", ".join(available_providers) if available_providers else "none configured"}
Do NOT use any provider that is not in this list.

OUTPUT FORMAT:
You must respond with a valid JSON object with this exact structure:
{{
  "nodes": [
    {{
      "id": "node_0",
      "name": "Task Name",
      "description": "Detailed description of what this node does",
      "provider": "{providers_str}",
      "model": "model_name",
      "input_contract": {{
        "field1": "description of what this field should contain",
        "field2": "description"
      }},
      "output_contract": {{
        "field1": "description of what this field will contain",
        "field2": "description"
      }},
      "dependencies": ["node_id1", "node_id2"]  // Empty array if no dependencies
    }}
  ],
  "edges": [
    {{"from": "node_id", "to": "node_id"}}  // Only include explicit dependencies
  ]
}}

EXAMPLES OF GOOD PARALLELIZATION:
- If task needs research on multiple topics, create separate nodes for each topic (no dependencies)
- If task needs code generation and documentation, these can be parallel if they don't depend on each other
- If task needs data processing and visualization, they can be parallel if visualization doesn't need processed data

EXAMPLES OF NECESSARY DEPENDENCIES:
- Code generation -> Code testing (testing needs the code)
- Data collection -> Data analysis (analysis needs the data)
- Multiple research nodes -> Synthesis node (synthesis needs all research results)

Think carefully about dependencies. When in doubt, make nodes independent and parallelizable."""


class Planner:
    """Creates execution plans from user prompts."""
    
    def __init__(self, provider_name: str = "openai", model: str = None):
        """Initialize planner with AI provider."""
        self.provider = create_provider(provider_name)
        self.model = model or Config.DEFAULT_MODELS.get(provider_name, "gpt-4o-mini")
        self.available_providers = Config.get_available_provider_names()
    
    async def create_plan(self, user_prompt: str) -> Plan:
        """Create a DAG plan from user prompt."""
        # Get system prompt with available providers
        system_prompt = get_planner_system_prompt(self.available_providers)
        
        planning_prompt = f"""Create a detailed execution plan for the following task:

TASK: {user_prompt}

Break this down into a DAG with clear nodes, contracts, and dependencies. Maximize parallelism where possible.

IMPORTANT: Only use providers from this list: {", ".join(self.available_providers) if self.available_providers else "none"}

Respond with ONLY the JSON object, no additional text."""
        
        try:
            response = await self.provider.generate(
                prompt=planning_prompt,
                model=self.model,
                system_prompt=system_prompt
            )
            
            # Extract JSON from response (handle markdown code blocks)
            response = response.strip()
            if response.startswith("```"):
                # Remove markdown code blocks
                lines = response.split("\n")
                response = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
            
            plan_data = json.loads(response)
            
            # Create nodes and validate providers
            nodes = []
            for node_data in plan_data.get("nodes", []):
                provider = node_data.get("provider", "openai").lower()
                
                # Validate provider is available
                if provider not in self.available_providers:
                    # Fallback to first available provider
                    if self.available_providers:
                        provider = self.available_providers[0]
                    else:
                        raise ValueError(f"Node {node_data.get('id')} uses unavailable provider {node_data.get('provider')}. No providers configured.")
                
                node = Node(
                    id=node_data["id"],
                    name=node_data["name"],
                    description=node_data["description"],
                    provider=provider,
                    model=node_data.get("model", Config.DEFAULT_MODELS.get(provider)),
                    input_contract=node_data.get("input_contract", {}),
                    output_contract=node_data.get("output_contract", {}),
                    dependencies=node_data.get("dependencies", []),
                    status=NodeStatus.PENDING
                )
                nodes.append(node)
            
            # Create plan
            plan = Plan(
                plan_id=str(uuid.uuid4()),
                user_prompt=user_prompt,
                nodes=nodes,
                edges=plan_data.get("edges", []),
                status="draft"
            )
            
            return plan
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse planner response as JSON: {e}\nResponse: {response}")
        except Exception as e:
            raise ValueError(f"Planning failed: {e}")
