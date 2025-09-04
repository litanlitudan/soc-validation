"""Telnet driver for direct board communication."""

import asyncio
import logging
import re
import time
from typing import Optional, List, Tuple, Union
from enum import Enum
import telnetlib
from asyncio import StreamReader, StreamWriter
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class TelnetConnectionError(Exception):
    """Raised when telnet connection fails."""
    pass


class TelnetTimeoutError(Exception):
    """Raised when telnet operation times out."""
    pass


class ConnectionState(Enum):
    """Connection state enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    ERROR = "error"


@dataclass
class TelnetConfig:
    """Telnet connection configuration."""
    host: str
    port: int = 23
    username: Optional[str] = None
    password: Optional[str] = None
    login_prompt: str = "login:"
    password_prompt: str = "Password:"
    shell_prompt: str = r"[$#>]\s*$"  # Matches common shell prompts
    timeout: int = 30
    connect_timeout: int = 10
    retry_count: int = 3
    retry_delay: float = 1.0
    encoding: str = "utf-8"
    buffer_size: int = 4096


class TelnetDriver:
    """
    Async telnet driver for board communication.
    
    Features:
    - Async connection management
    - Automatic login handling
    - Command execution with timeout
    - Output buffering and capture
    - Retry logic for resilience
    - Prompt detection
    """
    
    def __init__(self, config: TelnetConfig):
        """
        Initialize telnet driver.
        
        Args:
            config: Telnet configuration
        """
        self.config = config
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self.state = ConnectionState.DISCONNECTED
        self._output_buffer: List[str] = []
        self._command_history: List[Tuple[str, str]] = []  # (command, output) pairs
        
        logger.info(f"TelnetDriver initialized for {config.host}:{config.port}")
    
    async def connect(self) -> None:
        """
        Establish telnet connection with retry logic.
        
        Raises:
            TelnetConnectionError: If connection fails after retries
        """
        if self.state in [ConnectionState.CONNECTED, ConnectionState.AUTHENTICATED]:
            logger.debug("Already connected")
            return
        
        self.state = ConnectionState.CONNECTING
        last_error = None
        
        for attempt in range(self.config.retry_count):
            try:
                logger.info(f"Connecting to {self.config.host}:{self.config.port} (attempt {attempt + 1})")
                
                # Establish connection
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.config.host, self.config.port),
                    timeout=self.config.connect_timeout
                )
                
                self.state = ConnectionState.CONNECTED
                logger.info(f"Connected to {self.config.host}:{self.config.port}")
                
                # Perform login if credentials provided
                if self.config.username:
                    await self._login()
                
                return
                
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(f"Connection timeout (attempt {attempt + 1})")
            except Exception as e:
                last_error = e
                logger.warning(f"Connection failed (attempt {attempt + 1}): {e}")
            
            if attempt < self.config.retry_count - 1:
                await asyncio.sleep(self.config.retry_delay)
        
        self.state = ConnectionState.ERROR
        raise TelnetConnectionError(
            f"Failed to connect to {self.config.host}:{self.config.port} after {self.config.retry_count} attempts: {last_error}"
        )
    
    async def _login(self) -> None:
        """
        Perform login sequence.
        
        Raises:
            TelnetTimeoutError: If login times out
            TelnetConnectionError: If login fails
        """
        try:
            # Wait for login prompt
            output = await self._read_until(
                self.config.login_prompt,
                timeout=self.config.timeout
            )
            
            # Send username
            await self._write(self.config.username + "\n")
            
            # If password required
            if self.config.password:
                # Wait for password prompt
                output = await self._read_until(
                    self.config.password_prompt,
                    timeout=self.config.timeout
                )
                
                # Send password
                await self._write(self.config.password + "\n")
            
            # Wait for shell prompt
            output = await self._read_until_regex(
                self.config.shell_prompt,
                timeout=self.config.timeout
            )
            
            self.state = ConnectionState.AUTHENTICATED
            logger.info(f"Successfully logged in as {self.config.username}")
            
        except asyncio.TimeoutError:
            raise TelnetTimeoutError(f"Login timeout for {self.config.username}")
        except Exception as e:
            raise TelnetConnectionError(f"Login failed: {e}")
    
    async def execute_command(
        self,
        command: str,
        timeout: Optional[int] = None,
        expect_prompt: bool = True
    ) -> str:
        """
        Execute command and return output.
        
        Args:
            command: Command to execute
            timeout: Command timeout (uses config default if None)
            expect_prompt: Whether to wait for prompt after command
            
        Returns:
            Command output
            
        Raises:
            TelnetConnectionError: If not connected
            TelnetTimeoutError: If command times out
        """
        if self.state not in [ConnectionState.CONNECTED, ConnectionState.AUTHENTICATED]:
            raise TelnetConnectionError("Not connected")
        
        timeout = timeout or self.config.timeout
        
        try:
            # Clear any pending output
            await self._clear_buffer()
            
            # Send command
            await self._write(command + "\n")
            logger.debug(f"Executing: {command}")
            
            # Read output until prompt or timeout
            if expect_prompt:
                output = await self._read_until_regex(
                    self.config.shell_prompt,
                    timeout=timeout
                )
            else:
                # Just read available output with timeout
                output = await self._read_with_timeout(timeout)
            
            # Store in command history
            self._command_history.append((command, output))
            
            # Remove command echo and prompt from output
            lines = output.split('\n')
            if lines and command in lines[0]:
                lines = lines[1:]  # Remove command echo
            if expect_prompt and lines and re.search(self.config.shell_prompt, lines[-1]):
                lines = lines[:-1]  # Remove prompt
            
            result = '\n'.join(lines).strip()
            logger.debug(f"Command output ({len(result)} bytes)")
            
            return result
            
        except asyncio.TimeoutError:
            raise TelnetTimeoutError(f"Command '{command}' timed out after {timeout} seconds")
    
    async def execute_commands(
        self,
        commands: List[str],
        timeout: Optional[int] = None
    ) -> List[str]:
        """
        Execute multiple commands sequentially.
        
        Args:
            commands: List of commands
            timeout: Timeout for each command
            
        Returns:
            List of outputs
        """
        results = []
        for cmd in commands:
            output = await self.execute_command(cmd, timeout)
            results.append(output)
        return results
    
    async def send_file(
        self,
        local_path: str,
        remote_path: str,
        transfer_method: str = "base64"
    ) -> bool:
        """
        Send file to board using base64 encoding.
        
        Args:
            local_path: Local file path
            remote_path: Remote destination path
            transfer_method: Transfer method (only base64 supported)
            
        Returns:
            True if successful
        """
        import base64
        
        try:
            # Read local file
            with open(local_path, 'rb') as f:
                content = f.read()
            
            if transfer_method == "base64":
                # Encode to base64
                encoded = base64.b64encode(content).decode('ascii')
                
                # Send to board using echo and base64 decode
                # Split into chunks to avoid command line limits
                chunk_size = 1024
                chunks = [encoded[i:i+chunk_size] for i in range(0, len(encoded), chunk_size)]
                
                # Create file with first chunk
                if chunks:
                    await self.execute_command(
                        f"echo '{chunks[0]}' | base64 -d > {remote_path}"
                    )
                    
                    # Append remaining chunks
                    for chunk in chunks[1:]:
                        await self.execute_command(
                            f"echo '{chunk}' | base64 -d >> {remote_path}"
                        )
                
                # Verify file
                size_output = await self.execute_command(f"wc -c {remote_path}")
                remote_size = int(size_output.split()[0]) if size_output else 0
                
                if remote_size == len(content):
                    logger.info(f"Successfully transferred {local_path} to {remote_path}")
                    return True
                else:
                    logger.error(f"File size mismatch: local={len(content)}, remote={remote_size}")
                    return False
            else:
                raise ValueError(f"Unsupported transfer method: {transfer_method}")
                
        except Exception as e:
            logger.error(f"File transfer failed: {e}")
            return False
    
    async def read_file(self, remote_path: str) -> Optional[str]:
        """
        Read file from board.
        
        Args:
            remote_path: Remote file path
            
        Returns:
            File content or None if failed
        """
        try:
            output = await self.execute_command(f"cat {remote_path}")
            return output
        except Exception as e:
            logger.error(f"Failed to read {remote_path}: {e}")
            return None
    
    async def disconnect(self) -> None:
        """Disconnect from board."""
        if self.writer:
            try:
                # Send exit command
                await self._write("exit\n")
                await asyncio.sleep(0.5)
                
                # Close connection
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
        
        self.reader = None
        self.writer = None
        self.state = ConnectionState.DISCONNECTED
        logger.info(f"Disconnected from {self.config.host}:{self.config.port}")
    
    async def is_alive(self) -> bool:
        """
        Check if connection is alive.
        
        Returns:
            True if connected and responsive
        """
        if self.state not in [ConnectionState.CONNECTED, ConnectionState.AUTHENTICATED]:
            return False
        
        try:
            # Send echo command to test connection
            output = await self.execute_command("echo alive", timeout=5)
            return "alive" in output
        except Exception:
            return False
    
    def get_command_history(self) -> List[Tuple[str, str]]:
        """Get command history."""
        return self._command_history.copy()
    
    def clear_history(self) -> None:
        """Clear command history."""
        self._command_history.clear()
    
    # Private helper methods
    
    async def _write(self, data: str) -> None:
        """Write data to connection."""
        if not self.writer:
            raise TelnetConnectionError("Not connected")
        
        self.writer.write(data.encode(self.config.encoding))
        await self.writer.drain()
    
    async def _read_until(self, pattern: str, timeout: int) -> str:
        """Read until pattern is found."""
        if not self.reader:
            raise TelnetConnectionError("Not connected")
        
        start_time = time.time()
        buffer = ""
        
        while time.time() - start_time < timeout:
            try:
                # Read available data
                data = await asyncio.wait_for(
                    self.reader.read(self.config.buffer_size),
                    timeout=0.1
                )
                
                if data:
                    text = data.decode(self.config.encoding, errors='ignore')
                    buffer += text
                    self._output_buffer.append(text)
                    
                    if pattern in buffer:
                        return buffer
            except asyncio.TimeoutError:
                continue
        
        raise asyncio.TimeoutError(f"Pattern '{pattern}' not found within {timeout} seconds")
    
    async def _read_until_regex(self, pattern: str, timeout: int) -> str:
        """Read until regex pattern matches."""
        if not self.reader:
            raise TelnetConnectionError("Not connected")
        
        regex = re.compile(pattern)
        start_time = time.time()
        buffer = ""
        
        while time.time() - start_time < timeout:
            try:
                # Read available data
                data = await asyncio.wait_for(
                    self.reader.read(self.config.buffer_size),
                    timeout=0.1
                )
                
                if data:
                    text = data.decode(self.config.encoding, errors='ignore')
                    buffer += text
                    self._output_buffer.append(text)
                    
                    if regex.search(buffer):
                        return buffer
            except asyncio.TimeoutError:
                continue
        
        raise asyncio.TimeoutError(f"Regex pattern '{pattern}' not matched within {timeout} seconds")
    
    async def _read_with_timeout(self, timeout: int) -> str:
        """Read all available data within timeout."""
        if not self.reader:
            raise TelnetConnectionError("Not connected")
        
        start_time = time.time()
        buffer = ""
        last_read_time = start_time
        
        while time.time() - start_time < timeout:
            try:
                # Read available data
                data = await asyncio.wait_for(
                    self.reader.read(self.config.buffer_size),
                    timeout=0.1
                )
                
                if data:
                    text = data.decode(self.config.encoding, errors='ignore')
                    buffer += text
                    self._output_buffer.append(text)
                    last_read_time = time.time()
                elif time.time() - last_read_time > 1.0:
                    # No data for 1 second, assume command completed
                    break
            except asyncio.TimeoutError:
                if time.time() - last_read_time > 1.0:
                    break
        
        return buffer
    
    async def _clear_buffer(self) -> None:
        """Clear any pending data in the read buffer."""
        if not self.reader:
            return
        
        try:
            # Read any available data without blocking
            while True:
                data = await asyncio.wait_for(
                    self.reader.read(self.config.buffer_size),
                    timeout=0.01
                )
                if not data:
                    break
        except asyncio.TimeoutError:
            pass
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()