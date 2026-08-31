"""Quiz request handling, session state, progression, and leaderboards."""

from dataclasses import dataclass
import random
import time
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Max
from django.shortcuts import redirect, render
from django.utils import timezone

from .countries import get_countries
from .gamemodes import GAME_MODES, build_mode_pool, gamemode_sections
from .models import Country, FlagProgress, GameResult, Vexillologist


QUIZ_SESSION_KEYS = [
    "quiz_gamemode",
    "quiz_country",
    "quiz_streak",
    "quiz_score",
    "quiz_answered",
    "quiz_incorrect",
    "quiz_lives",
    "quiz_collected",
    "quiz_seen",
    "quiz_result",
    "quiz_pool_size",
    "quiz_pool_names",
    "quiz_started_at",
    "quiz_deadline",
    "quiz_choices",
    "quiz_round_token",
]


@dataclass
class QuizProgress:
    score: int
    streak: int
    answered: int
    incorrect: int
    lives: int | None
    collected: list
    seen: list

    @classmethod
    def from_session(cls, session):
        streak = session.get("quiz_streak", 0)
        return cls(
            score=session.get("quiz_score", streak),
            streak=streak,
            answered=session.get("quiz_answered", 0),
            incorrect=session.get("quiz_incorrect", 0),
            lives=session.get("quiz_lives"),
            collected=session.get("quiz_collected", []),
            seen=session.get("quiz_seen", []),
        )

    def save(self, session):
        session.update(
            {
                "quiz_score": self.score,
                "quiz_streak": self.streak,
                "quiz_answered": self.answered,
                "quiz_incorrect": self.incorrect,
                "quiz_lives": self.lives,
                "quiz_collected": self.collected,
                "quiz_seen": self.seen,
            }
        )


def clear_quiz_session(session):
    for key in QUIZ_SESSION_KEYS:
        session.pop(key, None)


def update_high_score(user, score):
    if not user.is_authenticated or score <= user.high_score:
        return

    updated = Vexillologist.objects.filter(
        pk=user.pk,
        high_score__lt=score,
    ).update(high_score=score)
    if updated:
        user.high_score = score
    else:
        user.refresh_from_db(fields=["high_score"])


def _pool_from_session(request):
    countries_by_name = {country["name"]: country for country in get_countries()}
    names = request.session.get("quiz_pool_names") or []
    return [countries_by_name[name] for name in names if name in countries_by_name]


def _set_current_country(request):
    mode = GAME_MODES[request.session["quiz_gamemode"]]
    pool = _pool_from_session(request)
    if not pool:
        # Older sessions may not contain the stable pool introduced in v1.3.
        pool = mode.filter_countries(get_countries())
        request.session["quiz_pool_names"] = [country["name"] for country in pool]
    if not pool:
        request.session["quiz_country"] = None
        return None

    seen = set(request.session.get("quiz_seen", []))
    available = [country for country in pool if country["name"] not in seen]
    if not available and mode.ruleset == "timed":
        request.session["quiz_seen"] = []
        available = pool
    if not available:
        request.session["quiz_country"] = None
        return None

    ordered_mode = mode.daily or mode.adaptive or mode.round_size
    country = available[0] if ordered_mode else random.choice(available)
    request.session["quiz_country"] = country
    request.session["quiz_round_token"] = uuid.uuid4().hex

    if mode.multiple_choice:
        request.session["quiz_choices"] = _multiple_choice_options(country, pool)
    else:
        request.session.pop("quiz_choices", None)
    return country


def _multiple_choice_options(country, pool):
    distractors = [item for item in pool if item["name"] != country["name"]]
    if len(distractors) < 3:
        distractors = [
            item for item in get_countries() if item["name"] != country["name"]
        ]
    choices = random.sample(distractors, min(3, len(distractors))) + [country]
    random.shuffle(choices)
    return [
        {"name": choice["name"], "flag_image_url": choice["flag_image_url"]}
        for choice in choices
    ]


