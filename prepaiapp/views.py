#pylint:disable=all
from django.shortcuts import render
from django.views import View
from .models import EarlyAccessEmail
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
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