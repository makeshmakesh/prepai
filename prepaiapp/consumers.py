# pylint: disable=all
import os
import json
import base64
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.shortcuts import get_object_or_404
import time
# os.environ["OPENAI_API_KEY"] = ""
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# voice_agent/consumers.py
import asyncio
import json
from typing import Any, Dict, Optional
import base64
import logging
from django.utils import timezone
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



class VoiceAgentConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session: Optional[RealtimeSession] = None
        self.runner: Optional[RealtimeRunner] = None
        self.playback_tracker = RealtimePlaybackTracker()
        self.processed_items = []
        self.agent = RealtimeAgent(
            name="Assistant",
            instructions=(
                "You are a helpful AI assistant. "
                "Always respond strictly in English. "
                "Do not translate, detect, or switch to any other language. "
                "If the user speaks in another language, politely respond in English only."
            ),
            tools=[],
        )
        self.session_task: Optional[asyncio.Task] = None
        self.connected = False

    async def connect(self, config: dict={}):
        await self.accept()
        self.connected = True
        logger.info("WebSocket connection established")

        # Start the realtime session
        await self.start_realtime_session(config)

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
            await self.send(text_data=json.dumps({"type": "error", "message": str(e)}))

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
                    if (
                        audio_format == "pcm16"
                        and sample_rate == SAMPLE_RATE
                        and channels == 1
                    ):
                        await self.handle_audio_data(audio_bytes)
                    else:
                        logger.warning(
                            f"Invalid audio format: {audio_format}, SR: {sample_rate}, Channels: {channels}"
                        )
                        await self.send(
                            text_data=json.dumps(
                                {
                                    "type": "error",
                                    "message": f"Invalid audio format. Expected PCM16, 24kHz, mono. Got: {audio_format}, {sample_rate}Hz, {channels}ch",
                                }
                            )
                        )

                except Exception as e:
                    logger.error(f"Error decoding audio data: {e}")
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "error",
                                "message": f"Audio decode error: {str(e)}",
                            }
                        )
                    )

        elif message_type == "start_recording":
            logger.info("Recording started by client")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "recording_started",
                        "message": "Voice agent is ready. You can start speaking.",
                    }
                )
            )

        elif message_type == "stop_recording":
            logger.info("Recording stopped by client")
            await self.send(text_data=json.dumps({"type": "recording_stopped"}))

        elif message_type == "interrupt":
            logger.info("Interrupt requested by client")
            # Clear current response tracking
            self.current_response_id = None
            self.processed_items.clear()

            # Send interrupt to session if available
            if self.session:
                try:
                    # If there's a way to cancel current response in the session
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "interrupting",
                                "message": "Interrupting current response...",
                            }
                        )
                    )
                except Exception as e:
                    logger.error(f"Error sending interrupt: {e}")

        elif message_type == "clear_session":
            logger.info("Clear session requested")
            # Reset session state
            self.current_response_id = None
            self.processed_items.clear()
            await self.send(
                text_data=json.dumps(
                    {"type": "session_cleared", "message": "Session state cleared"}
                )
            )

    async def handle_audio_data(self, audio_bytes: bytes):
        """Send audio data to the realtime session"""
        if self.session and self.connected:
            try:
                await self.session.send_audio(audio_bytes)
            except Exception as e:
                logger.error(f"Error sending audio to session: {e}")

    async def start_realtime_session(self, config: dict={}):
        """Initialize and start the realtime session"""
        try:
            self.runner = RealtimeRunner(self.agent)
            model_config: RealtimeModelConfig = {
                # "model" : "gpt-4o-mini-audio-preview",
                "playback_tracker": self.playback_tracker,
                
                "initial_model_settings": {
                    "voice": config.get("voice", "alloy"),
                    "turn_detection": {
                        "type": "semantic_vad",
                        "interrupt_response": True,
                        "create_response": True,
                    },
                    "input_audio_transcription": {"model": "whisper-1"},
                    "output_audio_transcription": {"model": "whisper-1"},
                },
            }

            # Start the session in a background task
            self.session_task = asyncio.create_task(self._run_session(model_config))

        except Exception as e:
            logger.error(f"Error starting realtime session: {e}")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": f"Failed to start voice agent: {str(e)}",
                    }
                )
            )

    async def _run_session(self, model_config: RealtimeModelConfig):
        """Run the realtime session and handle events"""
        try:
            async with await self.runner.run(model_config=model_config) as session:
                self.session = session
                logger.info("Realtime session started")

                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "session_ready",
                            "message": "Voice agent connected and ready",
                        }
                    )
                )

                # Process session events
                async for event in session:
                    if not self.connected:
                        break
                    await self._handle_session_event(event)

        except Exception as e:
            logger.error(f"Session error: {e}")
            if self.connected:
                await self.send(
                    text_data=json.dumps(
                        {"type": "error", "message": f"Session error: {str(e)}"}
                    )
                )

    async def _handle_session_event(self, event: RealtimeSessionEvent):
        """Handle events from the realtime session"""
        try:
            if event.type == "agent_start":
                await self.send(
                    text_data=json.dumps(
                        {"type": "agent_start", "agent_name": event.agent.name}
                    )
                )

            elif event.type == "agent_end":
                await self.send(
                    text_data=json.dumps(
                        {"type": "agent_end", "agent_name": event.agent.name}
                    )
                )

            elif event.type == "tool_start":
                await self.send(
                    text_data=json.dumps(
                        {"type": "tool_start", "tool_name": event.tool.name}
                    )
                )

            elif event.type == "tool_end":
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "tool_end",
                            "tool_name": event.tool.name,
                            "output": str(event.output),
                        }
                    )
                )

            elif event.type == "audio":
                # Send audio data back to client
                np_audio = np.frombuffer(event.audio.data, dtype=np.int16)
                audio_b64 = base64.b64encode(np_audio.tobytes()).decode("utf-8")

                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "audio",
                            "audio": audio_b64,
                            "item_id": event.item_id,
                            "content_index": event.content_index,
                            "sample_rate": SAMPLE_RATE,
                            "channels": CHANNELS,
                        }
                    )
                )

                # Update playback tracker
                try:
                    self.playback_tracker.on_play_bytes(
                        item_id=event.item_id,
                        item_content_index=event.content_index,
                        bytes=np_audio.tobytes(),
                    )
                except Exception as e:
                    logger.error(f"Playback tracker error: {e}")

            elif event.type == "audio_end":
                await self.send(text_data=json.dumps({"type": "audio_end"}))

            elif event.type == "audio_interrupted":
                await self.send(text_data=json.dumps({"type": "audio_interrupted"}))

            elif event.type == "error":
                await self.send(
                    text_data=json.dumps({"type": "error", "message": str(event.error)})
                )

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