def _start_game(request, mode_key):
    clear_quiz_session(request.session)
    mode = GAME_MODES[mode_key]
    pool = build_mode_pool(mode_key, get_countries(), request.user)
    if not pool:
        return False

    now = time.time()
    request.session.update(
        {
            "quiz_gamemode": mode_key,
            "quiz_pool_names": [country["name"] for country in pool],
            "quiz_pool_size": len(pool),
            "quiz_streak": 0,
            "quiz_score": 0,
            "quiz_answered": 0,
            "quiz_incorrect": 0,
            "quiz_lives": mode.lives,
            "quiz_collected": [],
            "quiz_seen": [],
            "quiz_started_at": now,
        }
    )
    if mode.ruleset == "timed":
        request.session["quiz_deadline"] = now + mode.time_limit
    _set_current_country(request)
    return True


def _daily_completed(request):
    today = timezone.localdate()
    if request.user.is_authenticated:
        return GameResult.objects.filter(
            user=request.user,
            gamemode="daily",
            challenge_date=today,
        ).exists()
    return request.session.get("quiz_daily_completed") == today.isoformat()


def _record_flag_attempt(user, country_name, correct):
    if not user.is_authenticated:
        return

    country = Country.objects.filter(name=country_name).first()
    if not country:
        return
    if correct:
        user.mastered_flags.add(country)

    progress, _ = FlagProgress.objects.get_or_create(user=user, country=country)
    updates = {
        "attempts": F("attempts") + 1,
        "last_seen": timezone.now(),
    }
    counter = "correct_answers" if correct else "wrong_answers"
    updates[counter] = F(counter) + 1
    FlagProgress.objects.filter(pk=progress.pk).update(**updates)


def _record_game_result(request, mode_key, progress, outcome):
    user = request.user
    if not user.is_authenticated:
        if mode_key == "daily":
            request.session["quiz_daily_completed"] = timezone.localdate().isoformat()
        return

    values = {
        "score": progress.score,
        "answered": progress.answered,
        "correct": progress.score,
        "incorrect": progress.incorrect,
        "duration_seconds": max(
            0,
            int(time.time() - request.session.get("quiz_started_at", time.time())),
        ),
        "outcome": outcome,
    }

    recorded = True
    if mode_key == "daily":
        try:
            with transaction.atomic():
                GameResult.objects.create(
                    user=user,
                    gamemode=mode_key,
                    challenge_date=timezone.localdate(),
                    **values,
                )
        except IntegrityError:
            # Two tabs can finish the same daily challenge at nearly the same time.
            recorded = False
    else:
        GameResult.objects.create(user=user, gamemode=mode_key, **values)

    if recorded:
        Vexillologist.objects.filter(pk=user.pk).update(
            games_played=F("games_played") + 1
        )
        user.refresh_from_db(fields=["games_played", "high_score"])


def _result_payload(
    request,
    mode_key,
    progress,
    truth,
    outcome,
    target,
    feedback,
    final_streak=None,
):
    # Preserve mastery from sessions created before progress was saved per answer.
    if request.user.is_authenticated and progress.collected:
        names = [item["name"] for item in progress.collected]
        request.user.mastered_flags.add(*Country.objects.filter(name__in=names))

    _record_game_result(request, mode_key, progress, outcome)
    perfect = bool(target and progress.score >= target and progress.incorrect == 0)
    return {
        "game_finished": True,
        "game_over": outcome == "lost",
        "game_won": perfect,
        "outcome": outcome,
        "final_streak": progress.streak if final_streak is None else final_streak,
        "final_score": progress.score,
        "final_answered": progress.answered,
        "final_incorrect": progress.incorrect,
        "final_collected_flags": [item["flag"] for item in progress.collected],
        "truth_name": truth.get("name", ""),
        "truth_flag": truth.get("flag_image_url", ""),
        "feedback": feedback,
    }


def _round_target(mode, pool_size):
    return min(mode.round_size, pool_size) if mode.round_size else pool_size


