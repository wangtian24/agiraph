"""AI planner that creates DAG from user prompts."""
import json
import uuid
from typing import List
from .models import Node, Plan, NodeStatus
from .providers.factory import create_provider
from .config import Config
from .prompts import load_prompt, format_prompt


def get_planner_system_prompt(available_providers: List[str], forced_provider: str = None, forced_model: str = None) -> str:
    """Generate planner system prompt with available providers."""
    providers_str = "|".join(available_providers) if available_providers else "openai"
    
    provider_constraint = ""
    if forced_provider and forced_model:
        provider_constraint = f"\n\nCRITICAL: ALL nodes MUST use provider=\"{forced_provider}\" and model=\"{forced_model}\". Do NOT use any other provider or model."
    
    template = load_prompt("planner_system.txt")
    
    return format_prompt(
        template,
        available_providers=", ".join(available_providers) if available_providers else "none configured",
        provider_constraint=provider_constraint,
        providers_str=providers_str
    )


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
        
        template = load_prompt("planner_user.txt")
        planning_prompt = format_prompt(
            template,
            user_prompt=user_prompt,
            available_providers=", ".join(self.available_providers) if self.available_providers else "none",
            provider_note=provider_note
        )
        
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
            
            # Generate a title if not provided in plan_data
            title = plan_data.get("title")
            if not title:
                # Generate a short title from the user prompt
                title_prompt = f"Generate a short, descriptive title (3-8 words) for this task: {user_prompt}\n\nRespond with ONLY the title, no additional text."
                try:
                    title = await self.provider.generate(
                        prompt=title_prompt,
                        model=self.model,
                        system_prompt="You are a title generator. Generate concise, descriptive titles."
                    )
                    title = title.strip().strip('"').strip("'")
                except Exception:
                    # Fallback to first few words of prompt
                    words = user_prompt.split()[:6]
                    title = " ".join(words) + ("..." if len(user_prompt.split()) > 6 else "")
            
            # Create plan
            plan = Plan(
                plan_id=str(uuid.uuid4()),
                user_prompt=user_prompt,
                title=title,
                nodes=nodes,
                edges=plan_data.get("edges", []),
                status="draft"
            )
            
            return plan
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse planner response as JSON: {e}\nResponse: {response}")
        except Exception as e:
            raise ValueError(f"Planning failed: {e}")
