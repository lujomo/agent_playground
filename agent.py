import subprocess
import threading
import queue
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Task:
    id: str
    command: str
    priority: TaskPriority
    created_at: float
    lane: str = "default"
    metadata: Optional[Dict[str, Any]] = None
    natural_language: Optional[str] = None  # Store original NL input


class LaneQueue:
    def __init__(self, name: str, max_concurrent: int = 1):
        self.name = name
        self.max_concurrent = max_concurrent
        self.queue = queue.PriorityQueue()
        self.running_tasks = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        
    def add_task(self, task: Task):
        # Use negative priority for max-heap behavior (higher priority = lower number)
        priority_value = -task.priority.value
        self.queue.put((priority_value, task.created_at, task))
        
    def get_task(self) -> Optional[Task]:
        if not self.queue.empty() and self.running_tasks < self.max_concurrent:
            _, _, task = self.queue.get()
            return task
        return None
        
    def task_started(self):
        self.running_tasks += 1
        
    def task_completed(self, success: bool = True):
        self.running_tasks -= 1
        if success:
            self.completed_tasks += 1
        else:
            self.failed_tasks += 1
            
    def is_available(self) -> bool:
        return self.running_tasks < self.max_concurrent and not self.queue.empty()


class LLMIntegration:
    def __init__(self):
        pass
        
    def generate_command(self, natural_language: str) -> tuple[str, str]:
        """Generate shell command from natural language input.
        
        Returns:
            tuple: (command, explanation)
        """
        
        prompt = f"""Convert the following natural language request into a safe shell command.
Only return the command, no explanation. Be conservative and safe.

Request: {natural_language}

Command:"""
        
        try:
            command = API_CALL(prompt).strip()
            
            # Basic safety checks
            dangerous_commands = ['rm -rf', 'sudo rm', 'format', 'del /f', 'shutdown', 'reboot']
            for dangerous in dangerous_commands:
                if dangerous in command.lower():
                    return "echo 'Command blocked for safety'", f"Blocked dangerous command: {command}"
            
            explanation = f"Generated command for: {natural_language}"
            return command, explanation
            
        except Exception as e:
            return "echo 'LLM command generation failed'", f"Error: {str(e)}"


