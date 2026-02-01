"""FastAPI backend for AI orchestration framework."""
import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .planner import Planner
from .executor import DAGExecutor
from .config import Config
from .models import Plan, NodeStatus


app = FastAPI(title="AI Agent Orchestration Framework")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage directory for execution results
STORAGE_DIR = Path(__file__).parent.parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)


# Request/Response models
class PlanRequest(BaseModel):
    prompt: str
    provider: str
    model: str


class ExecutionRequest(BaseModel):
    plan_id: str


class ExecutionStatus(BaseModel):
    execution_id: str
    plan_id: str
    status: str
    node_states: Dict[str, str]
    logs: List[str]


class NodeResult(BaseModel):
    node_id: str
    name: str
    status: str
    result: Optional[str] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None


class ExecutionResult(BaseModel):
    execution_id: str
    plan_id: str
    status: str
    node_results: List[NodeResult]
    execution_logs: List[str]
    started_at: str
    completed_at: Optional[str] = None


# In-memory storage for active executions
active_plans: Dict[str, Plan] = {}
active_executions: Dict[str, Dict] = {}


@app.get("/api/providers")
async def get_providers():
    """Get available providers and their default models."""
    available = Config.get_available_providers()
    available_providers = [p for p, avail in available.items() if avail]
    
    return {
        "providers": available_providers,
        "default_models": Config.DEFAULT_MODELS
    }




@app.post("/api/plan", response_model=Dict)
async def create_plan(request: PlanRequest):
    """Create an execution plan from a prompt."""
    try:
        planner = Planner(provider_name=request.provider, model=request.model)
        plan = await planner.create_plan(
            request.prompt,
            force_provider=request.provider,
            force_model=request.model
        )
        
        # Store plan
        active_plans[plan.plan_id] = plan
        
        # Convert to dict for JSON response
        plan_dict = {
            "plan_id": plan.plan_id,
            "user_prompt": plan.user_prompt,
            "title": plan.title,
            "nodes": [
                {
                    "id": node.id,
                    "name": node.name,
                    "description": node.description,
                    "provider": node.provider,
                    "model": node.model,
                    "input_description": node.input_description,
                    "output_description": node.output_description,
                    "dependencies": node.dependencies,
                    "status": node.status.value
                }
                for node in plan.nodes
            ],
            "edges": plan.edges,
            "status": plan.status
        }
        
        return plan_dict
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/execute")
async def execute_plan(request: ExecutionRequest):
    """Start executing a plan."""
    if request.plan_id not in active_plans:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    plan = active_plans[request.plan_id]
    execution_id = str(uuid.uuid4())
    
    # Store execution info
    active_executions[execution_id] = {
        "execution_id": execution_id,
        "plan_id": request.plan_id,
        "status": "starting",
        "started_at": datetime.now().isoformat(),
        "node_states": {},
        "logs": []
    }
    
    # Start execution in background (in real implementation, use background tasks)
    # For now, return execution_id and client can poll for status
    return {"execution_id": execution_id, "plan_id": request.plan_id}


@app.get("/api/execution/{execution_id}/status", response_model=ExecutionStatus)
async def get_execution_status(execution_id: str):
    """Get current execution status."""
    if execution_id not in active_executions:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    exec_info = active_executions[execution_id]
    plan = active_plans.get(exec_info["plan_id"])
    
    if plan:
        node_states = {node.id: node.status.value for node in plan.nodes}
    else:
        node_states = exec_info.get("node_states", {})
    
    return ExecutionStatus(
        execution_id=execution_id,
        plan_id=exec_info["plan_id"],
        status=exec_info["status"],
        node_states=node_states,
        logs=exec_info.get("logs", [])
    )


@app.get("/api/execution/{execution_id}/result", response_model=ExecutionResult)
async def get_execution_result(execution_id: str):
    """Get execution results."""
    if execution_id not in active_executions:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    exec_info = active_executions[execution_id]
    plan = active_plans.get(exec_info["plan_id"])
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Build node results
    node_results = []
    for node in plan.nodes:
        node_results.append(NodeResult(
            node_id=node.id,
            name=node.name,
            status=node.status.value,
            result=node.result,
            error=node.error,
            execution_time=node.execution_time
        ))
    
    return ExecutionResult(
        execution_id=execution_id,
        plan_id=exec_info["plan_id"],
        status=exec_info["status"],
        node_results=node_results,
        execution_logs=exec_info.get("logs", []),
        started_at=exec_info["started_at"],
        completed_at=exec_info.get("completed_at")
    )


