"""Mock telnet server for testing."""

import asyncio
import logging
import re
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


class MockTelnetServer:
    """
    Mock telnet server for testing telnet driver.
    
    Simulates a basic telnet server with:
    - Login authentication
    - Command execution
    - Configurable responses
    - Connection state tracking
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2323,
        username: str = "admin",
        password: str = "password",
        prompt: str = "mock$ "
    ):
        """
        Initialize mock server.
        
        Args:
            host: Server host
            port: Server port
            username: Expected username
            password: Expected password
            prompt: Shell prompt
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.prompt = prompt
        
        self.server = None
        self.clients: List[asyncio.StreamWriter] = []
        self.command_handlers: Dict[str, Callable] = {}
        self.command_responses: Dict[str, str] = {}
        
        # Default command responses
        self._setup_default_responses()
    
    def _setup_default_responses(self):
        """Setup default command responses."""
        self.command_responses = {
            "echo alive": "alive",
            "pwd": "/home/test",
            "ls": "file1.txt\nfile2.txt\ntest.bin",
            "whoami": self.username,
            "uname -a": "Linux mock-board 5.10.0 #1 SMP Mon Jan 1 00:00:00 UTC 2024 aarch64 GNU/Linux",
            "cat /proc/cpuinfo": "processor : 0\nmodel name : Mock CPU\ncpu MHz : 1000.0",
            "free -m": "              total        used        free\nMem:           2048         512        1536",
            "df -h": "Filesystem      Size  Used Avail Use% Mounted on\n/dev/root        16G  4.0G   12G  25% /",
            "exit": "",
        }
        
        # Setup regex patterns for parameterized commands
        self.add_regex_handler(r"^echo\s+(.+)$", lambda m: m.group(1))
        self.add_regex_handler(r"^cat\s+(.+)$", self._handle_cat)
        self.add_regex_handler(r"^wc\s+-c\s+(.+)$", self._handle_wc)
        self.add_regex_handler(r"^ls\s+-la\s+(.*)$", self._handle_ls_la)
    
    def add_command_response(self, command: str, response: str):
        """Add a custom command response."""
        self.command_responses[command] = response
    
    def add_regex_handler(self, pattern: str, handler: Callable):
        """Add a regex-based command handler."""
        self.command_handlers[pattern] = handler
    
    def _handle_cat(self, match) -> str:
        """Handle cat command."""
        filename = match.group(1)
        if filename == "/etc/passwd":
            return "root:x:0:0:root:/root:/bin/bash\ntest:x:1000:1000::/home/test:/bin/bash"
        elif filename.endswith(".txt"):
            return f"Content of {filename}"
        else:
            return f"cat: {filename}: No such file or directory"
    
    def _handle_wc(self, match) -> str:
        """Handle wc command."""
        filename = match.group(1)
        if "test" in filename:
            return "1234 " + filename  # Mock file size
        return "0 " + filename
    
    def _handle_ls_la(self, match) -> str:
        """Handle ls -la command."""
        path = match.group(1) or "."
        return f"""total 16
drwxr-xr-x 2 test test 4096 Jan  1 00:00 .
drwxr-xr-x 3 test test 4096 Jan  1 00:00 ..
-rw-r--r-- 1 test test 1234 Jan  1 00:00 file1.txt
-rw-r--r-- 1 test test 5678 Jan  1 00:00 file2.txt"""
    
    async def start(self):
        """Start the mock server."""
        self.server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port
        )
        
        logger.info(f"Mock telnet server started on {self.host}:{self.port}")
        
        async with self.server:
            await self.server.serve_forever()
    
    async def start_background(self):
        """Start server in background."""
        self.server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port
        )
        logger.info(f"Mock telnet server started in background on {self.host}:{self.port}")
    
    async def stop(self):
        """Stop the mock server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Mock telnet server stopped")
        
        # Close all client connections
        for client in self.clients:
            client.close()
            await client.wait_closed()
        self.clients.clear()
    
    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle client connection."""
        addr = writer.get_extra_info('peername')
        logger.info(f"Client connected from {addr}")
        self.clients.append(writer)
        
        try:
            # Handle login if credentials are set
            if self.username:
                # Send login prompt
                writer.write(b"login: ")
                await writer.drain()
                
                # Read username
                username_data = await reader.readline()
                username = username_data.decode().strip()
                
                if username != self.username:
                    writer.write(b"Login incorrect\n")
                    await writer.drain()
                    return
                
                # Send password prompt if password is set
                if self.password:
                    writer.write(b"Password: ")
                    await writer.drain()
                    
                    # Read password
                    password_data = await reader.readline()
                    password = password_data.decode().strip()
                    
                    if password != self.password:
                        writer.write(b"Login incorrect\n")
                        await writer.drain()
                        return
            
            # Send initial prompt
            writer.write(self.prompt.encode())
            await writer.drain()
            
            # Command loop
            while True:
                # Read command
                data = await reader.readline()
                if not data:
                    break
                
                command = data.decode().strip()
                logger.debug(f"Received command: {command}")
                
                # Handle exit
                if command == "exit":
                    break
                
                # Echo command (simulate terminal echo)
                writer.write(data)
                await writer.drain()
                
                # Special handling for blocking_command (for timeout testing)
                if command == "blocking_command":
                    # Don't send response or prompt - just hang
                    await asyncio.sleep(10)
                    continue
                
                # Process command
                response = self._process_command(command)
                
                # Send response
                if response:
                    writer.write((response + "\n").encode())
                    await writer.drain()
                
                # Send prompt
                writer.write(self.prompt.encode())
                await writer.drain()
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            # Clean up
            writer.close()
            await writer.wait_closed()
            if writer in self.clients:
                self.clients.remove(writer)
            logger.info(f"Client disconnected from {addr}")
    
    def _process_command(self, command: str) -> str:
        """
        Process command and return response.
        
        Args:
            command: Command to process
            
        Returns:
            Command response
        """
        # Check exact match first
        if command in self.command_responses:
            return self.command_responses[command]
        
        # Check regex handlers
        for pattern, handler in self.command_handlers.items():
            match = re.match(pattern, command)
            if match:
                try:
                    return handler(match)
                except Exception as e:
                    return f"Error: {e}"
        
        # Default response for unknown commands
        return f"{command}: command not found"