class RoleplayConsumer(VoiceAgentConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.roleplay_bot = None
        self.roleplay_session = None
        self.current_transcript = []  # Store the complete transcript
        self.last_processed_item_count = 0  # Track processed items to avoid duplicates
        self.session_start_time = None
        self.credit_deduction_task = None
        self.credits_deducted = 0
        self.roleplay_ended = False
        self.bot_creator = None  # To store the creator of the bot
        self.bot_shared_by = None  # To store who shared the bot, if applicable
        


    async def connect(self):
        # Get bot ID from URL
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        # Load roleplay bot and create session
        await self.load_roleplay_context()
        time.sleep(5)  # Simulate delay for testing

        if not self.roleplay_bot:
            await self.close()
            return

        # Create agent with dynamic instructions from bot
        self.agent = RealtimeAgent(
            name=self.roleplay_bot.name,
            instructions=self.get_roleplay_instructions(),
            tools=[],  # Add roleplay-specific tools if needed
        )
        config = {
            "voice": self.roleplay_bot.voice if self.roleplay_bot.voice else "alloy"
        }
        
        if self.roleplay_bot:
            self.credit_deduction_task = asyncio.create_task(self.credit_deduction_loop())

        self.session_start_time = timezone.now()
        await super().connect(config)
    async def credit_deduction_loop(self):
        """Deduct credits every minute during active session"""
        try:
            while self.connected and not self.roleplay_ended:
                await asyncio.sleep(10)  # Wait 1 minute
                
                if self.connected and not self.roleplay_ended:
                    success = await self.deduct_user_credit()
                    if not success:
                        # If credit deduction fails, end the session
                        await self.handle_insufficient_credits()
                        break
                        
        except asyncio.CancelledError:
            logger.info("Credit deduction task cancelled")
        except Exception as e:
            logger.error(f"Error in credit deduction loop: {e}")
            
    async def handle_insufficient_credits(self):
        """Handle case when user runs out of credits"""
        await self.send(text_data=json.dumps({
            "type": "insufficient_credits",
            "message": "You have run out of credits. The roleplay session will end.",
            "credits_used": self.credits_deducted
        }))
        
        # End the roleplay session
        await self.handle_end_roleplay()
        
    @database_sync_to_async
    def deduct_user_credit(self):
        """Deduct one credit from user and return success status"""
        from django.db import transaction
        try:
            with transaction.atomic():
                from .models import Profile
                
                user = Profile.objects.select_for_update().get(user=self.scope["user"])
                
                # Assuming you have a credits field on User model or a related UserProfile
                # Adjust this based on your actual credit system implementation
                if hasattr(user, 'credits') and user.credits >= 10:
                    user.credits -= 10
                    user.save(update_fields=['credits'])
                    self.credits_deducted += 10
                    logger.info(f"Deducted 10 credit from user {user.user.username}. Remaining: {user.credits}")
                    if self.bot_shared_by:
                        
                        logger.info(f"4 credited to {self.bot_shared_by.username} for shared bot usage.")
                        logger.info(f"3 credited to {self.bot_creator.username} for bot usage.")
                    else:
                        logger.info(f"7 credited to {self.bot_creator.username} for bot usage.")
                    return True
                else:
                    logger.warning(f"User {user.user.username} has insufficient credits")
                    return False
                
        except Exception as e:
            logger.error(f"Error deducting credit: {e}")
            return False

    @database_sync_to_async
    def load_roleplay_context(self):
        """Load roleplay bot and create session record"""
        from .models import RolePlayBots, RoleplaySession, MyInvitedRolePlayShare

        try:
            # Load the roleplay bot
        
            # Create a new roleplay session record
            self.roleplay_session = RoleplaySession.objects.get(
                id=self.session_id,
            )
            self.roleplay_bot = RolePlayBots.objects.get(id=self.roleplay_session.bot.id, is_active=True)
            self.bot_creator = self.roleplay_bot.created_by
            invited_data = MyInvitedRolePlayShare.objects.filter(bot=self.roleplay_bot, invited_to=self.scope["user"]).first()
            if invited_data:
                self.bot_shared_by = invited_data.share.shared_by
            return True
        except RolePlayBots.DoesNotExist:
            logger.error(f"Roleplay bot {self.roleplay_bot.id} not found or inactive")
            return False
        except Exception as e:
            logger.error(f"Error loading roleplay context: {e}")
            return False

    def get_roleplay_instructions(self):
        """Generate dynamic instructions based on roleplay bot configuration"""
        if not self.roleplay_bot:
            return "You are an AI assistant."

        base_instructions = self.roleplay_bot.system_prompt
        return base_instructions

    def extract_transcript_text(self, content_item):
        """Extract transcript text from a content item"""
        if hasattr(content_item, "transcript") and content_item.transcript:
            return content_item.transcript
        elif hasattr(content_item, "text") and content_item.text:
            return content_item.text
        return None

    def format_history_item(self, history_item):
        """Format a history item into transcript format"""
        if not hasattr(history_item, "role") or not hasattr(history_item, "content"):
            return None

        role = history_item.role
        content_parts = []

        for content_item in history_item.content:
            transcript_text = self.extract_transcript_text(content_item)
            if transcript_text:
                content_parts.append(transcript_text)

        if content_parts:
            full_content = " ".join(content_parts)
            timestamp = timezone.now().strftime("%H:%M:%S")

            # Use character name for assistant role
            role_display = self.roleplay_bot.name if role == "assistant" else "USER"

            return {
                "timestamp": timestamp,
                "role": role,
                "role_display": role_display,
                "content": full_content,
                "item_id": getattr(history_item, "item_id", None),
            }

        return None

    def update_transcript(self, history):
        """Update transcript with new history items, avoiding duplicates"""
        if not history:
            return

        # Process only new items beyond what we've already processed
        new_items = history[self.last_processed_item_count :]

        for history_item in new_items:
            # Skip in-progress items to avoid partial transcripts
            if hasattr(history_item, "status") and history_item.status == "in_progress":
                continue

            formatted_item = self.format_history_item(history_item)
            if formatted_item:
                # Check if this item is already in our transcript (by item_id)
                item_id = formatted_item.get("item_id")
                if item_id:
                    # Remove any existing item with same ID (for updates)
                    self.current_transcript = [
                        item
                        for item in self.current_transcript
                        if item.get("item_id") != item_id
                    ]

                self.current_transcript.append(formatted_item)

        # Update the count of processed items
        completed_items = [
            item
            for item in history
            if not (hasattr(item, "status") and item.status == "in_progress")
        ]
        self.last_processed_item_count = len(completed_items)

    def generate_formatted_transcript(self):
        """Generate a formatted transcript string"""
        if not self.current_transcript:
            return "No conversation transcript available."

        formatted_lines = []
        formatted_lines.append(f"=== ROLEPLAY SESSION: {self.roleplay_bot.name} ===")
        formatted_lines.append(f"Scenario: {self.roleplay_bot.description}")
        formatted_lines.append(
            f"Started: {self.session_start_time.strftime('%Y-%m-%d %H:%M:%S') if self.session_start_time else 'Unknown'}"
        )
        formatted_lines.append("=" * 50)
        formatted_lines.append("")

        for item in self.current_transcript:
            formatted_lines.append(f"[{item['timestamp']}] {item['role_display']}:")
            formatted_lines.append(f"{item['content']}")
            formatted_lines.append("")

        formatted_lines.append("=" * 50)
        formatted_lines.append("=== END OF ROLEPLAY SESSION ===")
        return "\n".join(formatted_lines)

    async def _handle_session_event(self, event: RealtimeSessionEvent):
        """Override to handle transcript updates and roleplay-specific events"""
        try:
            # Handle history updates for transcript
            if event.type == "history_updated":
                if hasattr(event, "history") and event.history:
                    self.update_transcript(event.history)

                    # Send transcript update to client for real-time display
                    latest_items = (
                        self.current_transcript[-2:]
                        if len(self.current_transcript) >= 2
                        else self.current_transcript
                    )
                    await self.send(
                        text_data=json.dumps(
                            {
                                "type": "roleplay_transcript_update",
                                "bot_name": self.roleplay_bot.name,
                                "transcript_length": len(self.current_transcript),
                                "latest_items": latest_items,
                            }
                        )
                    )

                return  # Don't pass to parent to avoid noise

            # Handle all other events normally, but with roleplay context
            if event.type == "agent_start":
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "roleplay_start",
                            "bot_name": self.roleplay_bot.name,
                            "scenario": self.roleplay_bot.description,
                        }
                    )
                )
                return

            # Handle other events normally
            await super()._handle_session_event(event)

        except Exception as e:
            logger.error(f"Error handling session event in RoleplayConsumer: {e}")
            await super()._handle_session_event(event)

    async def handle_message(self, data: Dict[str, Any]):
        """Override to add roleplay-specific message handling"""
        message_type = data.get("type")

        if message_type == "end_roleplay":
            await self.handle_end_roleplay()
        elif message_type == "get_roleplay_transcript":
            # Allow client to request current transcript
            transcript = self.generate_formatted_transcript()
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "current_roleplay_transcript",
                        "bot_name": self.roleplay_bot.name,
                        "transcript": transcript,
                    }
                )
            )
        elif message_type == "get_roleplay_info":
            # Send current roleplay session info
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "roleplay_info",
                        "bot": {
                            "id": self.roleplay_bot.id,
                            "name": self.roleplay_bot.name,
                            "description": self.roleplay_bot.description,
                            "scenario": self.roleplay_bot.description,
                        },
                        "session_duration": (
                            str(timezone.now() - self.session_start_time)
                            if self.session_start_time
                            else "Unknown"
                        ),
                    }
                )
            )
        else:
            await super().handle_message(data)

    async def handle_end_roleplay(self):
        """Handle roleplay completion and save transcript"""
        if self.roleplay_session:
            # Generate final transcript
            final_transcript = self.generate_formatted_transcript()

            # Calculate session duration
            duration_seconds = 0
            if self.session_start_time:
                duration = timezone.now() - self.session_start_time
                duration_seconds = int(duration.total_seconds())

            # Save transcript and duration to database
            await self.save_roleplay_session_data(final_transcript, duration_seconds)

            # Update session status
            await self.update_session_status("completed")
            self.roleplay_ended = True
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "roleplay_complete",
                        "message": f"Roleplay with {self.roleplay_bot.name} completed successfully",
                        "bot_name": self.roleplay_bot.name,
                        "transcript_saved": True,
                        "transcript_length": len(self.current_transcript),
                        "duration_seconds": duration_seconds,
                        "credits_used": self.credits_deducted
                    }
                )
            )

    @database_sync_to_async
    def save_roleplay_session_data(self, transcript, duration_seconds):
        """Save transcript and session data to RoleplaySession"""
        try:
            # Refresh the session from DB to avoid stale data
            self.roleplay_session.refresh_from_db()

            # Save transcript and duration
            self.roleplay_session.transcript = transcript
            self.roleplay_session.duration_seconds = duration_seconds
            self.roleplay_session.credits_used = self.credits_deducted
            self.roleplay_session.save(update_fields=["transcript", "duration_seconds","credits_used"])

            logger.info(
                f"Roleplay session data saved for bot {self.roleplay_bot.name}, session {self.roleplay_session.id}"
            )
            return True
        except Exception as e:
            logger.error(f"Error saving roleplay session data: {e}")
            return False

    @database_sync_to_async
    def update_session_status(self, status):
        """Update roleplay session status"""
        try:
            self.roleplay_session.status = status
            if status == "completed":
                self.roleplay_session.completed_at = timezone.now()
            self.roleplay_session.save(update_fields=["status", "completed_at"])
        except Exception as e:
            logger.error(f"Error updating roleplay session status: {e}")

    async def disconnect(self, close_code):
        """Override disconnect to save transcript if roleplay was in progress"""
        # If roleplay was in progress but not formally ended, still save transcript
        if self.roleplay_session and self.current_transcript:
            final_transcript = self.generate_formatted_transcript()

            # Calculate duration
            duration_seconds = 0
            if self.session_start_time:
                duration = timezone.now() - self.session_start_time
                duration_seconds = int(duration.total_seconds())

            await self.save_roleplay_session_data(final_transcript, duration_seconds)

            # Update status to indicate unexpected disconnect
            await self.update_session_status("disconnected")

        await super().disconnect(close_code)


