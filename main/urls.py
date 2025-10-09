# pylint:disable=all
from django.urls import path
from main import views as MainView
from django.conf import settings
from django.conf.urls.static import static
from prepaiapp import views
urlpatterns = [
    path("", MainView.HomePage.as_view(), name="entry"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("accounts/login/", views.LoginView.as_view(), name="login"),
    path("signup/", views.SignupView.as_view(), name="signup"),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
