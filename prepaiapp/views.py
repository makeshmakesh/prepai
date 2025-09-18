#pylint:disable=all
from django.shortcuts import render
from django.views import View
from .models import EarlyAccessEmail
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse


from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging

logger = logging.getLogger(__name__)

def voice_agent_view(request):
    """Main voice agent interface"""
    return render(request, 'voice_agent.html')

@csrf_exempt
def health_check(request):
    """Health check endpoint"""
    return JsonResponse({
        'status': 'healthy',
        'service': 'voice-agent'
    })

def api_status(request):
    """API status endpoint"""
    return JsonResponse({
        'websocket_url': '/ws/voice-agent/',
        'status': 'ready'
    })
class HomePage(View):
    """Renders the landing page."""
    def get(self, request):

        return render(request, "landing.html")
    
    

class EarlyAccessSignupView(View):
    template_name = "landing.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get("email", "").strip().lower()
        print("Received email:", email)
        if email:
            obj, created = EarlyAccessEmail.objects.get_or_create(email=email)
            if created:
                return JsonResponse({"status": "success", "message": "Thanks for joining!"})
            else:
                return JsonResponse({"status": "info", "message": "You're already on the list."})
        else:
            return JsonResponse({"status": "error", "message": "Please enter a valid email."})


def realtime_view(request):
    # This would later connect to your Realtime agent logic
    # but for now just return something simple
    return render(request, "realtime.html")