# class InterviewConsumer(VoiceAgentConsumer):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.interview_session = None
#         self.interview_template = None

#     async def connect(self):
#         # Get session ID from URL
#         self.session_id = self.scope["url_route"]["kwargs"]["session_id"]

#         # Load interview session and template
#         await self.load_interview_context()

#         if not self.interview_session:
#             await self.close()
#             return

#         # Create agent with dynamic instructions
#         self.agent = RealtimeAgent(
#             name="AI Interviewer",
#             instructions=self.get_interview_instructions(),
#             tools=[],  # Add interview-specific tools if needed
#         )

#         await super().connect()

#     @database_sync_to_async
#     def load_interview_context(self):
#         """Load interview session and template from database"""
#         from .models import InterviewSession

#         try:
#             self.interview_session = InterviewSession.objects.select_related(
#                 "template"
#             ).get(id=self.session_id, user=self.scope["user"])
#             self.interview_template = self.interview_session.template
#             return True
#         except InterviewSession.DoesNotExist:
#             return False

#     def get_interview_instructions(self):
#         """Generate dynamic instructions based on interview template"""
#         if not self.interview_template:
#             return "You are an AI interviewer."

#         base_instructions = f"""
# You are an AI interviewer conducting a {self.interview_template.get_role_type_display()} interview.