def _context(request, result=None):
    result = result or {}
    mode_key = request.session.get("quiz_gamemode", "world_tour")
    mode = GAME_MODES.get(mode_key, GAME_MODES["world_tour"])
    target = mode.round_size
    if target:
        target = min(target, request.session.get("quiz_pool_size", target))

    deadline = request.session.get("quiz_deadline")
    time_remaining = max(0, int(deadline - time.time())) if deadline else None
    answered = request.session.get("quiz_answered", 0)
    return {
        "random_country": request.session.get("quiz_country"),
        "streak": request.session.get("quiz_streak", 0),
        "score": request.session.get("quiz_score", 0),
        "answered": answered,
        "incorrect": request.session.get("quiz_incorrect", 0),
        "lives": request.session.get("quiz_lives"),
        "collected": request.session.get("quiz_collected", []),
        "gamemode_key": mode_key,
        "gamemode_name": mode.name,
        "ruleset": mode.ruleset,
        "multiple_choice": mode.multiple_choice,
        "choices": request.session.get("quiz_choices", []),
        "round_token": request.session.get("quiz_round_token", ""),
        "pool_size": request.session.get("quiz_pool_size", 0),
        "round_target": target,
        "question_number": min(answered + 1, target) if target else None,
        "time_remaining": time_remaining,
        "feedback": result.get("feedback"),
        "game_finished": result.get("game_finished", False),
        "game_over": result.get("game_over", False),
        "game_won": result.get("game_won", False),
        "outcome": result.get("outcome", ""),
        "final_streak": result.get("final_streak", 0),
        "final_score": result.get("final_score", 0),
        "final_answered": result.get("final_answered", 0),
        "final_incorrect": result.get("final_incorrect", 0),
        "final_collected_flags": result.get("final_collected_flags", []),
        "truth_name": result.get("truth_name", ""),
        "truth_flag": result.get("truth_flag", ""),
        "daily_complete": mode_key == "daily" and result.get("game_finished", False),
    }


def quiz(request):
    if request.method == "GET":
        return _show_quiz(request)
    if request.method != "POST":
        return redirect("quiz")

    selected_mode = request.POST.get("gamemode")
    if selected_mode:
        return _select_mode(request, selected_mode)
    return _submit_answer(request)


def _show_quiz(request):
    result = request.session.pop("quiz_result", None)
    if result:
        return render(request, "quiz.html", _context(request, result))

    if "quiz_gamemode" not in request.session:
        sections = gamemode_sections(get_countries(), request.user)
        progress = {
            card["key"]: {
                "mastered": card["mastered"],
                "total": card["total"],
            }
            for section in sections
            for card in section["cards"]
        }
        return render(
            request,
            "quiz.html",
            {
                "show_gamemode_select": True,
                "gamemode_sections": sections,
                "gamemode_progress": progress,
            },
        )

    mode_key = request.session.get("quiz_gamemode", "world_tour")
    if mode_key not in GAME_MODES:
        clear_quiz_session(request.session)
        return redirect("quiz")
    if mode_key == "daily" and _daily_completed(request):
        clear_quiz_session(request.session)
        messages.info(request, "Daily Challenge complete — come back tomorrow!")
        return redirect("quiz")
    if not request.session.get("quiz_country") and not _start_game(request, mode_key):
        messages.error(request, "That game mode does not have any available flags yet.")
        clear_quiz_session(request.session)
        return redirect("quiz")
    return render(request, "quiz.html", _context(request))


def _select_mode(request, selected_mode):
    mode_key = selected_mode if selected_mode in GAME_MODES else "world_tour"
    if mode_key == "daily" and _daily_completed(request):
        messages.info(request, "You already completed today’s Daily Challenge.")
        clear_quiz_session(request.session)
        return redirect("quiz")
    if not _start_game(request, mode_key):
        messages.error(request, "That game mode does not have any available flags yet.")
    return redirect("quiz")


def _submit_answer(request):
    truth = request.session.get("quiz_country")
    if not truth:
        return redirect("quiz")

    mode_key = request.session.get("quiz_gamemode", "world_tour")
    mode = GAME_MODES.get(mode_key, GAME_MODES["world_tour"])
    if _stale_round(request):
        return _render_quiz_result(request, {"game_finished": False})

    progress = QuizProgress.from_session(request.session)
    target = _round_target(mode, request.session.get("quiz_pool_size", 0))
    if _timed_out(request, mode):
        result = _finish_timeout(request, mode_key, progress, truth)
    else:
        result = _apply_guess(request, mode_key, mode, progress, truth, target)
    return _render_quiz_result(request, result)


def _stale_round(request):
    expected = request.session.get("quiz_round_token")
    submitted = request.POST.get("round_token")
    return bool(submitted and expected and submitted != expected)


def _timed_out(request, mode):
    deadline = request.session.get("quiz_deadline")
    return mode.ruleset == "timed" and (
        request.POST.get("quiz_action") == "timeout"
        or (deadline is not None and time.time() >= deadline)
    )


