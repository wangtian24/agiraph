"""AI planner that creates DAG from user prompts."""
import json
import uuid
from typing import List
from .models import Node, Plan, NodeStatus
from .providers.factory import create_provider
from .config import Config


def get_planner_system_prompt(available_providers: List[str], forced_provider: str = None, forced_model: str = None) -> str:
    """Generate planner system prompt with available providers."""
    providers_str = "|".join(available_providers) if available_providers else "openai"
    
    provider_constraint = ""
    if forced_provider and forced_model:
        provider_constraint = f"\n\nCRITICAL: ALL nodes MUST use provider=\"{forced_provider}\" and model=\"{forced_model}\". Do NOT use any other provider or model."
    
    return f"""You are an expert task planner for AI agent orchestration. Your job is to break down complex tasks into a Directed Acyclic Graph (DAG) of independent, parallelizable components.

CRITICAL PRINCIPLES:
1. **Maximize Parallelism**: Split tasks so that as many nodes as possible can run in parallel. Think about what can be done independently.
2. **Natural Language Communication**: All communication between nodes should be in natural language. Avoid structured schemas unless absolutely necessary.
3. **Minimal Dependencies**: Only create dependencies when absolutely necessary. If two tasks can run independently, they should have no dependency.
4. **Atomic Components**: Each node should be a single, well-defined task that can be completed by an AI agent independently.
5. **Clear Descriptions**: Each node should have a clear description of what it needs as input (if any) and what it will produce as output, all in natural language.

IMPORTANT: You can ONLY use these available providers: {", ".join(available_providers) if available_providers else "none configured"}
Do NOT use any provider that is not in this list.{provider_constraint}

OUTPUT FORMAT:
You must respond with a valid JSON object with this exact structure:
{{
  "nodes": [
    {{
      "id": "node_0",
      "name": "Task Name",
      "description": "Detailed description of what this node does and what it will produce",
      "provider": "{providers_str}",
      "model": "model_name",
      "input_description": "Natural language description of what inputs this node needs (if any). Leave empty string if no inputs needed.",
      "output_description": "Natural language description of what this node will produce",
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
        self.provider_name = provider_name
        self.provider = create_provider(provider_name)
        self.model = model or Config.DEFAULT_MODELS.get(provider_name, "gpt-4o-mini")
        self.available_providers = Config.get_available_provider_names()
    
    async def create_plan(self, user_prompt: str, force_provider: str = None, force_model: str = None) -> Plan:
        """Create a DAG plan from user prompt.
        
        Args:
            user_prompt: The task to plan
            force_provider: If provided, all nodes will use this provider
            force_model: If provided, all nodes will use this model
        """
        # Use forced provider/model if provided, otherwise use planner's provider/model
        forced_provider = force_provider or self.provider_name
        forced_model = force_model or self.model
        
        # Get system prompt with available providers and forced provider/model
        system_prompt = get_planner_system_prompt(
            self.available_providers,
            forced_provider=forced_provider,
            forced_model=forced_model
        )
        
        provider_note = ""
        if forced_provider and forced_model:
            provider_note = f"\n\nCRITICAL: ALL nodes must use provider=\"{forced_provider}\" and model=\"{forced_model}\". Do not use any other provider or model."
        
        planning_prompt = f"""Create a detailed execution plan for the following task:

TASK: {user_prompt}

Break this down into a DAG with clear nodes and dependencies. Maximize parallelism where possible.
Use natural language descriptions for inputs and outputs - avoid structured schemas unless absolutely necessary.

IMPORTANT: Only use providers from this list: {", ".join(self.available_providers) if self.available_providers else "none"}{provider_note}

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
                # Use forced provider/model if specified, otherwise use what planner suggested
                if forced_provider and forced_model:
                    provider = forced_provider.lower()
                    model = forced_model
                else:
                    provider = node_data.get("provider", "openai").lower()
                    model = node_data.get("model", Config.DEFAULT_MODELS.get(provider))
                
                # Validate provider is available
                if provider not in self.available_providers:
                    # Fallback to first available provider
                    if self.available_providers:
                        provider = self.available_providers[0]
                        model = Config.DEFAULT_MODELS.get(provider)
                    else:
                        raise ValueError(f"Node {node_data.get('id')} uses unavailable provider {node_data.get('provider')}. No providers configured.")
                
                # Handle both old format (input_contract/output_contract) and new format (input_description/output_description)
                input_desc = node_data.get("input_description", "")
                output_desc = node_data.get("output_description", "")
                
                # Fallback to old format if new format not present
                if not input_desc and "input_contract" in node_data:
                    # Convert old contract to natural language description
                    contract = node_data.get("input_contract", {})
                    if contract:
                        input_desc = f"Needs: {', '.join([f'{k} ({v})' for k, v in contract.items()])}"
                
                if not output_desc and "output_contract" in node_data:
                    contract = node_data.get("output_contract", {})
                    if contract:
                        output_desc = f"Produces: {', '.join([f'{k} ({v})' for k, v in contract.items()])}"
                
                node = Node(
                    id=node_data["id"],
                    name=node_data["name"],
                    description=node_data["description"],
                    provider=provider,
                    model=model,
                    input_description=input_desc,
                    output_description=output_desc,
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