# Interview Details:
# - Role: {self.interview_template.get_role_type_display()}
# - Difficulty: {self.interview_template.get_difficulty_display()}
# - Duration: {self.interview_template.estimated_duration_minutes} minutes
# - Title: {self.interview_template.title}
# - Description: {self.interview_template.description}

# System Prompt:
# {self.interview_template.system_prompt}

# Instructions:
# 1. **Introduction**
#    - Greet the candidate politely and introduce yourself as the interviewer.
#    - Explain the purpose of the interview, its structure, and the estimated duration.
#    - Reassure the candidate that the process will be professional yet conversational.

# 2. **Interview Flow**
#    - Ask clear, relevant, and role-appropriate questions aligned with the provided system prompt.
#    - Adjust difficulty and depth based on the candidate’s responses.
#    - Use follow-up questions to explore reasoning, experiences, and problem-solving approaches in greater detail.
#    - Keep the conversation structured but natural, avoiding rigid or scripted exchanges.

# 3. **Tone and Style**
#    - Be professional, supportive, and attentive throughout.
#    - Respond only in **English**, using clear and polite language.
#    - Maintain a balance between encouragement and thorough evaluation.

# 4. **Time Management**
#    - Keep track of pacing to ensure the interview aligns with the allotted duration.
#    - Allow the candidate enough time to respond fully, while moving forward smoothly when needed.

