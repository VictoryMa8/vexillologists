from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import TemplateView

from . import account_views, country_views, gameplay

urlpatterns = [
    path('', country_views.index, name='index'),
    path('login/', account_views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('signup/', account_views.signup, name='signup'),
    path("search_countries/", country_views.search_countries, name="search_countries"),
    path("search_guesses/", country_views.search_guesses, name="search_guesses"),
    path("country/<slug:country_name>/", country_views.country, name="country"),
    path("quiz/", gameplay.quiz, name="quiz"),
    path("quiz/change-gamemode/", gameplay.change_gamemode, name="change_gamemode"),
    path("leaderboard/", gameplay.leaderboard, name="leaderboard"),
    path("mastery/", country_views.mastery, name="mastery"),
    path("about/", TemplateView.as_view(template_name="about.html"), name="about"),
    path("privacy/", TemplateView.as_view(template_name="privacy.html"), name="privacy"),
    path("contact/", TemplateView.as_view(template_name="contact.html"), name="contact"),
    path(
        "release-notes/",
        TemplateView.as_view(template_name="release_notes.html"),
        name="release_notes",
    ),
    path("settings/", account_views.settings, name="settings"),
    path(
        "settings/delete_account/",
        account_views.delete_account,
        name="delete_account",
    ),
    path(
        "settings/resend_confirmation/",
        account_views.resend_confirmation,
        name="resend_confirmation",
    ),
]