@app.post("/api/execute/{execution_id}/start")
async def start_execution(execution_id: str):
    """Actually start the execution (runs async)."""
    if execution_id not in active_executions:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    exec_info = active_executions[execution_id]
    plan = active_plans.get(exec_info["plan_id"])
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Run execution in background
    import asyncio
    asyncio.create_task(run_execution(execution_id, plan, exec_info))
    
    return {"status": "started", "execution_id": execution_id}


async def run_execution(execution_id: str, plan: Plan, exec_info: Dict):
    """Run execution and update status."""
    try:
        exec_info["status"] = "executing"
        executor = DAGExecutor()
        
        # Override executor's log function to update execution info
        original_log = executor._log
        def log_with_storage(message: str):
            original_log(message)
            exec_info["logs"].append(message)
            # Update node states
            for node in plan.nodes:
                exec_info["node_states"][node.id] = node.status.value
        
        executor._log = log_with_storage
        
        # Execute
        result = await executor.execute(plan)
        
        # Save results to JSON file
        save_execution_result(execution_id, plan, result)
        
        exec_info["status"] = result["status"]
        exec_info["completed_at"] = datetime.now().isoformat()
        exec_info["node_states"] = {node.id: node.status.value for node in plan.nodes}
        
    except Exception as e:
        exec_info["status"] = "failed"
        exec_info["error"] = str(e)
        exec_info["logs"].append(f"Execution failed: {e}")


def save_execution_result(execution_id: str, plan: Plan, result: Dict):
    """Save execution result to JSON file."""
    save_data = {
        "execution_id": execution_id,
        "plan_id": plan.plan_id,
        "user_prompt": plan.user_prompt,
        "title": plan.title,
        "timestamp": datetime.now().isoformat(),
        "status": result["status"],
        "nodes": [
            {
                "id": node.id,
                "name": node.name,
                "description": node.description,
                "provider": node.provider,
                "model": node.model,
                "input_description": node.input_description,
                "output_description": node.output_description,
                "dependencies": node.dependencies,
                "status": node.status.value,
                "result": node.result,
                "error": node.error,
                "execution_time": node.execution_time
            }
            for node in plan.nodes
        ],
        "node_results": result.get("node_results", {}),
        "execution_logs": result.get("execution_logs", [])
    }
    
    file_path = STORAGE_DIR / f"{execution_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)


@app.get("/api/executions")
async def list_executions():
    """List all saved executions."""
    execution_files = sorted(STORAGE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    executions = []
    for file_path in execution_files[:50]:  # Limit to 50 most recent
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                executions.append({
                    "execution_id": data.get("execution_id", file_path.stem),
                    "plan_id": data.get("plan_id"),
                    "title": data.get("title"),
                    "user_prompt": data.get("user_prompt", ""),
                    "timestamp": data.get("timestamp"),
                    "status": data.get("status")
                })
        except Exception:
            continue
    
    return {"executions": executions}


@app.get("/api/execution/{execution_id}/load")
async def load_execution(execution_id: str):
    """Load a saved execution result."""
    file_path = STORAGE_DIR / f"{execution_id}.json"
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Execution not found")
    
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.websocket("/ws/{execution_id}")
async def websocket_endpoint(websocket: WebSocket, execution_id: str):
    """WebSocket endpoint for real-time execution updates."""
    await websocket.accept()
    
    try:
        while True:
            if execution_id in active_executions:
                exec_info = active_executions[execution_id]
                plan = active_plans.get(exec_info["plan_id"])
                
                if plan:
                    node_states = {node.id: node.status.value for node in plan.nodes}
                else:
                    node_states = exec_info.get("node_states", {})
                
                await websocket.send_json({
                    "status": exec_info["status"],
                    "node_states": node_states,
                    "logs": exec_info.get("logs", [])[-10:]  # Last 10 logs
                })
            
            await asyncio.sleep(1)  # Update every second
    except WebSocketDisconnect:
        pass


# Mount static files - serve frontend
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")
    
    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        """Serve frontend files."""
        # Don't interfere with API routes
        if path.startswith("api/") or path.startswith("ws/"):
            raise HTTPException(status_code=404)
        if path == "" or path == "index.html" or not path:
            return FileResponse(str(frontend_path / "index.html"))
        file_path = frontend_path / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_path / "index.html"))
