# Simple AI Agent

A lightweight Python-based agent with lane-based queuing, command execution, and LLM-powered natural language processing capabilities.

## Features

- **Lane Queue System**: Organize tasks into different lanes with configurable concurrency
- **Priority-based Execution**: Tasks are executed based on priority (CRITICAL > HIGH > MEDIUM > LOW)
- **Command Execution Layer**: Execute terminal/bash commands safely
- **LLM Integration**: Convert natural language to shell commands using your preferred LLM API
- **Multi-threaded Processing**: Each lane runs in its own thread for concurrent execution
- **Task Tracking**: Monitor task status and results

## Architecture

### Components

1. **Task**: Represents a single command to be executed with priority and lane assignment
2. **LaneQueue**: Manages queued tasks for a specific lane with concurrency limits
3. **ExecutionLayer**: Handles actual command execution using subprocess
4. **LLMIntegration**: Converts natural language to shell commands using your LLM API
5. **SimpleAgent**: Main orchestrator that manages lanes and coordinates execution

### Lane System

- **default lane**: Up to 2 concurrent tasks
- **high_priority lane**: 1 concurrent task (for important tasks)
- Custom lanes can be added with any concurrency limit

## Usage

### Standard Agent (Command-based)

```python
from agent import SimpleAgent, TaskPriority

# Create and start the agent
agent = SimpleAgent()
agent.start()

# Submit tasks to different lanes
agent.submit_task("echo 'Hello World!'", TaskPriority.MEDIUM, "default")
agent.submit_task("ls -la", TaskPriority.HIGH, "default")
agent.submit_task("echo 'Critical task!'", TaskPriority.CRITICAL, "high_priority")

# Stop the agent
agent.stop()
```

### LLM-Enabled Agent (Natural Language)

```python
from agent import SimpleAgent, TaskPriority

# Create agent with LLM integration enabled
agent = SimpleAgent(use_llm=True)
agent.start()

# Submit natural language requests
agent.submit_natural_language_task("list all files in current directory", TaskPriority.MEDIUM, "default")
agent.submit_natural_language_task("what time is it?", TaskPriority.HIGH, "high_priority")
agent.submit_natural_language_task("say hello world", TaskPriority.MEDIUM, "default")

# Stop the agent
agent.stop()
```

### Integrating Your LLM API

Replace the mock `API_CALL` function in `agent.py` with your actual LLM integration:

```python
def API_CALL(prompt: str) -> str:
    # Example with OpenAI
    import openai
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    return response.choices[0].message.content.strip()
```

### Priority Levels

- `TaskPriority.CRITICAL` (4) - Highest priority
- `TaskPriority.HIGH` (3)
- `TaskPriority.MEDIUM` (2) - Default
- `TaskPriority.LOW` (1) - Lowest priority

### Adding Custom Lanes

```python
# Add a lane with 3 concurrent workers
agent.add_lane("batch_processing", max_concurrent=3)

# Submit tasks to the custom lane
agent.submit_task("python process_data.py", TaskPriority.MEDIUM, "batch_processing")
```

## Running the Example

The included example demonstrates the agent's capabilities:

```bash
python agent.py
```

This will:
1. Start the agent with default and high_priority lanes
2. Submit 5 test tasks with different priorities
3. Execute them concurrently according to lane limits
4. Display statistics and results

## Output Format

Each task result includes:
- `task_id`: Unique identifier
- `command`: The executed command
- `lane`: Which lane processed the task
- `success`: Boolean indicating if command succeeded
- `stdout`: Standard output from the command
- `stderr`: Standard error from the command
- `completed_at`: Timestamp when task finished

## Thread Safety

The agent uses thread-safe queues and proper synchronization to handle concurrent task execution across multiple lanes.
