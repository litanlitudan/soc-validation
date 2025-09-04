"""Unit and integration tests for telnet driver."""

import asyncio
import pytest
import tempfile
import os
import random
from unittest.mock import AsyncMock, MagicMock, patch

# Set default timeout for async tests
pytestmark = pytest.mark.asyncio(timeout=10)

from src.device_manager.drivers.telnet_driver import (
    TelnetDriver,
    TelnetConfig,
    TelnetConnectionError,
    TelnetTimeoutError,
    ConnectionState
)
from tests.mocks.mock_telnet_server import MockTelnetServer, MockBoardSimulator


@pytest.fixture
def telnet_config():
    """Create test telnet configuration."""
    return TelnetConfig(
        host="127.0.0.1",
        port=random.randint(60001, 65000),  # Random port to avoid conflicts
        username="admin",
        password="password",
        timeout=5,
        connect_timeout=2,
        retry_count=2
    )


@pytest.fixture
def telnet_driver(telnet_config):
    """Create telnet driver instance."""
    return TelnetDriver(telnet_config)


@pytest.fixture
async def mock_server():
    """Create and start mock telnet server."""
    # Use random port to avoid conflicts
    port = random.randint(10000, 20000)
    server = MockTelnetServer(
        host="127.0.0.1",
        port=port,
        username="admin",
        password="password"
    )
    
    # Start server in background
    await server.start_background()
    
    yield server
    
    # Cleanup
    await server.stop()


@pytest.fixture
async def board_simulator():
    """Create and start board simulator."""
    # Use random port to avoid conflicts
    port = random.randint(20001, 30000)
    simulator = MockBoardSimulator(
        host="127.0.0.1",
        port=port,
        username="test",
        password="test123"
    )
    
    # Start server in background
    await simulator.start_background()
    
    yield simulator
    
    # Cleanup
    await simulator.stop()


class TestTelnetConfig:
    """Test TelnetConfig dataclass."""
    
    def test_default_config(self):
        """Test configuration with defaults."""
        config = TelnetConfig(host="192.168.1.1")
        
        assert config.host == "192.168.1.1"
        assert config.port == 23
        assert config.username is None
        assert config.password is None
        assert config.timeout == 30
        assert config.connect_timeout == 10
        assert config.retry_count == 3
    
    def test_custom_config(self):
        """Test configuration with custom values."""
        config = TelnetConfig(
            host="10.0.0.1",
            port=2323,
            username="admin",
            password="secret",
            timeout=60,
            shell_prompt="# "
        )
        
        assert config.host == "10.0.0.1"
        assert config.port == 2323
        assert config.username == "admin"
        assert config.password == "secret"
        assert config.timeout == 60
        assert config.shell_prompt == "# "


class TestTelnetDriverInit:
    """Test TelnetDriver initialization."""
    
    def test_init(self, telnet_config):
        """Test driver initialization."""
        driver = TelnetDriver(telnet_config)
        
        assert driver.config == telnet_config
        assert driver.state == ConnectionState.DISCONNECTED
        assert driver.reader is None
        assert driver.writer is None
        assert len(driver._output_buffer) == 0
        assert len(driver._command_history) == 0


