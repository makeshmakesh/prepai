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
    path("marketplace/", views.MarketplaceView.as_view(), name="marketplace"),
    path("voice_roleplay/", views.VoiceRolePlayView.as_view(), name="voice_roleplay"),
    path("interview_history/", views.InterviewHistoryView.as_view(), name="interview_history"),
    path("purchase_credits/", views.PurchaseCredits.as_view(), name="purchase_credits"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path('process-purchase/', views.process_purchase, name='process_purchase'),
    path("create_roleplay_bot/", views.CreateRolePlayBotView.as_view(), name="create_roleplay_bot"),
    path("my-roleplay-bots/", views.MyRolePlayBotView.as_view(), name="my-roleplay-bots"),
    path("edit-roleplay-bot/<uuid:bot_id>/", views.EditRolePlayBotView.as_view(), name="edit-roleplay-bot"),
    path("delete-roleplay-bot/<uuid:bot_id>/", views.DeleteRolePlayBotView.as_view(), name="delete-roleplay-bot"),
    
    path('purchase/confirmation/<uuid:transaction_id>/', views.purchase_confirmation, name='purchase_confirmation'),
    path('transaction-status/<uuid:transaction_id>/', views.transaction_status, name='transaction_status'),
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
    path(
        "roleplay/start/<uuid:bot_id>/",
        views.RolePlayStartView.as_view(),
        name="start_roleplay",
    ),
    path(
        "roleplay/session/<uuid:session_id>/",
        views.RolePlaySessionView.as_view(),
        name="roleplay_session",
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
