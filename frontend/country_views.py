"""Country explorer and mastery views."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.text import slugify

from .countries import filter_choices, filter_countries, get_countries
from .models import GameResult


def _optional_int(value):
    try:
        return int(value.strip()) if value.strip() else None
    except (AttributeError, ValueError):
        return None


def _filters(query_params):
    return {
        "query": query_params.get("search_countries", ""),
        "continent": query_params.get("continent", ""),
        "entry_type": query_params.get("entry_type", ""),
        "min_area": _optional_int(query_params.get("min_area", "")),
        "min_population": _optional_int(query_params.get("min_population", "")),
    }


def _daily_completed(request):
    today = timezone.localdate()
    if request.user.is_authenticated:
        return GameResult.objects.filter(
            user=request.user,
            gamemode="daily",
            challenge_date=today,
        ).exists()
    return request.session.get("quiz_daily_completed") == today.isoformat()


def index(request):
    countries = get_countries()
    filters = _filters(request.GET)
    return render(
        request,
        "index.html",
        {
            "countries": filter_countries(countries, **filters),
            "total_count": len(countries),
            "continents": filter_choices(countries, "region"),
            "entry_types": filter_choices(countries, "entry_type"),
            "selected_query": filters["query"],
            "selected_continent": filters["continent"],
            "selected_type": filters["entry_type"],
            "selected_min_area": request.GET.get("min_area", ""),
            "selected_min_population": request.GET.get("min_population", ""),
            "daily_completed": _daily_completed(request),
        },
    )


def search_countries(request):
    countries = filter_countries(get_countries(), **_filters(request.GET))
    return render(request, "list.html", {"countries": countries})


def search_guesses(request):
    countries = filter_countries(
        get_countries(),
        query=request.GET.get("guess", ""),
    )
    return render(request, "guesses.html", {"countries": countries})


def country(request, country_name):
    chosen = next(
        (
            country
            for country in get_countries()
            if slugify(country["name"]) == country_name
        ),
        None,
    )
    if not chosen:
        return redirect("index")
    return render(request, "country.html", {"chosen_country": chosen})


@login_required
def mastery(request):
    countries = get_countries()
    mastered = set(request.user.mastered_flags.values_list("name", flat=True))
    progress = {
        item.country.name: item
        for item in request.user.flag_progress.select_related("country")
    }

    entries = []
    for country_data in countries:
        name = country_data["name"]
        flag_progress = progress.get(name)
        wrong_answers = flag_progress.wrong_answers if flag_progress else 0
        entries.append(
            {
                **country_data,
                "mastered": name in mastered,
                "attempts": flag_progress.attempts if flag_progress else 0,
                "wrong_answers": wrong_answers,
                "needs_review": name not in mastered or wrong_answers > 0,
            }
        )

    return render(
        request,
        "mastery.html",
        {
            "entries": entries,
            "mastered_count": len(mastered),
            "total_count": len(countries),
            "review_count": sum(entry["needs_review"] for entry in entries),
        },
    )
