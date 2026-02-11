"""Wire tool definitions to implementations and create the default registry."""

from agiraph.tools.definitions import (
    ASK_HUMAN, ASSIGN_WORKER, BASH, CANCEL_TRIGGER, CHECK_BOARD,
    CHECK_MESSAGES, CHECKPOINT, CREATE_WORK_NODE, FINISH, LIST_FILES,
    LIST_TRIGGERS, MEMORY_READ, MEMORY_SEARCH, MEMORY_WRITE, PUBLISH,
    READ_FILE, READ_REF, RECONVENE, SCHEDULE, SEND_MESSAGE, SPAWN_WORKER,
    SUGGEST_NEXT, WEB_FETCH, WEB_SEARCH, WRITE_FILE,
)
from agiraph.tools.implementations import (
    impl_ask_human, impl_assign_worker, impl_bash, impl_cancel_trigger,
    impl_check_board, impl_check_messages, impl_checkpoint,
    impl_create_work_node, impl_finish, impl_list_files, impl_list_triggers,
    impl_memory_read, impl_memory_search, impl_memory_write, impl_publish,
    impl_read_file, impl_read_ref, impl_reconvene, impl_schedule,
    impl_send_message, impl_spawn_worker, impl_suggest_next, impl_web_fetch,
    impl_web_search, impl_write_file,
)
from agiraph.tools.registry import ToolRegistry


def create_default_registry() -> ToolRegistry:
    """Create a fully-wired tool registry with all built-in tools."""
    registry = ToolRegistry()

    # Work management
    registry.register(PUBLISH, impl_publish)
    registry.register(CHECKPOINT, impl_checkpoint)
    registry.register(CREATE_WORK_NODE, impl_create_work_node)
    registry.register(SUGGEST_NEXT, impl_suggest_next)

    # Communication
    registry.register(SEND_MESSAGE, impl_send_message)
    registry.register(CHECK_MESSAGES, impl_check_messages)
    registry.register(ASK_HUMAN, impl_ask_human)

    # File I/O
    registry.register(READ_FILE, impl_read_file)
    registry.register(WRITE_FILE, impl_write_file)
    registry.register(LIST_FILES, impl_list_files)
    registry.register(READ_REF, impl_read_ref)

    # Execution
    registry.register(BASH, impl_bash)

    # Research
    registry.register(WEB_SEARCH, impl_web_search)
    registry.register(WEB_FETCH, impl_web_fetch)

    # Memory
    registry.register(MEMORY_WRITE, impl_memory_write)
    registry.register(MEMORY_READ, impl_memory_read)
    registry.register(MEMORY_SEARCH, impl_memory_search)

    # Scheduling
    registry.register(SCHEDULE, impl_schedule)
    registry.register(LIST_TRIGGERS, impl_list_triggers)
    registry.register(CANCEL_TRIGGER, impl_cancel_trigger)

    # Coordinator-only
    registry.register(SPAWN_WORKER, impl_spawn_worker)
    registry.register(ASSIGN_WORKER, impl_assign_worker)
    registry.register(CHECK_BOARD, impl_check_board)
    registry.register(RECONVENE, impl_reconvene)
    registry.register(FINISH, impl_finish)

    return registry