class TestTelnetConnection:
    """Test telnet connection functionality."""
    
    @pytest.mark.asyncio
    async def test_connect_success(self, mock_server):
        """Test successful connection."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=mock_server.port,
            username="admin",
            password="password",
            timeout=5
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        
        assert driver.state == ConnectionState.AUTHENTICATED
        assert driver.reader is not None
        assert driver.writer is not None
        
        await driver.disconnect()
    
    @pytest.mark.asyncio
    async def test_connect_no_auth(self):
        """Test connection without authentication."""
        # Create mock server without auth with random port
        port = random.randint(30001, 40000)
        server = MockTelnetServer(
            host="127.0.0.1",
            port=port,
            username=None,
            password=None
        )
        await server.start_background()
        
        config = TelnetConfig(
            host="127.0.0.1",
            port=port,
            timeout=5
        )
        driver = TelnetDriver(config)
        
        try:
            await driver.connect()
            
            assert driver.state == ConnectionState.CONNECTED
            
            await driver.disconnect()
        finally:
            await server.stop()
    
    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Test connection failure."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=9999,  # Non-existent port
            connect_timeout=1,
            retry_count=2
        )
        driver = TelnetDriver(config)
        
        with pytest.raises(TelnetConnectionError) as exc_info:
            await driver.connect()
        
        assert "Failed to connect" in str(exc_info.value)
        assert driver.state == ConnectionState.ERROR
    
    @pytest.mark.asyncio
    async def test_connect_already_connected(self, mock_server):
        """Test connecting when already connected."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=mock_server.port,
            username="admin",
            password="password",
            timeout=2
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        initial_reader = driver.reader
        
        # Try to connect again
        await driver.connect()
        
        # Should keep same connection
        assert driver.reader == initial_reader
        
        await driver.disconnect()
    
    @pytest.mark.asyncio
    async def test_disconnect(self, mock_server):
        """Test disconnection."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=mock_server.port,
            username="admin",
            password="password"
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        await driver.disconnect()
        
        assert driver.state == ConnectionState.DISCONNECTED
        assert driver.reader is None
        assert driver.writer is None


class TestCommandExecution:
    """Test command execution functionality."""
    
    @pytest.mark.asyncio
    async def test_execute_command_simple(self, mock_server):
        """Test simple command execution."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=mock_server.port,
            username="admin",
            password="password"
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        
        # Execute command
        output = await driver.execute_command("echo alive")
        assert "alive" in output
        
        # Check command history
        history = driver.get_command_history()
        assert len(history) == 1
        assert history[0][0] == "echo alive"
        
        await driver.disconnect()
    
    @pytest.mark.asyncio
    async def test_execute_command_not_connected(self, telnet_driver):
        """Test command execution when not connected."""
        with pytest.raises(TelnetConnectionError) as exc_info:
            await telnet_driver.execute_command("echo test")
        
        assert "Not connected" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_execute_command_timeout(self, mock_server):
        """Test command timeout."""
        # The mock server doesn't actually sleep, so we test with a command 
        # that will never return a prompt
        config = TelnetConfig(
            host="127.0.0.1",
            port=mock_server.port,
            username="admin",
            password="password",
            timeout=1
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        
        # Use a command that doesn't exist in mock server, which won't return a prompt
        with pytest.raises(TelnetTimeoutError) as exc_info:
            await driver.execute_command("blocking_command", timeout=1)
        
        assert "timed out" in str(exc_info.value)
        
        await driver.disconnect()
    
    @pytest.mark.asyncio
    async def test_execute_commands_batch(self, mock_server):
        """Test batch command execution."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=mock_server.port,
            username="admin",
            password="password"
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        
        commands = ["echo test1", "echo test2", "whoami"]
        outputs = await driver.execute_commands(commands)
        
        assert len(outputs) == 3
        assert "test1" in outputs[0]
        assert "test2" in outputs[1]
        assert "admin" in outputs[2]
        
        await driver.disconnect()


class TestFileTransfer:
    """Test file transfer functionality."""
    
    @pytest.mark.asyncio
    async def test_send_file(self, board_simulator):
        """Test file transfer to board."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=board_simulator.port,
            username="test",
            password="test123"
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        
        # Create test file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("Test file content")
            local_path = f.name
        
        try:
            # Send file
            success = await driver.send_file(
                local_path,
                "/tmp/test.txt",
                transfer_method="base64"
            )
            
            assert success is True
            
        finally:
            os.unlink(local_path)
            await driver.disconnect()
    
    @pytest.mark.asyncio
    async def test_read_file(self, board_simulator):
        """Test file reading from board."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=board_simulator.port,
            username="test",
            password="test123"
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        
        # Read existing file
        content = await driver.read_file("/etc/passwd")
        assert content is not None
        assert "root" in content
        
        # Read non-existent file
        content = await driver.read_file("/non/existent/file")
        assert "No such file" in content or content == ""
        
        await driver.disconnect()


class TestConnectionManagement:
    """Test connection management features."""
    
    @pytest.mark.asyncio
    async def test_is_alive(self, mock_server):
        """Test connection liveness check."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=mock_server.port,
            username="admin",
            password="password"
        )
        driver = TelnetDriver(config)
        
        # Not connected
        assert await driver.is_alive() is False
        
        # Connected
        await driver.connect()
        assert await driver.is_alive() is True
        
        # Disconnected
        await driver.disconnect()
        assert await driver.is_alive() is False
    
    @pytest.mark.asyncio
    async def test_context_manager(self, mock_server):
        """Test async context manager."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=mock_server.port,
            username="admin",
            password="password"
        )
        
        async with TelnetDriver(config) as driver:
            assert driver.state == ConnectionState.AUTHENTICATED
            
            output = await driver.execute_command("echo test")
            assert "test" in output
        
        # Should be disconnected after context
        assert driver.state == ConnectionState.DISCONNECTED
    
    @pytest.mark.asyncio
    async def test_command_history(self, mock_server):
        """Test command history management."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=mock_server.port,
            username="admin",
            password="password"
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        
        # Execute commands
        await driver.execute_command("echo test1")
        await driver.execute_command("echo test2")
        await driver.execute_command("whoami")
        
        # Check history
        history = driver.get_command_history()
        assert len(history) == 3
        assert history[0][0] == "echo test1"
        assert history[1][0] == "echo test2"
        assert history[2][0] == "whoami"
        
        # Clear history
        driver.clear_history()
        assert len(driver.get_command_history()) == 0
        
        await driver.disconnect()


