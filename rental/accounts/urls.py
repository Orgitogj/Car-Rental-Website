from django.urls import path
from . import controllers

urlpatterns = [
    path("accounts/login/", controllers.login_view, name="login"),
    path("accounts/register/", controllers.register_view, name="register"),
    path("accounts/logout/", controllers.logout_view, name="logout"),
    path("portal/login/", controllers.portal_login, name="portal_login"),
    path("portal/register/", controllers.company_register, name="portal_register"),
    path("portal/logout/", controllers.portal_logout, name="portal_logout"),
]