# 5. **Closing**
#    - When sufficient insights have been gathered, begin wrapping up naturally.
#    - Thank the candidate sincerely for their time and responses.
#    - End with a polite and encouraging closing statement.

# Begin by greeting the candidate, introducing yourself, and explaining the interview process.
# """
#         return base_instructions

#     async def handle_message(self, data: Dict[str, Any]):
#         """Override to add interview-specific message handling"""
#         message_type = data.get("type")

#         if message_type == "end_interview":
#             await self.handle_end_interview()
#         else:
#             await super().handle_message(data)

#     async def handle_end_interview(self):
#         """Handle interview completion"""
#         if self.interview_session:
#             await self.update_session_status("completed")
#             await self.send(
#                 text_data=json.dumps(
#                     {
#                         "type": "session_complete",
#                         "message": "Interview completed successfully",
#                     }
#                 )
#             )

#     @database_sync_to_async
#     def update_session_status(self, status):
#         """Update interview session status"""
#         try:
#             self.interview_session.status = status
#             if status == "completed":
#                 self.interview_session.completed_at = timezone.now()
#             self.interview_session.save()
#         except Exception as e:
#             logger.error(f"Error updating session status: {e}")


# class InterviewConsumer(VoiceAgentConsumer):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.interview_session = None
#         self.interview_template = None
#         self.current_transcript = []  # Store the complete transcript
#         self.last_processed_item_count = 0  # Track processed items to avoid duplicates

