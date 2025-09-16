# pylint:disable=all
from django.urls import path
from prepaiapp import views


# Wire up our API using automatic URL routing.
urlpatterns = [
    path("", views.HomePage.as_view(), name="entry"),
    path("early-access/", views.EarlyAccessSignupView.as_view(), name="early_access"),
]