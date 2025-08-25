"""Notification service for test results."""

import os
import httpx
from typing import Optional, Dict
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications to Slack/Feishu."""
    
    def __init__(self):
        """Initialize notification service with webhooks from environment."""
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        self.feishu_webhook = os.getenv("FEISHU_WEBHOOK_URL")
        self.enabled = bool(self.slack_webhook or self.feishu_webhook)
        
        if not self.enabled:
            logger.warning("No notification webhooks configured")
    
    async def send_test_completed(self, test_result: Dict) -> bool:
        """
        Send test completion notification.
        
        Args:
            test_result: Test result dictionary
        
        Returns:
            bool: True if notification sent successfully
        """
        if not self.enabled:
            return False
        
        message = self._format_test_message(test_result)
        
        if self.slack_webhook:
            return await self._send_slack(message)
        elif self.feishu_webhook:
            return await self._send_feishu(message)
        
        return False
    
    def _format_test_message(self, test_result: Dict) -> str:
        """
        Format test result into a notification message.
        
        Args:
            test_result: Test result dictionary
        
        Returns:
            str: Formatted message
        """
        status = test_result.get("status", "unknown")
        test_binary = test_result.get("test_binary", "unknown")
        board_id = test_result.get("board_id", "unknown")
        duration = test_result.get("duration", 0)
        
        emoji = "✅" if status == "passed" else "❌" if status == "failed" else "⏱️"
        
        message = f"{emoji} Test {status.upper()}\n"
        message += f"• Test: {test_binary}\n"
        message += f"• Board: {board_id}\n"
        message += f"• Duration: {duration:.2f}s\n"
        
        if test_result.get("error_message"):
            message += f"• Error: {test_result['error_message']}\n"
        
        if test_result.get("output_file"):
            message += f"• Logs: {test_result['output_file']}\n"
        
        return message
    
    async def _send_slack(self, message: str) -> bool:
        """
        Send message to Slack.
        
        Args:
            message: Message to send
        
        Returns:
            bool: True if successful
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.slack_webhook,
                    json={"text": message},
                    timeout=10.0
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False
    
    async def _send_feishu(self, message: str) -> bool:
        """
        Send message to Feishu/Lark.
        
        Args:
            message: Message to send
        
        Returns:
            bool: True if successful
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.feishu_webhook,
                    json={
                        "msg_type": "text",
                        "content": {"text": message}
                    },
                    timeout=10.0
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send Feishu notification: {e}")
            return False
    
    async def send_queue_alert(self, queue_length: int, avg_wait_time: float) -> bool:
        """
        Send alert when queue is getting long.
        
        Args:
            queue_length: Current queue length
            avg_wait_time: Average wait time in minutes
        
        Returns:
            bool: True if notification sent
        """
        if not self.enabled or avg_wait_time < 30:
            return False
        
        message = f"⚠️ Queue Alert\n"
        message += f"• Queue length: {queue_length} tests\n"
        message += f"• Average wait: {avg_wait_time:.1f} minutes\n"
        message += f"• Time: {datetime.now().isoformat()}\n"
        
        if self.slack_webhook:
            return await self._send_slack(message)
        elif self.feishu_webhook:
            return await self._send_feishu(message)
        
        return False