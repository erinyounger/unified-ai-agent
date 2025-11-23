"""Claude CLI process execution and management."""

import asyncio
import json
import platform
from pathlib import Path
from typing import AsyncIterator, Optional

# Import asyncio.subprocess for better async support
from asyncio import subprocess as async_subprocess

from uniaiagent.config import settings
from uniaiagent.core.session_manager import create_workspace
from uniaiagent.exceptions.custom_errors import (
    ClaudeCliError,
    ClaudeCliNotFoundError,
    ErrorContext,
)
from uniaiagent.models.types import ClaudeOptions
from uniaiagent.services import (
    create_request_logger,
    executor_logger,
    log_process_event,
)


class ClaudeExecutor:
    """Claude CLI executor with process management."""

    def __init__(self):
        """Initialize Claude executor."""
        self.active_processes: set[async_subprocess.Process] = set()
        self._cleaning_up = False
        # Don't setup signal handlers here - let Uvicorn/FastAPI handle shutdown
        # Cleanup will be done via lifespan shutdown event in main.py

    async def resolve_claude_path(self) -> Optional[str]:
        """Resolve Claude CLI executable path."""
        env_path = settings.claude_cli_path

        executor_logger.info(
            env_path=env_path,
            type="claude_path_resolution",
            msg="Resolving Claude CLI executable path",
        )

        # If explicit path is provided, try it first
        if env_path:
            # On Windows, try with .cmd extension if it's an npm global install
            if platform.system() == "Windows":
                possible_paths = [env_path, f"{env_path}.cmd", f"{env_path}.bat"]

                for test_path in possible_paths:
                    if Path(test_path).exists():
                        return test_path
            else:
                # On Unix-like systems, check if file exists and is executable
                if Path(env_path).exists():
                    return env_path

        # Try to find 'claude' in PATH using 'where' (Windows) or 'which' (Unix)
        command = "where" if platform.system() == "Windows" else "which"
        try:
            process = await asyncio.create_subprocess_exec(
                command,
                "claude",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0 and stdout:
                return stdout.decode().strip().split("\n")[0]
        except Exception:
            pass

        return None

    def _build_args(
        self,
        session_id: Optional[str],
        options: Optional[ClaudeOptions],
        workspace_path: Path,
    ) -> list[str]:
        """Build command arguments for Claude CLI."""
        args = ["-p", "--verbose", "--output-format", "stream-json"]

        # Add MCP configuration if file exists
        mcp_config_path = settings.resolved_mcp_config_path
        if mcp_config_path and mcp_config_path.exists():
            args.extend(["--mcp-config", str(mcp_config_path)])
            executor_logger.info(
                mcp_config_path=str(mcp_config_path),
                type="mcp_config",
                msg="MCP configuration file found, adding to command",
            )

        if session_id:
            args.extend(["--resume", session_id])

        if options:
            if options.dangerously_skip_permissions:
                args.append("--dangerously-skip-permissions")

            if options.system_prompt:
                args.extend(["--system-prompt", options.system_prompt])

            if options.allowed_tools and len(options.allowed_tools) > 0:
                args.extend(["--allowedTools", ",".join(options.allowed_tools)])

            if options.disallowed_tools and len(options.disallowed_tools) > 0:
                args.extend(["--disallowedTools", ",".join(options.disallowed_tools)])

            if options.skills and len(options.skills) > 0:
                args.extend(["--skills", ",".join(options.skills)])

            if options.skill_options:
                args.extend(["--skillOptions", json.dumps(options.skill_options)])

        return args

    async def _spawn_claude(
        self,
        prompt: str,
        session_id: Optional[str],
        workspace_path: Path,
        options: Optional[ClaudeOptions],
    ) -> async_subprocess.Process:
        """Spawn Claude CLI process using asyncio.subprocess."""
        claude_path = await self.resolve_claude_path()
        command = claude_path or settings.claude_cli_path or "claude"
        args = self._build_args(session_id, options, workspace_path)

        # Use asyncio.create_subprocess_exec for better async support
        # This works better on Windows and handles streaming more reliably
        # On Windows, if command ends with .cmd or doesn't have extension, use shell
        if platform.system() == "Windows" and (command.endswith(".cmd") or (not command.endswith(".exe") and "/" not in command and "\\" not in command)):
            # On Windows, use shell for .cmd files or commands without path
            full_command = f"{command} {' '.join(args)}"
            process = await async_subprocess.create_subprocess_shell(
                full_command,
                cwd=str(workspace_path),
                stdin=async_subprocess.PIPE,
                stdout=async_subprocess.PIPE,
                stderr=async_subprocess.PIPE,
            )
        else:
            # Use exec for better control
            process = await async_subprocess.create_subprocess_exec(
                command,
                *args,
                cwd=str(workspace_path),
                stdin=async_subprocess.PIPE,
                stdout=async_subprocess.PIPE,
                stderr=async_subprocess.PIPE,
            )

        return process

    async def execute_and_stream(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        options: Optional[ClaudeOptions] = None,
    ) -> AsyncIterator[str]:
        """
        Execute Claude command and stream responses.

        Args:
            prompt: The prompt to send to Claude
            session_id: Session ID to resume (optional)
            options: Claude execution options

        Yields:
            JSON lines from Claude CLI stdout

        Raises:
            ClaudeCliError: If Claude CLI execution fails
        """
        # Determine workspace path
        if options and options.workspace:
            workspace_path = await create_workspace(options.workspace)
        elif session_id:
            workspace_path = await create_workspace()
        else:
            workspace_path = await create_workspace()

        # Create request-scoped logger
        request_logger = create_request_logger("claude-execution")

        request_logger.info(
            workspace_path=str(workspace_path),
            workspace=options.workspace if options else "default",
            session_id=session_id,
            prompt_length=len(prompt),
            options={
                "system_prompt": f"{len(options.system_prompt)} characters"
                if options and options.system_prompt
                else None,
                "dangerously_skip_permissions": options.dangerously_skip_permissions
                if options
                else False,
                "allowed_tools_count": len(options.allowed_tools) if options and options.allowed_tools else 0,
                "disallowed_tools_count": len(options.disallowed_tools)
                if options and options.disallowed_tools
                else 0,
            },
            type="execution_start",
            msg="Starting Claude execution",
        )

        timeout_ms = settings.claude_total_timeout_ms

        # Clean up any zombie processes before starting new one
        self._cleanup_zombie_processes()
        
        # Log active processes count for debugging
        if len(self.active_processes) > 0:
            request_logger.warn(
                type="active_processes_warning",
                active_count=len(self.active_processes),
                msg=f"Starting new request with {len(self.active_processes)} active processes",
            )

        try:
            process = await self._spawn_claude(prompt, session_id, workspace_path, options)
        except FileNotFoundError:
            raise ClaudeCliNotFoundError(
                ErrorContext(
                    session_id=session_id,
                    workspace=str(workspace_path),
                )
            )

        # Track this process for cleanup
        self.active_processes.add(process)

        # Wait for process to be ready (similar to TypeScript's 'spawn' event)
        # On Windows, we need to wait a bit for the process to fully initialize
        await asyncio.sleep(0.1)
        
        log_process_event(
            "spawn",
            {
                "pid": process.pid,
                "command": "claude",
            },
            {
                "workspace_path": str(workspace_path),
                "session_id": session_id,
                "prompt_length": len(prompt),
            },
        )

        # Write prompt to stdin (after process is spawned, like TypeScript version)
        try:
            if process.stdin:
                request_logger.info(
                    type="stdin_write_start",
                    prompt_length=len(prompt),
                    msg="Writing prompt to stdin",
                )
                # For asyncio.subprocess, use write() which is async
                process.stdin.write(prompt.encode() if isinstance(prompt, str) else prompt)
                await process.stdin.drain()  # Wait for data to be written
                process.stdin.close()
                await process.stdin.wait_closed()  # Wait for stdin to be closed
                request_logger.info(
                    type="stdin_write_complete",
                    msg="Prompt written to stdin, waiting for output",
                )
                # Give the process a moment to start producing output
                # This is especially important on Windows
                await asyncio.sleep(0.3)
                
                # Check if process is still alive after writing
                if process.returncode is not None:
                    # Process exited immediately, log error and raise exception
                    error_msg = f"Claude process exited immediately with code {process.returncode}"
                    request_logger.error(
                        type="process_exited_early",
                        exit_code=process.returncode,
                        pid=process.pid,
                        msg=error_msg,
                    )
                    # Try to read stderr for error message
                    stderr_output = ""
                    if process.stderr:
                        try:
                            stderr_data = await asyncio.wait_for(process.stderr.read(), timeout=0.5)
                            if stderr_data:
                                stderr_output = stderr_data.decode('utf-8', errors='replace')
                                request_logger.error(
                                    type="process_stderr",
                                    stderr=stderr_output,
                                    msg="Claude process stderr output",
                                )
                        except Exception:
                            pass
                    
                    # Raise exception with error details
                    raise ClaudeCliError(
                        f"{error_msg}. Stderr: {stderr_output}" if stderr_output else error_msg,
                        ErrorContext(session_id=session_id, workspace=str(workspace_path)),
                    )
        except Exception as error:
            request_logger.error(
                error=str(error),
                type="stdin_write_error",
                msg="Failed to write prompt to Claude CLI",
            )
            self.active_processes.discard(process)
            process.terminate()
            raise ClaudeCliError(
                f"Failed to write prompt to Claude CLI: {error}",
                ErrorContext(session_id=session_id, workspace=str(workspace_path)),
            )

        # Set up timeouts
        inactivity_timeout_ms = settings.claude_inactivity_timeout_ms
        kill_timeout_ms = settings.process_kill_timeout_ms

        try:
            async for line in self._read_stdout_with_timeout(
                process, timeout_ms, inactivity_timeout_ms, kill_timeout_ms, session_id, workspace_path
            ):
                try:
                    yield line
                except RuntimeError as e:
                    # Client disconnected (connection closed)
                    if "closed" in str(e).lower() or "broken" in str(e).lower():
                        request_logger.info(
                            type="client_disconnected",
                            pid=process.pid,
                            error=str(e),
                            msg="Client disconnected during streaming, cleanup will happen in finally",
                        )
                        # Don't raise here - let finally block handle cleanup
                        break
                    else:
                        # Other runtime error, re-raise
                        raise
        except (GeneratorExit, asyncio.CancelledError):
            # Client disconnected or request was cancelled, cleanup immediately
            request_logger.info(
                type="client_disconnected",
                pid=process.pid,
                msg="Client disconnected or request cancelled, cleaning up process",
            )
            raise
        except Exception as e:
            # Other exceptions during streaming
            request_logger.error(
                error=str(e),
                type="stream_error",
                pid=process.pid,
                msg="Error during streaming",
            )
            raise
        finally:
            # Cleanup - ensure process is terminated and removed from tracking
            request_logger.info(
                type="stream_cleanup_start",
                pid=process.pid,
                active_processes_count=len(self.active_processes),
                msg="Starting stream cleanup",
            )
            self.active_processes.discard(process)
            if process.returncode is None:  # Process still running
                request_logger.info(
                    type="process_cleanup_start",
                    pid=process.pid,
                    msg="Cleaning up process after stream completion",
                )
                try:
                    # Try to terminate first
                    process.terminate()
                    # Wait with timeout
                    try:
                        await asyncio.wait_for(process.wait(), timeout=kill_timeout_ms / 1000)
                    except asyncio.TimeoutError:
                        # If terminate didn't work, force kill
                        request_logger.warn(
                            type="process_force_kill",
                            pid=process.pid,
                            msg="Process did not terminate, forcing kill",
                        )
                        process.kill()
                        # Wait for kill to complete (should be fast)
                        try:
                            await asyncio.wait_for(process.wait(), timeout=1.0)
                        except asyncio.TimeoutError:
                            # Process still not dead, log but continue
                            request_logger.error(
                                type="process_kill_failed",
                                pid=process.pid,
                                msg="Failed to kill process, may be a zombie",
                            )
                except Exception as cleanup_error:
                    # Log but don't fail - process may already be dead
                    request_logger.error(
                        error=str(cleanup_error),
                        type="process_cleanup_error",
                        pid=process.pid,
                        msg="Error during process cleanup",
                    )

    async def _read_stdout_with_timeout(
        self,
        process: async_subprocess.Process,
        total_timeout_ms: int,
        inactivity_timeout_ms: int,
        kill_timeout_ms: int,
        session_id: Optional[str],
        workspace_path: Path,
    ) -> AsyncIterator[str]:
        """Read stdout with timeout handling using asyncio.StreamReader."""
        import time

        last_activity = time.time()

        async def read_line() -> Optional[str]:
            """Read a line from stdout using StreamReader."""
            nonlocal last_activity
            try:
                if process.stdout:
                    # Use StreamReader.readline() which is async and works better on Windows
                    # Use a shorter timeout to check process status more frequently
                    line_bytes = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=0.1
                    )
                    if line_bytes:
                        last_activity = time.time()
                        line_str = line_bytes.decode('utf-8', errors='replace').rstrip()
                        if line_str:  # Only return non-empty lines
                            return line_str
                    # Check if process has ended
                    if process.returncode is not None:
                        # EOF reached and process has ended
                        return None
                    # Empty line but process still running - might be buffering
                    return None
                return None
            except asyncio.TimeoutError:
                # Timeout is normal, continue reading
                # Check if process has ended during timeout
                if process.returncode is not None:
                    return None
                return None
            except Exception as e:
                executor_logger.error(
                    error=str(e),
                    type="readline_error",
                    msg="Error reading line from stdout",
                )
                import traceback
                executor_logger.error(
                    traceback=traceback.format_exc(),
                    type="readline_traceback",
                    msg="Readline error traceback",
                )
                return None

        # Total timeout task
        async def total_timeout_task():
            await asyncio.sleep(total_timeout_ms / 1000)
            if process.returncode is None:
                log_process_event(
                    "timeout",
                    {"pid": process.pid, "command": "claude"},
                    {
                        "timeout_type": "total",
                        "timeout_ms": total_timeout_ms,
                        "session_id": session_id,
                        "workspace_path": str(workspace_path),
                    },
                )
                process.terminate()
                await asyncio.sleep(kill_timeout_ms / 1000)
                if process.returncode is None:
                    process.kill()

        # Inactivity timeout task
        inactivity_cancelled = False
        async def inactivity_timeout_task():
            nonlocal inactivity_cancelled
            try:
                while process.returncode is None:
                    await asyncio.sleep(0.1)
                    elapsed = (time.time() - last_activity) * 1000
                    if elapsed >= inactivity_timeout_ms:
                        log_process_event(
                            "timeout",
                            {"pid": process.pid, "command": "claude"},
                            {
                                "timeout_type": "inactivity",
                                "inactivity_timeout_ms": inactivity_timeout_ms,
                                "session_id": session_id,
                                "workspace_path": str(workspace_path),
                            },
                        )
                        process.terminate()
                        await asyncio.sleep(kill_timeout_ms / 1000)
                        if process.returncode is None:
                            process.kill()
                        break
            except asyncio.CancelledError:
                inactivity_cancelled = True
                raise

        # Start timeout tasks
        total_timeout = asyncio.create_task(total_timeout_task())
        inactivity_timeout = asyncio.create_task(inactivity_timeout_task())
        
        # Start stderr reading task
        async def read_stderr():
            """Read stderr in background."""
            try:
                if process.stderr:
                    while process.returncode is None:
                        try:
                            line_bytes = await asyncio.wait_for(
                                process.stderr.readline(),
                                timeout=0.1
                            )
                            if line_bytes:
                                error_data = line_bytes.decode('utf-8', errors='replace').rstrip()
                                executor_logger.error(
                                    type="process_stderr",
                                    error_data=error_data,
                                    pid=process.pid,
                                    msg="Claude process stderr output",
                                )
                            elif process.returncode is not None:
                                break
                        except (asyncio.TimeoutError, Exception):
                            continue
            except Exception as e:
                executor_logger.error(
                    error=str(e),
                    type="stderr_read_error",
                    msg="Error reading stderr",
                )
        
        stderr_task = asyncio.create_task(read_stderr())

        # Add initial output timeout: if no output within 5 seconds, consider it a problem
        initial_output_timeout = 5.0  # 5 seconds
        initial_output_start = time.time()
        has_received_output = False
        initial_timeout_triggered = False
        
        # Create a task to check initial output timeout
        # Use an event to signal timeout instead of a flag
        initial_timeout_event = asyncio.Event()
        
        async def initial_output_timeout_task():
            """Check for initial output timeout."""
            await asyncio.sleep(initial_output_timeout)
            if not has_received_output and process.returncode is None:
                nonlocal initial_timeout_triggered
                initial_timeout_triggered = True
                error_msg = f"Claude process started but produced no output within {initial_output_timeout} seconds"
                executor_logger.error(
                    type="initial_output_timeout",
                    timeout=initial_output_timeout,
                    pid=process.pid,
                    has_received_output=has_received_output,
                    msg=error_msg,
                )
                # Log process status
                executor_logger.error(
                    type="process_status_check",
                    pid=process.pid,
                    returncode=process.returncode,
                    msg="Process status during initial timeout",
                )
                # Terminate the process
                try:
                    process.terminate()
                    executor_logger.error(
                        type="process_terminated",
                        pid=process.pid,
                        msg="Terminated process due to initial output timeout",
                    )
                except Exception as e:
                    executor_logger.error(
                        error=str(e),
                        type="process_terminate_error",
                        pid=process.pid,
                        msg="Error terminating process",
                    )
                # Set event to signal timeout
                initial_timeout_event.set()
        
        initial_timeout_task_obj = asyncio.create_task(initial_output_timeout_task())

        try:
            # Give process a moment to start producing output after stdin is closed
            await asyncio.sleep(0.3)

            # Log that we're starting to read output
            executor_logger.info(
                type="stream_reading_start",
                pid=process.pid,
                msg="Starting to read output from Claude process",
            )

            consecutive_empty_reads = 0
            max_empty_reads = 20  # Allow some empty reads before checking process status

            while True:
                # Check if initial timeout was triggered (check event first for immediate response)
                if initial_timeout_event.is_set() or initial_timeout_triggered:
                    # Try to read stderr for error message
                    stderr_output = ""
                    if process.stderr:
                        try:
                            # Try to read any available stderr
                            stderr_data = await asyncio.wait_for(process.stderr.read(1024), timeout=0.5)
                            if stderr_data:
                                stderr_output = stderr_data.decode('utf-8', errors='replace')
                                executor_logger.error(
                                    type="process_stderr_timeout",
                                    stderr=stderr_output,
                                    msg="Stderr output during timeout",
                                )
                        except Exception:
                            pass
                    
                    # Raise exception
                    error_msg = f"Claude process started but produced no output within {initial_output_timeout} seconds"
                    raise ClaudeCliError(
                        f"{error_msg}. Stderr: {stderr_output}" if stderr_output else error_msg,
                        ErrorContext(session_id=session_id, workspace=str(workspace_path)),
                    )
                
                # Check if process has ended (for asyncio.subprocess, use returncode)
                if process.returncode is not None:
                    # Process has ended, try to read any remaining data
                    try:
                        # Read remaining data with a short timeout
                        while True:
                            remaining_line = await asyncio.wait_for(read_line(), timeout=0.1)
                            if remaining_line:
                                yield remaining_line
                            else:
                                break
                    except (asyncio.TimeoutError, Exception):
                        pass
                    break

                # Try to read a line with timeout, but also check for initial timeout event
                # Use asyncio.wait to wait for either read_line or timeout event
                read_task = asyncio.create_task(read_line())
                timeout_wait_task = asyncio.create_task(initial_timeout_event.wait())
                
                done, pending = await asyncio.wait(
                    [read_task, timeout_wait_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=0.2  # Maximum wait time before checking again
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
                
                # If timeout event was triggered, handle it
                if timeout_wait_task in done or initial_timeout_event.is_set():
                    # Will be handled at start of next iteration
                    continue
                
                # If read completed, process the line
                if read_task in done:
                    try:
                        line = await read_task
                        if line:
                            has_received_output = True  # Mark that we've received output
                            initial_timeout_task_obj.cancel()  # Cancel initial timeout task
                            consecutive_empty_reads = 0
                            executor_logger.info(
                                type="stream_line_received",
                                pid=process.pid,
                                line_preview=line[:100],
                                msg="Received output line from Claude process",
                            )

                            # Check if this is a result message indicating completion
                            # Claude sends {"type":"result",...} when it finishes
                            if '"type":"result"' in line:
                                executor_logger.info(
                                    type="process_completed_with_result",
                                    pid=process.pid,
                                    msg="Claude process completed (result message received), breaking from stream loop",
                                )
                                yield line
                                # Break immediately to trigger cleanup
                                break
                            else:
                                yield line
                        else:
                            consecutive_empty_reads += 1
                            # Log every 5 empty reads to avoid spam
                            if consecutive_empty_reads % 5 == 0:
                                executor_logger.debug(
                                    type="empty_reads",
                                    pid=process.pid,
                                    consecutive_empty_reads=consecutive_empty_reads,
                                    max_empty_reads=max_empty_reads,
                                    process_running=process.returncode is None,
                                    msg=f"Empty reads: {consecutive_empty_reads}/{max_empty_reads}",
                                )
                            # If process has ended, break
                            if process.returncode is not None:
                                executor_logger.info(
                                    type="process_ended_during_read",
                                    pid=process.pid,
                                    returncode=process.returncode,
                                    msg="Process ended during reading",
                                )
                                break
                            # Check if process output has completed
                            # If we've received output and no more for a while, consider it complete
                            if has_received_output and consecutive_empty_reads > 50:  # About 5 seconds
                                executor_logger.info(
                                    type="process_completed_no_more_output",
                                    pid=process.pid,
                                    consecutive_empty_reads=consecutive_empty_reads,
                                    msg="No more output from Claude process, considering complete",
                                )
                                break
                            # If too many empty reads, check if process is still alive
                            if consecutive_empty_reads >= max_empty_reads:
                                # Check process status
                                if process.returncode is not None:
                                    break
                                # Reset counter and continue
                                consecutive_empty_reads = 0
                                # Small delay to avoid busy waiting
                                await asyncio.sleep(0.1)
                    except Exception as error:
                        executor_logger.error(
                            error=str(error),
                            type="stdout_read_error",
                            msg="Error reading from Claude CLI stdout",
                        )
                        break
        finally:
            # Cancel all background tasks immediately
            total_timeout.cancel()
            inactivity_timeout.cancel()
            stderr_task.cancel()
            initial_timeout_task_obj.cancel()

            # Wait for tasks to finish cancellation with a short timeout
            # Don't use gather() as it might hang if a task doesn't handle cancellation properly
            async def wait_for_task_with_timeout(task: asyncio.Task, timeout_seconds: float = 0.3):
                """Wait for task to finish with timeout."""
                try:
                    await asyncio.wait_for(task, timeout=timeout_seconds)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    # Expected - task was cancelled or timed out
                    pass
                except Exception:
                    # Other exceptions - log but continue
                    pass

            # Wait for each task individually with a short timeout
            await wait_for_task_with_timeout(total_timeout, 0.2)
            await wait_for_task_with_timeout(inactivity_timeout, 0.2)
            await wait_for_task_with_timeout(stderr_task, 0.2)
            await wait_for_task_with_timeout(initial_timeout_task_obj, 0.2)

            # Log process exit
            exit_code = process.returncode
            log_process_event(
                "exit",
                {
                    "pid": process.pid,
                    "command": "claude",
                    "exit_code": exit_code,
                },
                {
                    "session_id": session_id,
                    "workspace_path": str(workspace_path),
                },
            )

    def _cleanup_zombie_processes(self) -> None:
        """Check for and clean up zombie processes."""
        for proc in list(self.active_processes):
            # For asyncio.subprocess.Process, check returncode
            if proc.returncode is not None:
                self.active_processes.discard(proc)

    def cleanup_active_processes(self) -> None:
        """Cleanup function to kill all active processes."""
        # Prevent multiple simultaneous cleanup calls
        if self._cleaning_up:
            return
        self._cleaning_up = True
        
        executor_logger.info(
            active_process_count=len(self.active_processes),
            type="process_cleanup",
            msg=f"Cleaning up {len(self.active_processes)} active processes",
        )

        kill_timeout_ms = settings.process_kill_timeout_ms

        for proc in list(self.active_processes):
            # For asyncio.subprocess.Process, check returncode
            if proc.returncode is None:  # Process still running
                try:
                    log_process_event(
                        "signal",
                        {
                            "pid": proc.pid,
                            "signal": "SIGTERM",
                            "command": "claude",
                        },
                        {"reason": "cleanup"},
                    )
                    proc.terminate()
                    
                    # For asyncio.subprocess.Process, we need to check returncode
                    # But in signal handler, we can't await, so we'll kill immediately
                    # The terminate() should work, but if not, kill() will force it
                    # Note: On Windows, terminate() may not work immediately, so we kill() right away
                    if platform.system() == "Windows":
                        # On Windows, terminate() may not work, so kill immediately
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    else:
                        # On Unix, give terminate() a brief moment, then kill if needed
                        import time
                        time.sleep(0.1)  # Brief wait
                        if proc.returncode is None:
                            log_process_event(
                                "signal",
                                {
                                    "pid": proc.pid,
                                    "signal": "SIGKILL",
                                    "command": "claude",
                                },
                                {"reason": "force_cleanup"},
                            )
                            proc.kill()
                except Exception as e:
                    executor_logger.error(
                        error=str(e),
                        pid=proc.pid,
                        type="process_kill_error",
                        msg="Error killing process",
                    )

        self.active_processes.clear()

    # Signal handlers removed - let Uvicorn/FastAPI handle shutdown signals
    # Cleanup is done via FastAPI lifespan shutdown event in main.py


# Global executor instance
executor = ClaudeExecutor()