#     async def connect(self):
#         # Get session ID from URL
#         self.session_id = self.scope["url_route"]["kwargs"]["session_id"]

#         # Load interview session and template
#         await self.load_interview_context()

#         if not self.interview_session:
#             await self.close()
#             return

#         # Create agent with dynamic instructions
#         self.agent = RealtimeAgent(
#             name="AI Interviewer",
#             instructions=self.get_interview_instructions(),
#             tools=[],  # Add interview-specific tools if needed
#         )

#         await super().connect()

#     @database_sync_to_async
#     def load_interview_context(self):
#         """Load interview session and template from database"""
#         from .models import InterviewSession

#         try:
#             self.interview_session = InterviewSession.objects.select_related(
#                 "template"
#             ).get(id=self.session_id, user=self.scope["user"])
#             self.interview_template = self.interview_session.template
#             return True
#         except InterviewSession.DoesNotExist:
#             return False

#     def get_interview_instructions(self):
#         """Generate dynamic instructions based on interview template"""
#         if not self.interview_template:
#             return "You are an AI interviewer."

#         base_instructions = f"""
# You are an AI interviewer conducting a {self.interview_template.get_role_type_display()} interview.

# Interview Details:
# - Role: {self.interview_template.get_role_type_display()}
# - Difficulty: {self.interview_template.get_difficulty_display()}
# - Duration: {self.interview_template.estimated_duration_minutes} minutes
# - Title: {self.interview_template.title}
# - Description: {self.interview_template.description}

