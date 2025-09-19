# pylint:disable=all
from django.urls import path
from prepaiapp import views
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("", views.HomePage.as_view(), name="entry"),
    path("early-access/", views.EarlyAccessSignupView.as_view(), name="early_access"),
    path("voice/", views.voice_agent_view, name="voice_agent"),
    path("health/", views.health_check, name="health_check"),
    path("status/", views.api_status, name="api_status"),
    path("topic/", views.topic, name="topic"),
    path("sub-topic/", views.sub_topic, name="sub_topic"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("signup/", views.SignupView.as_view(), name="signup"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("courses/", views.CourseView.as_view(), name="courses"),
    path("interview_types/", views.InterviewView.as_view(), name="interview_types"),
    path(
        "course/<slug:slug>/subtopics/",
        views.CourseSubtopicsView.as_view(),
        name="course_subtopics",
    ),
    path(
        "interview/start/<uuid:template_id>/",
        views.StartInterviewView.as_view(),
        name="start_interview",
    ),
    path(
        "interview/session/<uuid:session_id>/",
        views.InterviewSessionView.as_view(),
        name="interview_session",
    ),
    path(
        "interview/results/<uuid:session_id>/",
        views.InterviewResultView.as_view(),
        name="interview_results",
    ),
]
# # Wire up our API using automatic URL routing.
# urlpatterns = [
#     path("/home", views.HomePage.as_view(), name="entry"),
#     path("early-access/", views.EarlyAccessSignupView.as_view(), name="early_access"),
#     path("realtime/", views.realtime_view, name="realtime"),
#     path("", TemplateView.as_view(template_name="realtime.html")),
# ]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
