const playedQuizFeedback = new WeakSet();

function guessElements() {
    return {
        input: document.getElementById("guess"),
        dropdown: document.getElementById("guesses"),
    };
}

function submitGuess(text) {
    const { input, dropdown } = guessElements();
    if (!input || !dropdown) return;
    input.value = text;
    input.classList.add("bg-success");
    dropdown.replaceChildren();
    input.closest("form").requestSubmit();
}

function focusGuessInput(resetScroll = false) {
    const input = document.getElementById("guess");
    input?.focus({ preventScroll: true });
    if (resetScroll && document.getElementById("quiz-active")) {
        window.scrollTo(0, 0);
    }
}

function quizSoundEnabled() {
    return localStorage.getItem("quizSound") !== "off";
}

function refreshSoundToggles() {
    const enabled = quizSoundEnabled();
    document.querySelectorAll("[data-sound-toggle]").forEach((button) => {
        button.textContent = enabled ? "🔊 Sound" : "🔇 Sound";
        button.setAttribute("aria-pressed", String(enabled));
    });
}

function toggleQuizSound() {
    localStorage.setItem("quizSound", quizSoundEnabled() ? "off" : "on");
    refreshSoundToggles();
}

function playQuizFeedback() {
    refreshSoundToggles();
    const feedback = document.getElementById("quiz-feedback");
    if (!feedback?.dataset.status || !quizSoundEnabled() || playedQuizFeedback.has(feedback)) {
        return;
    }

    playedQuizFeedback.add(feedback);
    const source = feedback.dataset.status === "success"
        ? document.body.dataset.correctSound
        : document.body.dataset.incorrectSound;
    new Audio(source).play().catch(() => {});
}

function startQuizCountdown() {
    clearInterval(window.quizCountdown);
    const timer = document.getElementById("quiz-timer");
    if (!timer) return;

    const finishAt = Date.now() + Number(timer.dataset.seconds || 0) * 1000;
    window.quizCountdown = setInterval(() => {
        const seconds = Math.max(0, Math.ceil((finishAt - Date.now()) / 1000));
        timer.textContent = `${seconds}s`;
        if (seconds > 0) return;

        clearInterval(window.quizCountdown);
        const form = document.getElementById("guess-form");
        if (!form) return;

        const guess = form.querySelector('[name="guess"]');
        if (guess) guess.required = false;
        const action = document.createElement("input");
        action.type = "hidden";
        action.name = "quiz_action";
        action.value = "timeout";
        form.appendChild(action);
        form.requestSubmit();
    }, 250);
}

function initializeQuizRound(resetScroll = false) {
    focusGuessInput(resetScroll);
    playQuizFeedback();
    startQuizCountdown();
    document.getElementById("game_over_modal")?.showModal();
}

document.addEventListener("click", (event) => {
    if (event.target.closest("[data-sound-toggle]")) toggleQuizSound();

    if (event.target.closest("[data-quiz-hint]")) {
        document.getElementById("fact")?.classList.remove("hidden");
        document.getElementById("fact-button")?.classList.add("hidden");
    }

    const guessButton = event.target.closest("[data-guess]");
    if (guessButton) submitGuess(guessButton.dataset.guess);

    const { input, dropdown } = guessElements();
    if (input && dropdown && !dropdown.contains(event.target) && event.target !== input) {
        dropdown.replaceChildren();
    }
});

document.addEventListener("keydown", (event) => {
    const { input, dropdown } = guessElements();
    if (!input || !dropdown || document.activeElement !== input) return;

    if (event.key === "Escape") dropdown.replaceChildren();
    if (event.key === "Tab" || event.key === "Enter") {
        const firstButton = dropdown.querySelector("button");
        if (firstButton) {
            event.preventDefault();
            submitGuess(firstButton.dataset.guess);
        }
    }
    if (!input.value) input.classList.remove("bg-success");
});

document.addEventListener("htmx:afterSettle", (event) => {
    if (event.detail?.target?.id === "quiz-active") initializeQuizRound();
});

document.addEventListener("DOMContentLoaded", () => {
    initializeQuizRound(true);
});
