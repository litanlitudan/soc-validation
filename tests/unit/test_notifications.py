"""Unit tests for notification service."""

import pytest
import os
from unittest.mock import patch, AsyncMock
from src.notifications.notifier import NotificationService


class TestNotificationService:
    """Test NotificationService."""
    
    def test_initialization_no_webhooks(self):
        """Test initialization without webhooks."""
        with patch.dict(os.environ, {}, clear=True):
            service = NotificationService()
            assert not service.enabled
            assert service.slack_webhook is None
            assert service.feishu_webhook is None
    
    def test_initialization_with_slack(self):
        """Test initialization with Slack webhook."""
        with patch.dict(os.environ, {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'}):
            service = NotificationService()
            assert service.enabled
            assert service.slack_webhook == 'https://hooks.slack.com/test'
            assert service.feishu_webhook is None
    
    def test_format_test_message_passed(self):
        """Test formatting passed test message."""
        service = NotificationService()
        test_result = {
            'status': 'passed',
            'test_binary': '/path/to/test',
            'board_id': 'soc-a-001',
            'duration': 123.45,
            'output_file': '/data/artifacts/test-123/output.log'
        }
        
        message = service._format_test_message(test_result)
        assert '✅' in message
        assert 'PASSED' in message
        assert '/path/to/test' in message
        assert 'soc-a-001' in message
        assert '123.45s' in message
    
    def test_format_test_message_failed(self):
        """Test formatting failed test message."""
        service = NotificationService()
        test_result = {
            'status': 'failed',
            'test_binary': '/path/to/test',
            'board_id': 'soc-b-001',
            'duration': 45.67,
            'error_message': 'Assertion failed at line 42'
        }
        
        message = service._format_test_message(test_result)
        assert '❌' in message
        assert 'FAILED' in message
        assert 'Assertion failed at line 42' in message
    
    @pytest.mark.asyncio
    async def test_send_test_completed_disabled(self):
        """Test send_test_completed when notifications are disabled."""
        with patch.dict(os.environ, {}, clear=True):
            service = NotificationService()
            result = await service.send_test_completed({'status': 'passed'})
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_slack_success(self):
        """Test successful Slack notification."""
        with patch.dict(os.environ, {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'}):
            service = NotificationService()
            
            with patch('httpx.AsyncClient') as mock_client:
                mock_response = AsyncMock()
                mock_response.status_code = 200
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
                
                result = await service._send_slack("Test message")
                assert result is True
    
    @pytest.mark.asyncio
    async def test_send_slack_failure(self):
        """Test failed Slack notification."""
        with patch.dict(os.environ, {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'}):
            service = NotificationService()
            
            with patch('httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=Exception("Network error"))
                
                result = await service._send_slack("Test message")
                assert result is False
    
    @pytest.mark.asyncio
    async def test_send_queue_alert(self):
        """Test queue alert notification."""
        with patch.dict(os.environ, {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'}):
            service = NotificationService()
            
            # Should not send if wait time < 30 minutes
            result = await service.send_queue_alert(10, 25.0)
            assert result is False
            
            # Should send if wait time >= 30 minutes
            with patch.object(service, '_send_slack', return_value=True) as mock_send:
                result = await service.send_queue_alert(20, 35.0)
                assert result is True
                mock_send.assert_called_once()
                
                # Check message content
                call_args = mock_send.call_args[0][0]
                assert '⚠️ Queue Alert' in call_args
                assert '20 tests' in call_args
                assert '35.0 minutes' in call_args