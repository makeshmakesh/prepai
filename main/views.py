from django.shortcuts import render
from django.views import View
# Create your views here.
class HomePage(View):
    """Renders the landing page."""
    def get(self, request):

        return render(request, "main/landing.html")