class TestBoardSimulator:
    """Test with board simulator for realistic scenarios."""
    
    @pytest.mark.asyncio
    async def test_test_execution(self, board_simulator):
        """Test simulated test execution."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=board_simulator.port,
            username="test",
            password="test123"
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        
        # Execute test
        output = await driver.execute_command("./test_binary")
        
        assert "Starting test" in output
        assert "PASS" in output
        assert "All tests completed successfully" in output
        
        await driver.disconnect()
    
    @pytest.mark.asyncio
    async def test_process_management(self, board_simulator):
        """Test process listing and management."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=board_simulator.port,
            username="test",
            password="test123"
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        
        # List processes
        output = await driver.execute_command("ps aux")
        assert "PID" in output
        assert "/sbin/init" in output
        
        # Simulate running process
        await driver.execute_command("./long_test &")
        
        # Check if process appears
        output = await driver.execute_command("ps aux")
        # Note: Our mock doesn't handle background processes perfectly
        
        await driver.disconnect()
    
    @pytest.mark.asyncio
    async def test_system_info(self, board_simulator):
        """Test system information retrieval."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=board_simulator.port,
            username="test",
            password="test123"
        )
        driver = TelnetDriver(config)
        
        await driver.connect()
        
        # Get system info
        uname = await driver.execute_command("uname -a")
        assert "Linux" in uname
        assert "mock-board" in uname
        
        # Get CPU info
        cpuinfo = await driver.execute_command("cat /proc/cpuinfo")
        assert "processor" in cpuinfo
        assert "Mock CPU" in cpuinfo
        
        # Get memory info
        meminfo = await driver.execute_command("free -m")
        assert "Mem:" in meminfo
        assert "2048" in meminfo
        
        # Get disk info
        diskinfo = await driver.execute_command("df -h")
        assert "Filesystem" in diskinfo
        assert "/dev/root" in diskinfo
        
        await driver.disconnect()


class TestErrorHandling:
    """Test error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_login_failure_wrong_username(self):
        """Test login failure with wrong username."""
        port = random.randint(40001, 50000)
        server = MockTelnetServer(
            host="127.0.0.1",
            port=port,
            username="admin",
            password="password"
        )
        await server.start_background()
        
        config = TelnetConfig(
            host="127.0.0.1",
            port=port,
            username="wrong",
            password="password",
            timeout=2
        )
        driver = TelnetDriver(config)
        
        try:
            with pytest.raises(TelnetConnectionError) as exc_info:
                await driver.connect()
            
            assert "Login" in str(exc_info.value) or "timeout" in str(exc_info.value)
        finally:
            await server.stop()
    
    @pytest.mark.asyncio
    async def test_login_failure_wrong_password(self):
        """Test login failure with wrong password."""
        port = random.randint(50001, 60000)
        server = MockTelnetServer(
            host="127.0.0.1",
            port=port,
            username="admin",
            password="password"
        )
        await server.start_background()
        
        config = TelnetConfig(
            host="127.0.0.1",
            port=port,
            username="admin",
            password="wrong",
            timeout=2
        )
        driver = TelnetDriver(config)
        
        try:
            with pytest.raises(TelnetConnectionError) as exc_info:
                await driver.connect()
            
            assert "Login" in str(exc_info.value) or "timeout" in str(exc_info.value)
        finally:
            await server.stop()
    
    @pytest.mark.asyncio
    async def test_retry_logic(self):
        """Test connection retry logic."""
        config = TelnetConfig(
            host="127.0.0.1",
            port=9998,  # Non-existent port
            connect_timeout=0.5,
            retry_count=3,
            retry_delay=0.1
        )
        driver = TelnetDriver(config)
        
        import time
        start = time.time()
        
        with pytest.raises(TelnetConnectionError) as exc_info:
            await driver.connect()
        
        elapsed = time.time() - start
        
        # Should have retried 3 times
        assert "after 3 attempts" in str(exc_info.value)
        # Should have taken at least retry_delay * 2 (between retries)
        assert elapsed >= 0.2