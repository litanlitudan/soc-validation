"""Notification Service API."""

import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import httpx
import logging

from .notifier import NotificationService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SoC Validation Notification Service",
    version="0.1.0",
    description="Notification service for test results and webhook handling"
)

# Initialize notification service
notification_service = NotificationService()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str


class WebhookPayload(BaseModel):
    """Generic webhook payload."""
    event: str
    data: dict


class TestNotification(BaseModel):
    """Test result notification."""
    test_binary: str
    board_id: str
    status: str
    duration: Optional[float] = None
    error_message: Optional[str] = None


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="notification-service",
        version="0.1.0"
    )


@app.post("/api/v1/notify/test")
async def notify_test_result(notification: TestNotification):
    """Send test result notification."""
    try:
        test_result = {
            "test_binary": notification.test_binary,
            "board_id": notification.board_id,
            "status": notification.status,
            "duration": notification.duration,
            "error_message": notification.error_message
        }
        
        success = await notification_service.send_test_completed(test_result)
        
        if success:
            return {"status": "sent", "message": "Notification sent successfully"}
        else:
            return {"status": "skipped", "message": "Notifications not configured or disabled"}
            
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/notify/queue-alert")
async def notify_queue_alert(queue_size: int = 0, wait_time: float = 0.0):
    """Send queue alert notification."""
    try:
        success = await notification_service.send_queue_alert(queue_size, wait_time)
        
        if success:
            return {"status": "sent", "message": "Queue alert sent"}
        else:
            return {"status": "skipped", "message": "Alert threshold not met or notifications disabled"}
            
    except Exception as e:
        logger.error(f"Failed to send queue alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhooks/slack")
async def slack_webhook(request: Request):
    """Handle Slack webhook events and commands."""
    try:
        # Get the raw body for signature verification
        body = await request.body()
        
        # Parse the payload
        payload = await request.json()
        
        # TODO: Verify Slack signature
        # slack_signature = request.headers.get("X-Slack-Signature")
        # slack_timestamp = request.headers.get("X-Slack-Request-Timestamp")
        
        # Handle different Slack event types
        if "command" in payload:
            # Slash command
            command = payload["command"]
            text = payload.get("text", "")
            user = payload.get("user_name", "unknown")
            
            if command == "/run-test":
                # Trigger a test run via Prefect
                # TODO: Implement Prefect deployment trigger
                return {
                    "response_type": "in_channel",
                    "text": f"Test requested by @{user} for: {text}"
                }
            else:
                return {
                    "response_type": "ephemeral",
                    "text": f"Unknown command: {command}"
                }
                
        elif "event" in payload:
            # Event callback
            event = payload["event"]
            event_type = event.get("type")
            
            # Handle different event types
            logger.info(f"Received Slack event: {event_type}")
            return {"ok": True}
            
        else:
            return {"ok": True}
            
    except Exception as e:
        logger.error(f"Slack webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhooks/feishu")
async def feishu_webhook(request: Request):
    """Handle Feishu webhook events."""
    try:
        payload = await request.json()
        
        # TODO: Verify Feishu signature
        # feishu_signature = request.headers.get("X-Feishu-Signature")
        
        # Handle Feishu events
        event_type = payload.get("header", {}).get("event_type")
        
        if event_type == "im.message.receive_v1":
            # Handle message
            message = payload.get("event", {}).get("message", {})
            content = message.get("content", "")
            
            # TODO: Parse and handle commands
            logger.info(f"Received Feishu message: {content}")
            
        return {"msg": "ok"}
        
    except Exception as e:
        logger.error(f"Feishu webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhooks/jenkins")
async def jenkins_webhook(request: Request):
    """Handle Jenkins webhook events."""
    try:
        payload = await request.json()
        
        # TODO: Verify Jenkins webhook token
        # token = request.headers.get("X-Jenkins-Token")
        
        # Handle Jenkins build events
        build_status = payload.get("build", {}).get("status")
        build_url = payload.get("build", {}).get("url")
        
        if build_status:
            # TODO: Trigger appropriate test workflows
            logger.info(f"Jenkins build {build_status}: {build_url}")
            
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"Jenkins webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info("Notification Service starting up...")
    logger.info(f"Slack webhook configured: {notification_service.slack_webhook is not None}")
    logger.info(f"Feishu webhook configured: {notification_service.feishu_webhook is not None}")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Notification Service shutting down...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)