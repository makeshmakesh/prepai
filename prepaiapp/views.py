#pylint:disable=all
from django.shortcuts import render
from django.views import View
from .models import EarlyAccessEmail
from django.shortcuts import render, redirect
from django.contrib import messages

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
        if email:
            obj, created = EarlyAccessEmail.objects.get_or_create(email=email)
            if created:
                messages.success(request, "🎉 Thanks for joining early access!")
            else:
                messages.info(request, "You're already on the early access list.")
        else:
            messages.error(request, "Please enter a valid email.")

        return redirect("/")  # named URL