def _finish_timeout(request, mode_key, progress, truth):
    feedback = {"status": "info", "text": "Time is up!"}
    result = _result_payload(
        request,
        mode_key,
        progress,
        truth,
        "timed_out",
        None,
        feedback,
    )
    _start_game(request, mode_key)
    return result


def _apply_guess(request, mode_key, mode, progress, truth, target):
    truth_name = truth["name"]
    accepted_answers = [truth_name, *(truth.get("aliases") or [])]
    guess = request.POST.get("guess", "").strip().casefold()
    correct = any(guess == answer.casefold() for answer in accepted_answers)

    previous_streak, feedback = _score_answer(
        request,
        mode_key,
        progress,
        truth,
        correct,
    )
    progress.save(request.session)
    finished, outcome = _finished_outcome(
        mode,
        progress,
        correct,
        target,
        request.session.get("quiz_pool_size", 0),
    )
    if not finished:
        _set_current_country(request)
        return {"game_finished": False, "feedback": feedback}

    result = _result_payload(
        request,
        mode_key,
        progress,
        truth,
        outcome,
        target,
        feedback,
        final_streak=progress.streak if correct else previous_streak,
    )
    if mode_key == "daily":
        request.session["quiz_country"] = truth
    else:
        _start_game(request, mode_key)
    return result


def _score_answer(request, mode_key, progress, truth, correct):
    truth_name = truth["name"]
    previous_streak = progress.streak

    progress.answered += 1
    progress.seen.append(truth_name)
    _record_flag_attempt(request.user, truth_name, correct)

    if correct:
        progress.score += 1
        progress.streak += 1
        progress.collected.append(
            {
                "flag": truth.get("flag_image_url"),
                "name": truth_name,
                "fact": truth.get("fact") or "",
            }
        )
        if mode_key == "world_tour":
            update_high_score(request.user, progress.score)
        feedback = {"status": "success", "text": f"Correct — {truth_name}!"}
    else:
        progress.incorrect += 1
        progress.streak = 0
        if progress.lives is not None:
            progress.lives = max(0, progress.lives - 1)
        feedback = {
            "status": "error",
            "text": f"Not quite — that was {truth_name}.",
        }
    return previous_streak, feedback


def _finished_outcome(mode, progress, correct, target, pool_size):
    pool_exhausted = len(set(progress.seen)) >= pool_size if pool_size else True
    if mode.ruleset == "sudden_death" and not correct:
        return True, "lost"
    if mode.ruleset == "fixed" and (progress.answered >= target or pool_exhausted):
        return True, "completed"
    if mode.ruleset == "lives" and (
        progress.lives == 0
        or pool_exhausted
        or (target and progress.answered >= target)
    ):
        return True, "lost" if progress.lives == 0 else "completed"
    if mode.ruleset == "sudden_death" and pool_exhausted:
        return True, "completed"
    return False, "completed"


def _render_quiz_result(request, result):
    if request.htmx:
        return render(request, "quiz_active.html", _context(request, result))

    request.session["quiz_result"] = result
    if result.get("game_finished"):
        messages.success(request, result["feedback"]["text"])
    return redirect("quiz")


def change_gamemode(request):
    if request.method == "POST":
        clear_quiz_session(request.session)
    return redirect("quiz")


@login_required
def leaderboard(request):
    selected_mode = request.GET.get("mode", "world_tour")
    if selected_mode not in GAME_MODES:
        selected_mode = "world_tour"

    rows = (
        GameResult.objects.filter(gamemode=selected_mode)
        .values("user_id", "user__username")
        .annotate(best_score=Max("score"), games=Count("id"))
        .order_by("-best_score", "user__username")[:10]
    )
    top_players = [
        {
            "username": row["user__username"],
            "best_score": row["best_score"],
            "games": row["games"],
        }
        for row in rows
    ]
    mode = GAME_MODES[selected_mode]
    score_cap = mode.round_size
    if mode.ruleset == "sudden_death":
        score_cap = len(mode.filter_countries(get_countries()))

    return render(
        request,
        "leaderboard.html",
        {
            "top_players": top_players,
            "selected_mode": selected_mode,
            "selected_mode_name": mode.name,
            "mode_options": [
                {"key": key, "name": option.name}
                for key, option in GAME_MODES.items()
            ],
            "score_cap": score_cap,
        },
    )
