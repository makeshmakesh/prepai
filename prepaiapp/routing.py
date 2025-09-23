from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/voice-agent/$', consumers.VoiceAgentConsumer.as_asgi()),
    # re_path(r'ws/interview/(?P<session_id>[0-9a-f-]+)/$', consumers.InterviewConsumer.as_asgi()),
    re_path(r'ws/roleplay/(?P<session_id>[0-9a-f-]+)/$', consumers.RoleplayConsumer.as_asgi())
]