# System Prompt:
# {self.interview_template.system_prompt}

# Instructions:
# 1. **Introduction**
#    - Greet the candidate politely and introduce yourself as the interviewer.
#    - Explain the purpose of the interview, its structure, and the estimated duration.
#    - Reassure the candidate that the process will be professional yet conversational.

# 2. **Interview Flow**
#    - Ask clear, relevant, and role-appropriate questions aligned with the provided system prompt.
#    - Adjust difficulty and depth based on the candidate's responses.
#    - Use follow-up questions to explore reasoning, experiences, and problem-solving approaches in greater detail.
#    - Keep the conversation structured but natural, avoiding rigid or scripted exchanges.

# 3. **Tone and Style**
#    - Be professional, supportive, and attentive throughout.
#    - Respond only in **English**, using clear and polite language.
#    - Maintain a balance between encouragement and thorough evaluation.

# 4. **Time Management**
#    - Keep track of pacing to ensure the interview aligns with the allotted duration.
#    - Allow the candidate enough time to respond fully, while moving forward smoothly when needed.

# 5. **Closing**
#    - When sufficient insights have been gathered, begin wrapping up naturally.
#    - Thank the candidate sincerely for their time and responses.
#    - End with a polite and encouraging closing statement.

# Begin by greeting the candidate, introducing yourself, and explaining the interview process.
# """
#         return base_instructions

#     def extract_transcript_text(self, content_item):
#         """Extract transcript text from a content item"""
#         if hasattr(content_item, "transcript") and content_item.transcript:
#             return content_item.transcript
#         elif hasattr(content_item, "text") and content_item.text:
#             return content_item.text
#         return None

#     def format_history_item(self, history_item):
#         """Format a history item into transcript format"""
#         if not hasattr(history_item, "role") or not hasattr(history_item, "content"):
#             return None

#         role = history_item.role
#         content_parts = []

#         for content_item in history_item.content:
#             transcript_text = self.extract_transcript_text(content_item)
#             if transcript_text:
#                 content_parts.append(transcript_text)

#         if content_parts:
#             full_content = " ".join(content_parts)
#             timestamp = timezone.now().strftime("%H:%M:%S")

#             return {
#                 "timestamp": timestamp,
#                 "role": role,
#                 "content": full_content,
#                 "item_id": getattr(history_item, "item_id", None),
#             }

#         return None

#     def update_transcript(self, history):
#         """Update transcript with new history items, avoiding duplicates"""
#         if not history:
#             return

#         # Process only new items beyond what we've already processed
#         new_items = history[self.last_processed_item_count :]

#         for history_item in new_items:
#             # Skip in-progress items to avoid partial transcripts
#             if hasattr(history_item, "status") and history_item.status == "in_progress":
#                 continue

#             formatted_item = self.format_history_item(history_item)
#             if formatted_item:
#                 # Check if this item is already in our transcript (by item_id)
#                 item_id = formatted_item.get("item_id")
#                 if item_id:
#                     # Remove any existing item with same ID (for updates)
#                     self.current_transcript = [
#                         item
#                         for item in self.current_transcript
#                         if item.get("item_id") != item_id
#                     ]

#                 self.current_transcript.append(formatted_item)

#         # Update the count of processed items
#         # Only count completed items
#         completed_items = [
#             item
#             for item in history
#             if not (hasattr(item, "status") and item.status == "in_progress")
#         ]
#         self.last_processed_item_count = len(completed_items)

