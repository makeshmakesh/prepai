# pylint:disable=all
from django.urls import path
from prepaiapp import views
from django.views.generic import TemplateView
urlpatterns = [
    path("", views.HomePage.as_view(), name="entry"),
    path("early-access/", views.EarlyAccessSignupView.as_view(), name="early_access"),
    path('voice/', views.voice_agent_view, name='voice_agent'),
    path('health/', views.health_check, name='health_check'),
    path('status/', views.api_status, name='api_status'),
]
# # Wire up our API using automatic URL routing.
# urlpatterns = [
#     path("/home", views.HomePage.as_view(), name="entry"),
#     path("early-access/", views.EarlyAccessSignupView.as_view(), name="early_access"),
#     path("realtime/", views.realtime_view, name="realtime"),
#     path("", TemplateView.as_view(template_name="realtime.html")),
# ]