class MockBoardSimulator(MockTelnetServer):
    """
    Enhanced mock server that simulates a real board.
    
    Adds:
    - File system simulation
    - Process simulation
    - Test execution simulation
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Simulated file system
        self.filesystem: Dict[str, str] = {
            "/home/test/test.txt": "Test file content",
            "/home/test/data.bin": "Binary data here",
            "/tmp/test_output.log": "",
        }
        
        # Simulated processes
        self.processes: List[str] = []
        
        # Additional handlers
        self._setup_board_handlers()
    
    def _setup_board_handlers(self):
        """Setup board-specific handlers."""
        # File operations
        self.add_regex_handler(
            r"^echo\s+'(.+)'\s*\|\s*base64\s+-d\s*>\s*(.+)$",
            self._handle_base64_decode
        )
        
        # Process operations
        self.add_regex_handler(r"^ps\s+aux$", self._handle_ps)
        self.add_regex_handler(r"^kill\s+(\d+)$", self._handle_kill)
        
        # Test execution
        self.add_regex_handler(r"^\.\/(.+)$", self._handle_test_execution)
        self.add_regex_handler(r"^/home/test/(.+)$", self._handle_test_execution)
    
    def _handle_base64_decode(self, match) -> str:
        """Handle base64 decode to file."""
        import base64
        encoded = match.group(1)
        filepath = match.group(2)
        
        try:
            decoded = base64.b64decode(encoded)
            self.filesystem[filepath] = decoded.decode('utf-8', errors='ignore')
            return ""
        except Exception as e:
            return f"base64: invalid input: {e}"
    
    def _handle_ps(self, match) -> str:
        """Handle ps command."""
        output = "PID   USER     TIME  COMMAND\n"
        output += "1     root     0:00  /sbin/init\n"
        output += "100   test     0:00  /bin/bash\n"
        
        for i, proc in enumerate(self.processes, start=1000):
            output += f"{i}   test     0:00  {proc}\n"
        
        return output
    
    def _handle_kill(self, match) -> str:
        """Handle kill command."""
        pid = int(match.group(1))
        if pid >= 1000 and pid < 1000 + len(self.processes):
            proc_index = pid - 1000
            removed = self.processes.pop(proc_index)
            return f"Killed process {pid} ({removed})"
        return f"kill: ({pid}) - No such process"
    
    def _handle_test_execution(self, match) -> str:
        """Simulate test execution."""
        test_name = match.group(1)
        
        # Add to process list
        self.processes.append(test_name)
        
        # Simulate test output
        output = f"""Starting test: {test_name}
[TEST] Initializing...
[TEST] Running test cases...
[TEST] Test 1: PASS
[TEST] Test 2: PASS
[TEST] Test 3: PASS
[TEST] All tests completed successfully
Test result: PASS"""
        
        # Remove from process list
        if test_name in self.processes:
            self.processes.remove(test_name)
        
        return output