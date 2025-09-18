
#pylint: disable=all
import os
import json
import base64
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
# os.environ["OPENAI_API_KEY"] = ""
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12"



# voice_agent/consumers.py
import asyncio
import json
import queue
import threading
from typing import Any, Dict, Optional
import base64
import logging

import numpy as np
from channels.generic.websocket import AsyncWebsocketConsumer

from agents.realtime import (
    RealtimeAgent,
    RealtimePlaybackTracker,
    RealtimeRunner,
    RealtimeSession,
    RealtimeSessionEvent,
)
from agents.realtime.model import RealtimeModelConfig
from agents import function_tool

logger = logging.getLogger(__name__)

# Audio configuration
SAMPLE_RATE = 24000
FORMAT = np.int16
CHANNELS = 1

@function_tool
def get_weather(city: str) -> str:
    """Get the weather in a city."""
    return f"The weather in {city} is sunny."

class VoiceAgentConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session: Optional[RealtimeSession] = None
        self.runner: Optional[RealtimeRunner] = None
        self.playback_tracker = RealtimePlaybackTracker()
        self.agent = RealtimeAgent(
            name="Assistant",
            instructions=(
    "You are a helpful AI assistant. "
    "Always respond strictly in English. "
    "Do not translate, detect, or switch to any other language. "
    "If the user speaks in another language, politely respond in English only."
),
            tools=[get_weather],
        )
        self.session_task: Optional[asyncio.Task] = None
        self.connected = False

    async def connect(self):
        await self.accept()
        self.connected = True
        logger.info("WebSocket connection established")
        
        # Start the realtime session
        await self.start_realtime_session()

    async def disconnect(self, close_code):
        self.connected = False
        logger.info(f"WebSocket disconnected with code: {close_code}")
        
        # Clean up the realtime session
        await self.cleanup_session()

    async def receive(self, text_data=None, bytes_data=None):
        if not self.connected:
            return
            
        try:
            if text_data:
                data = json.loads(text_data)
                await self.handle_message(data)
            elif bytes_data:
                # Handle raw audio data
                await self.handle_audio_data(bytes_data)
        except Exception as e:
            logger.error(f"Error processing received data: {e}")
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": str(e)
            }))

    async def handle_message(self, data: Dict[str, Any]):
        """Handle JSON messages from client"""
        message_type = data.get("type")
        
        if message_type == "audio_data":
            # Handle base64 encoded audio
            audio_b64 = data.get("audio")
            audio_format = data.get("format", "unknown")
            sample_rate = data.get("sample_rate", SAMPLE_RATE)
            channels = data.get("channels", 1)
            
            if audio_b64:
                try:
                    audio_bytes = base64.b64decode(audio_b64)
                    
                    # Validate audio format
                    if audio_format == "pcm16" and sample_rate == SAMPLE_RATE and channels == 1:
                        await self.handle_audio_data(audio_bytes)
                    else:
                        logger.warning(f"Invalid audio format: {audio_format}, SR: {sample_rate}, Channels: {channels}")
                        await self.send(text_data=json.dumps({
                            "type": "error",
                            "message": f"Invalid audio format. Expected PCM16, 24kHz, mono. Got: {audio_format}, {sample_rate}Hz, {channels}ch"
                        }))
                        
                except Exception as e:
                    logger.error(f"Error decoding audio data: {e}")
                    await self.send(text_data=json.dumps({
                        "type": "error",
                        "message": f"Audio decode error: {str(e)}"
                    }))
                    
        elif message_type == "start_recording":
            logger.info("Recording started by client")
            await self.send(text_data=json.dumps({
                "type": "recording_started",
                "message": "Voice agent is ready. You can start speaking."
            }))
            
        elif message_type == "stop_recording":
            logger.info("Recording stopped by client")
            await self.send(text_data=json.dumps({
                "type": "recording_stopped"
            }))
            
        elif message_type == "interrupt":
            logger.info("Interrupt requested by client")
            # Clear current response tracking
            self.current_response_id = None
            self.processed_items.clear()
            
            # Send interrupt to session if available
            if self.session:
                try:
                    # If there's a way to cancel current response in the session
                    await self.send(text_data=json.dumps({
                        "type": "interrupting",
                        "message": "Interrupting current response..."
                    }))
                except Exception as e:
                    logger.error(f"Error sending interrupt: {e}")
                    
        elif message_type == "clear_session":
            logger.info("Clear session requested")
            # Reset session state
            self.current_response_id = None
            self.processed_items.clear()
            await self.send(text_data=json.dumps({
                "type": "session_cleared",
                "message": "Session state cleared"
            }))

    async def handle_audio_data(self, audio_bytes: bytes):
        """Send audio data to the realtime session"""
        if self.session and self.connected:
            try:
                await self.session.send_audio(audio_bytes)
            except Exception as e:
                logger.error(f"Error sending audio to session: {e}")

    async def start_realtime_session(self):
        """Initialize and start the realtime session"""
        try:
            self.runner = RealtimeRunner(self.agent)
            model_config: RealtimeModelConfig = {
                "playback_tracker": self.playback_tracker,
                "initial_model_settings": {
                    "turn_detection": {
                        "type": "semantic_vad",
                        "interrupt_response": True,
                        "create_response": True,
                    },
                },
            }
            
            # Start the session in a background task
            self.session_task = asyncio.create_task(
                self._run_session(model_config)
            )
            
        except Exception as e:
            logger.error(f"Error starting realtime session: {e}")
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": f"Failed to start voice agent: {str(e)}"
            }))

    async def _run_session(self, model_config: RealtimeModelConfig):
        """Run the realtime session and handle events"""
        try:
            async with await self.runner.run(model_config=model_config) as session:
                self.session = session
                logger.info("Realtime session started")
                
                await self.send(text_data=json.dumps({
                    "type": "session_ready",
                    "message": "Voice agent connected and ready"
                }))

                # Process session events
                async for event in session:
                    if not self.connected:
                        break
                    await self._handle_session_event(event)
                    
        except Exception as e:
            logger.error(f"Session error: {e}")
            if self.connected:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": f"Session error: {str(e)}"
                }))

    async def _handle_session_event(self, event: RealtimeSessionEvent):
        """Handle events from the realtime session"""
        try:
            if event.type == "agent_start":
                await self.send(text_data=json.dumps({
                    "type": "agent_start",
                    "agent_name": event.agent.name
                }))
                
            elif event.type == "agent_end":
                await self.send(text_data=json.dumps({
                    "type": "agent_end",
                    "agent_name": event.agent.name
                }))
                
            elif event.type == "tool_start":
                await self.send(text_data=json.dumps({
                    "type": "tool_start",
                    "tool_name": event.tool.name
                }))
                
            elif event.type == "tool_end":
                await self.send(text_data=json.dumps({
                    "type": "tool_end",
                    "tool_name": event.tool.name,
                    "output": str(event.output)
                }))
                
            elif event.type == "audio":
                # Send audio data back to client
                np_audio = np.frombuffer(event.audio.data, dtype=np.int16)
                audio_b64 = base64.b64encode(np_audio.tobytes()).decode('utf-8')
                
                await self.send(text_data=json.dumps({
                    "type": "audio",
                    "audio": audio_b64,
                    "item_id": event.item_id,
                    "content_index": event.content_index,
                    "sample_rate": SAMPLE_RATE,
                    "channels": CHANNELS
                }))
                
                # Update playback tracker
                try:
                    self.playback_tracker.on_play_bytes(
                        item_id=event.item_id,
                        item_content_index=event.content_index,
                        bytes=np_audio.tobytes()
                    )
                except Exception as e:
                    logger.error(f"Playback tracker error: {e}")
                    
            elif event.type == "audio_end":
                await self.send(text_data=json.dumps({
                    "type": "audio_end"
                }))
                
            elif event.type == "audio_interrupted":
                await self.send(text_data=json.dumps({
                    "type": "audio_interrupted"
                }))
                
            elif event.type == "error":
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": str(event.error)
                }))
                
            elif event.type in ["history_updated", "history_added"]:
                # Skip frequent events to reduce noise
                pass
                
            elif event.type == "raw_model_event":
                # Optionally log or handle raw model events
                logger.debug(f"Raw model event: {str(event.data)[:200]}")
                
        except Exception as e:
            logger.error(f"Error handling session event: {e}")

    async def cleanup_session(self):
        """Clean up the realtime session"""
        try:
            if self.session_task and not self.session_task.done():
                self.session_task.cancel()
                try:
                    await self.session_task
                except asyncio.CancelledError:
                    pass
                    
            self.session = None
            self.runner = None
            logger.info("Session cleaned up")
            
        except Exception as e:
            logger.error(f"Error cleaning up session: {e}")