class ExecutionLayer:
    def __init__(self, use_llm: bool = False, command_timeout: int = 300):
        self.active_processes: Dict[str, subprocess.Popen] = {}
        self.llm_integration = LLMIntegration() if use_llm else None
        self.command_timeout = command_timeout
        
    def execute_command(self, task: Task) -> tuple[bool, str, str, str]:
        """Execute a terminal command and return (success, stdout, stderr, executed_command)"""
        try:
            # If this is a natural language task and we have LLM integration
            if task.natural_language and self.llm_integration:
                logger.info(f"Processing natural language: '{task.natural_language}'")
                generated_command, explanation = self.llm_integration.generate_command(task.natural_language)
                logger.info(f"Generated command: {generated_command}")
                logger.info(f"Explanation: {explanation}")
                command_to_execute = generated_command
            else:
                command_to_execute = task.command

            logger.info(f"Executing: {command_to_execute}")
            process = subprocess.Popen(
                command_to_execute,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.active_processes[task.id] = process

            stdout, stderr = process.communicate(timeout=self.command_timeout)
            success = process.returncode == 0
            
            # Clean up
            if task.id in self.active_processes:
                del self.active_processes[task.id]
                
            return success, stdout, stderr, command_to_execute
            
        except subprocess.TimeoutExpired as e:
            if task.id in self.active_processes:
                self.active_processes[task.id].kill()
                del self.active_processes[task.id]
            logger.error(f"Command timed out for task {task.id}: {e}")
            return False, "", f"Command timed out after {self.command_timeout} seconds", command_to_execute
        except (OSError, subprocess.SubprocessError) as e:
            if task.id in self.active_processes:
                del self.active_processes[task.id]
            logger.error(f"Command execution failed for task {task.id}: {e}")
            return False, "", str(e), task.command
            
    def kill_task(self, task_id: str) -> bool:
        """Kill a running task"""
        if task_id in self.active_processes:
            try:
                self.active_processes[task_id].terminate()
                del self.active_processes[task_id]
                return True
            except (ProcessLookupError, OSError) as e:
                logger.warning(f"Failed to kill task {task_id}: {e}")
        return False


class SimpleAgent:
    def __init__(self, use_llm: bool = False, command_timeout: int = 300):
        self.lanes: Dict[str, LaneQueue] = {}
        self.execution_layer = ExecutionLayer(use_llm=use_llm, command_timeout=command_timeout)
        self.running = False
        self.task_counter = 0
        self.results: Dict[str, Dict] = {}
        self.use_llm = use_llm
        self.results_lock = threading.Lock()

        # Create default lane
        self.add_lane("default", max_concurrent=2)
        self.add_lane("high_priority", max_concurrent=1)
        
    def add_lane(self, name: str, max_concurrent: int = 1):
        """Add a new lane with specified concurrency"""
        self.lanes[name] = LaneQueue(name, max_concurrent)
        
    def submit_task(self, command: str, priority: TaskPriority = TaskPriority.MEDIUM, 
                   lane: str = "default", metadata: Optional[Dict[str, Any]] = None) -> str:
        """Submit a task to the agent"""
        if lane not in self.lanes:
            raise ValueError(f"Lane '{lane}' does not exist")
            
        self.task_counter += 1
        task_id = f"task_{self.task_counter}"
        
        task = Task(
            id=task_id,
            command=command,
            priority=priority,
            created_at=time.time(),
            lane=lane,
            metadata=metadata
        )
        
        self.lanes[lane].add_task(task)
        logger.info(f"Task {task_id} queued in lane '{lane}' with priority {priority.name}")
        return task_id
        
    def submit_natural_language_task(self, natural_language: str, 
                                    priority: TaskPriority = TaskPriority.MEDIUM,
                                    lane: str = "default", 
                                    metadata: Optional[Dict[str, Any]] = None) -> str:
        """Submit a natural language task that will be converted to a command by LLM"""
        if not self.use_llm:
            raise ValueError("LLM integration is not enabled. Initialize agent with use_llm=True")
            
        if lane not in self.lanes:
            raise ValueError(f"Lane '{lane}' does not exist")
            
        self.task_counter += 1
        task_id = f"task_{self.task_counter}"
        
        task = Task(
            id=task_id,
            command="",  # Will be generated by LLM
            priority=priority,
            created_at=time.time(),
            lane=lane,
            metadata=metadata,
            natural_language=natural_language
        )
        
        self.lanes[lane].add_task(task)
        logger.info(f"Natural language task {task_id} queued in lane '{lane}' with priority {priority.name}")
        logger.info(f"  Request: '{natural_language}'")
        return task_id
        
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get the status of a specific task"""
        return self.results.get(task_id)
        
    def _process_lane(self, lane: LaneQueue):
        """Process tasks in a specific lane"""
        while self.running or lane.is_available():
            if lane.is_available():
                task = lane.get_task()
                if task:
                    lane.task_started()
                    
                    # Execute the task
                    success, stdout, stderr, executed_command = self.execution_layer.execute_command(task)
                    
                    # Store results
                    result_data = {
                        'task_id': task.id,
                        'command': executed_command,
                        'lane': task.lane,
                        'success': success,
                        'stdout': stdout,
                        'stderr': stderr,
                        'completed_at': time.time()
                    }
                    
                    # Add natural language info if applicable
                    if task.natural_language:
                        result_data['natural_language'] = task.natural_language
                        result_data['llm_generated'] = True
                    
                    with self.results_lock:
                        self.results[task.id] = result_data

                    lane.task_completed(success)

                    logger.info(f"Task {task.id} completed: {'SUCCESS' if success else 'FAILED'}")
                    
            time.sleep(0.1)  # Small delay to prevent busy waiting
            
    def start(self):
        """Start the agent loop"""
        if self.running:
            logger.warning("Agent is already running")
            return

        self.running = True
        logger.info("Starting Simple Agent...")

        # Start a thread for each lane
        self.threads = []
        for lane in self.lanes.values():
            thread = threading.Thread(target=self._process_lane, args=(lane,))
            thread.daemon = True
            thread.start()
            self.threads.append(thread)

        logger.info(f"Agent started with {len(self.lanes)} lanes")
        
    def stop(self):
        """Stop the agent loop"""
        if not self.running:
            logger.warning("Agent is not running")
            return

        logger.info("Stopping Simple Agent...")
        self.running = False

        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=1)

        # Kill any remaining processes
        for task_id in list(self.execution_layer.active_processes.keys()):
            self.execution_layer.kill_task(task_id)

        logger.info("Agent stopped")
        
    def get_stats(self) -> Dict:
        """Get agent statistics"""
        stats = {
            'running': self.running,
            'total_tasks': self.task_counter,
            'lanes': {}
        }
        
        for name, lane in self.lanes.items():
            stats['lanes'][name] = {
                'queue_size': lane.queue.qsize(),
                'running_tasks': lane.running_tasks,
                'completed_tasks': lane.completed_tasks,
                'failed_tasks': lane.failed_tasks,
                'max_concurrent': lane.max_concurrent
            }
            
        return stats


# Mock API_CALL function for demonstration
# Replace this with your actual LLM API integration
def API_CALL(prompt: str) -> str:
    """Mock LLM API call that converts natural language to shell commands"""
    import re
    
    # Simple pattern matching for common requests
    patterns = {
        r'list.*file': 'ls -la',
        r'show.*file': 'ls -la',
        r'current.*dir': 'pwd',
        r'where.*am': 'pwd',
        r'print.*hello': 'echo "Hello World"',
        r'say.*hello': 'echo "Hello World"',
        r'create.*dir': 'mkdir test_directory',
        r'make.*dir': 'mkdir test_directory',
        r'current.*time': 'date',
        r'what.*time': 'date',
        r'count.*file': 'ls -1 | wc -l',
        r'how.*file': 'ls -1 | wc -l',
        r'disk.*usage': 'df -h',
        r'memory.*usage': 'free -h' if __import__('subprocess').run('which free', shell=True, capture_output=True).returncode == 0 else 'vm_stat',
    }
    
    prompt_lower = prompt.lower()
    for pattern, command in patterns.items():
        if re.search(pattern, prompt_lower):
            return command
    
    # Default response for unrecognized requests
    return 'echo "Sorry, I could not understand that request"'


if __name__ == "__main__":
    # Example usage
    logger.info("=== Standard Agent Example ===")
    agent = SimpleAgent()
    
    try:
        agent.start()
        
        # Submit some test tasks
        agent.submit_task("echo 'Hello from default lane!'", TaskPriority.MEDIUM, "default")
        agent.submit_task("sleep 2 && echo 'Task completed after 2 seconds'", TaskPriority.LOW, "default")
        agent.submit_task("echo 'High priority task!'", TaskPriority.HIGH, "high_priority")
        agent.submit_task("ls -la", TaskPriority.MEDIUM, "default")
        agent.submit_task("echo 'Critical task!'", TaskPriority.CRITICAL, "high_priority")
        
        # Let the agent run for a bit
        time.sleep(5)
        
        # Print stats
        logger.info("\n=== Agent Stats ===")
        stats = agent.get_stats()
        for lane_name, lane_stats in stats['lanes'].items():
            logger.info(f"Lane '{lane_name}': {lane_stats}")

        # Print task results
        logger.info("\n=== Task Results ===")
        for task_id, result in agent.results.items():
            logger.info(f"\nTask {task_id}:")
            logger.info(f"  Command: {result['command']}")
            logger.info(f"  Success: {result['success']}")
            logger.info(f"  Output: {result['stdout'].strip()}")
            if result['stderr']:
                logger.info(f"  Error: {result['stderr'].strip()}")
                
    except KeyboardInterrupt:
        logger.warning("\nReceived interrupt signal...")
    finally:
        agent.stop()

    # Wait a bit before starting LLM example
    time.sleep(1)

    logger.info("\n\n=== LLM-Enabled Agent Example ===")
    llm_agent = SimpleAgent(use_llm=True)
    
    try:
        llm_agent.start()
        
        # Submit natural language tasks
        llm_agent.submit_natural_language_task("list all files in current directory", TaskPriority.MEDIUM, "default")
        llm_agent.submit_natural_language_task("what time is it?", TaskPriority.HIGH, "high_priority")
        llm_agent.submit_natural_language_task("say hello world", TaskPriority.MEDIUM, "default")
        llm_agent.submit_natural_language_task("show current directory", TaskPriority.LOW, "default")
        llm_agent.submit_natural_language_task("how many files are here?", TaskPriority.HIGH, "high_priority")
        
        # Let the agent run for a bit
        time.sleep(5)
        
        # Print stats
        logger.info("\n=== LLM Agent Stats ===")
        stats = llm_agent.get_stats()
        for lane_name, lane_stats in stats['lanes'].items():
            logger.info(f"Lane '{lane_name}': {lane_stats}")

        # Print task results
        logger.info("\n=== LLM Task Results ===")
        for task_id, result in llm_agent.results.items():
            logger.info(f"\nTask {task_id}:")
            if result.get('natural_language'):
                logger.info(f"  Natural Language: {result['natural_language']}")
                logger.info(f"  LLM Generated: {result.get('llm_generated', False)}")
            logger.info(f"  Command: {result['command']}")
            logger.info(f"  Success: {result['success']}")
            logger.info(f"  Output: {result['stdout'].strip()}")
            if result['stderr']:
                logger.info(f"  Error: {result['stderr'].strip()}")
                
    except KeyboardInterrupt:
        print("\nReceived interrupt signal...")
    finally:
        llm_agent.stop()