#     def generate_formatted_transcript(self):
#         """Generate a formatted transcript string"""
#         if not self.current_transcript:
#             return "No transcript available."

#         formatted_lines = []
#         formatted_lines.append("=== INTERVIEW TRANSCRIPT ===\n")

#         for item in self.current_transcript:
#             role_display = "INTERVIEWER" if item["role"] == "assistant" else "CANDIDATE"
#             formatted_lines.append(f"[{item['timestamp']}] {role_display}:")
#             formatted_lines.append(f"{item['content']}\n")

#         formatted_lines.append("=== END OF TRANSCRIPT ===")
#         return "\n".join(formatted_lines)

#     async def _handle_session_event(self, event: RealtimeSessionEvent):
#         """Override to handle transcript updates"""
#         try:
#             # Handle history updates for transcript
#             if event.type == "history_updated":
#                 if hasattr(event, "history") and event.history:
#                     self.update_transcript(event.history)

#                     # Optionally send transcript update to client (for real-time display)
#                     await self.send(
#                         text_data=json.dumps(
#                             {
#                                 "type": "transcript_update",
#                                 "transcript_length": len(self.current_transcript),
#                                 "latest_items": (
#                                     self.current_transcript[-2:]
#                                     if len(self.current_transcript) >= 2
#                                     else self.current_transcript
#                                 ),
#                             }
#                         )
#                     )

#                 # Don't pass to parent to avoid noise
#                 return

#             # Handle all other events normally
#             await super()._handle_session_event(event)

#         except Exception as e:
#             logger.error(f"Error handling session event in InterviewConsumer: {e}")
#             await super()._handle_session_event(event)

#     async def handle_message(self, data: Dict[str, Any]):
#         """Override to add interview-specific message handling"""
#         message_type = data.get("type")

#         if message_type == "end_interview":
#             await self.handle_end_interview()
#         elif message_type == "get_transcript":
#             # Allow client to request current transcript
#             transcript = self.generate_formatted_transcript()
#             await self.send(
#                 text_data=json.dumps(
#                     {"type": "current_transcript", "transcript": transcript}
#                 )
#             )
#         else:
#             await super().handle_message(data)

#     async def handle_end_interview(self):
#         """Handle interview completion and save transcript"""
#         if self.interview_session:
#             # Generate final transcript
#             final_transcript = self.generate_formatted_transcript()

#             # Save transcript to database
#             await self.save_transcript_to_db(final_transcript)

#             # Update session status
#             await self.update_session_status("completed")

#             await self.send(
#                 text_data=json.dumps(
#                     {
#                         "type": "session_complete",
#                         "message": "Interview completed successfully",
#                         "transcript_saved": True,
#                         "transcript_length": len(self.current_transcript),
#                     }
#                 )
#             )

#     @database_sync_to_async
#     def save_transcript_to_db(self, transcript):
#         """Save transcript to InterviewSession.transcript field"""
#         try:
#             # Refresh the session from DB to avoid stale data
#             self.interview_session.refresh_from_db()

#             # Save transcript in the transcript field
#             self.interview_session.transcript = transcript
#             self.interview_session.save(update_fields=["transcript"])

#             logger.info(f"Transcript saved for interview session {self.session_id}")
#             return True
#         except Exception as e:
#             logger.error(f"Error saving transcript to database: {e}")
#             return False

#     @database_sync_to_async
#     def update_session_status(self, status):
#         """Update interview session status"""
#         try:
#             self.interview_session.status = status
#             if status == "completed":
#                 self.interview_session.completed_at = timezone.now()
#             self.interview_session.save(update_fields=["status", "completed_at"])
#         except Exception as e:
#             logger.error(f"Error updating session status: {e}")

#     async def disconnect(self, close_code):
#         """Override disconnect to save transcript if interview was in progress"""
#         # If interview was in progress but not formally ended, still save transcript
#         if self.interview_session and self.current_transcript:
#             final_transcript = self.generate_formatted_transcript()
#             await self.save_transcript_to_db(final_transcript)

#             # Update status to indicate unexpected disconnect
#             await self.update_session_status("disconnected")

#         await super().disconnect(close_code)