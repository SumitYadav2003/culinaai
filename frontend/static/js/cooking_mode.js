document.addEventListener("DOMContentLoaded", function () {
  const dataElement = document.getElementById("cookingStepsData");

  if (!dataElement) {
    return;
  }

  let steps = [];

  try {
    steps = JSON.parse(dataElement.textContent || "[]");
  } catch (error) {
    steps = [];
  }

  if (!steps.length) {
    steps = [
      {
        number: 1,
        title: "Cooking Step",
        text: "Review this recipe before cooking.",
        timer_minutes: 3,
      },
    ];
  }

  // Learning and voice settings from the server (cooking_learning_service.py).
  let config = {};

  try {
    config = JSON.parse(document.getElementById("cookingConfig")?.textContent || "{}");
  } catch (error) {
    config = {};
  }

  let currentStepIndex = 0;
  const completedSteps = new Set();

  let timerTotalSeconds = getStepDurationSeconds(currentStepIndex);
  let timerRemainingSeconds = timerTotalSeconds;
  let timerInterval = null;
  let timerRunning = false;
  let timerEndsAt = null;
  // The step the timer belongs to. A running timer keeps going when you move
  // to another step (the chicken is still roasting while you make the sauce).
  let timerStepIndex = 0;

  const currentStepNumber = document.getElementById("currentStepNumber");
  const currentStepTitle = document.getElementById("currentStepTitle");
  const currentStepText = document.getElementById("currentStepText");
  const stepCounterText = document.getElementById("stepCounterText");
  const progressPercentText = document.getElementById("progressPercentText");
  const progressFill = document.getElementById("cookingProgressFill");
  const completedStepsCount = document.getElementById("completedStepsCount");
  const previousStepBtn = document.getElementById("previousStepBtn");
  const nextStepBtn = document.getElementById("nextStepBtn");
  const completeStepBtn = document.getElementById("completeStepBtn");
  const timerDisplay = document.getElementById("timerDisplay");
  const timerStepLabel = document.getElementById("timerStepLabel");
  const startTimerBtn = document.getElementById("startTimerBtn");
  const pauseTimerBtn = document.getElementById("pauseTimerBtn");
  const resetTimerBtn = document.getElementById("resetTimerBtn");
  const finishCard = document.getElementById("cookingFinishCard");
  const stepButtons = Array.from(document.querySelectorAll("[data-step-button]"));

  function getStepDurationSeconds(index) {
    const minutes = Number(steps[index]?.timer_minutes || 3);
    return Math.max(1, minutes) * 60;
  }

  function formatTime(seconds) {
    const safeSeconds = Math.max(0, Number(seconds || 0));
    const minutes = Math.floor(safeSeconds / 60);
    const remainingSeconds = safeSeconds % 60;

    return String(minutes).padStart(2, "0") + ":" + String(remainingSeconds).padStart(2, "0");
  }

  // "17:47" (or "5:47 PM" for US English) for when a timer ends.
  function clockTime(time, lang) {
    try {
      return new Date(time).toLocaleTimeString(lang || config.english || undefined, { hour: "numeric", minute: "2-digit" });
    } catch (error) {
      return new Date(time).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    }
  }

  // "5 min", "1 min 30 s", "45 s" for labels.
  function shortDuration(seconds) {
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;

    if (!minutes) {
      return rest + " s";
    }

    return rest ? minutes + " min " + rest + " s" : minutes + " min";
  }

  // ---------------------------------------------------------------------
  // A short beep when a timer finishes (Web Audio, no sound file needed)
  // ---------------------------------------------------------------------

  let audioContext = null;

  function prepareSound() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;

    if (!audioContext && AudioContextClass) {
      try {
        audioContext = new AudioContextClass();
      } catch (error) {
        audioContext = null;
      }
    }

    if (audioContext && audioContext.state === "suspended") {
      audioContext.resume();
    }
  }

  function playBeep() {
    if (!audioContext) {
      return;
    }

    [0, 0.35, 0.7].forEach(function (offset) {
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      const start = audioContext.currentTime + offset;

      oscillator.type = "sine";
      oscillator.frequency.value = 880;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.25, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.25);
      oscillator.connect(gain).connect(audioContext.destination);
      oscillator.start(start);
      oscillator.stop(start + 0.3);
    });
  }

  // ---------------------------------------------------------------------
  // Recording how the user cooks (only while learning is on)
  // ---------------------------------------------------------------------

  const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  const MAX_STINT_SECONDS = 2 * 60 * 60;

  let learning = Boolean(config.learning);
  let sessionId = null;
  let meaningful = false;
  let sending = false;
  let sendAgain = false;
  let sendTimeout = null;
  let outcome = "";
  let voiceUsed = false;
  let stepOpenedAt = Date.now();

  const stepStats = steps.map(function (step, index) {
    return {
      number: step.number || index + 1,
      seconds: 0,
      repeats: 0,
      trouble: "",
      went_fine: false,
      note: "",
      completed: false,
      timer_used: false,
    };
  });

  function openSeconds() {
    return Math.min(MAX_STINT_SECONDS, Math.round((Date.now() - stepOpenedAt) / 1000));
  }

  // Adds the time the current step has been open to its total.
  function closeStint() {
    const seconds = openSeconds();

    stepStats[currentStepIndex].seconds += seconds;
    stepOpenedAt = Date.now();

    return seconds;
  }

  function buildPayload() {
    const liveSeconds = openSeconds();

    return {
      session_id: sessionId,
      voice_used: voiceUsed,
      outcome: outcome,
      steps: stepStats
        .map(function (stats, index) {
          return Object.assign({}, stats, {
            seconds: stats.seconds + (index === currentStepIndex ? liveSeconds : 0),
          });
        })
        .filter(function (stats) {
          return stats.seconds > 0 || stats.completed || stats.trouble || stats.repeats || stats.timer_used || stats.went_fine || stats.note;
        }),
    };
  }

  function sendNow() {
    if (!learning || !meaningful || !config.record_url) {
      return;
    }

    if (sending) {
      sendAgain = true;
      return;
    }

    sending = true;

    fetch(config.record_url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "fetch",
      },
      body: JSON.stringify(buildPayload()),
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        if (data.session_id) {
          sessionId = data.session_id;
        }

        if (data.learning === false) {
          setLearning(false, false);
        }
      })
      .catch(function () {
        // Saving is best-effort: cooking mode keeps working offline.
      })
      .finally(function () {
        sending = false;

        if (sendAgain) {
          sendAgain = false;
          sendNow();
        }
      });
  }

  function scheduleSend() {
    clearTimeout(sendTimeout);
    sendTimeout = setTimeout(sendNow, 800);
  }

  function noteActivity() {
    meaningful = true;
    scheduleSend();
  }

  // When the page is closed or hidden, send what we have without waiting.
  function sendOnLeave() {
    if (!learning || !meaningful || !config.record_url || !navigator.sendBeacon) {
      return;
    }

    if (sending && !sessionId) {
      return; // the first save is still on its way; avoid a duplicate session
    }

    const form = new FormData();
    form.append("csrfmiddlewaretoken", csrfToken);
    form.append("payload", JSON.stringify(buildPayload()));
    navigator.sendBeacon(config.record_url, form);
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      sendOnLeave();
    }
  });

  window.addEventListener("pagehide", sendOnLeave);

  setInterval(function () {
    if (meaningful) {
      sendNow();
    }
  }, 60000);

  // ---------------------------------------------------------------------
  // Timer
  // ---------------------------------------------------------------------

  function stopTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
    }

    timerInterval = null;
    timerRunning = false;
    timerEndsAt = null;
  }

  function resetTimerForCurrentStep() {
    stopTimer();
    timerStepIndex = currentStepIndex;
    timerTotalSeconds = getStepDurationSeconds(currentStepIndex);
    timerRemainingSeconds = timerTotalSeconds;
    renderTimer();
  }

  function renderTimer() {
    if (timerDisplay) {
      timerDisplay.textContent = formatTime(timerRemainingSeconds);
    }

    if (timerStepLabel) {
      timerStepLabel.textContent =
        "Timer for step " + (timerStepIndex + 1) + " · " + shortDuration(timerTotalSeconds) +
        (timerRunning && timerEndsAt ? " · ends " + clockTime(timerEndsAt) : "");
    }
  }

  function startTimer() {
    if (timerRunning) {
      return;
    }

    if (timerStepIndex !== currentStepIndex) {
      // A finished or paused timer from another step: start this step's timer instead.
      resetTimerForCurrentStep();
    } else if (timerRemainingSeconds <= 0) {
      timerRemainingSeconds = timerTotalSeconds;
    }

    prepareSound();
    timerRunning = true;
    timerEndsAt = Date.now() + timerRemainingSeconds * 1000;
    stepStats[currentStepIndex].timer_used = true;
    noteActivity();
    renderTimer();

    const timerStep = timerStepIndex;

    timerInterval = setInterval(function () {
      // Counted from the clock, so a busy or hidden tab doesn't make the timer drift.
      timerRemainingSeconds = Math.max(0, Math.round((timerEndsAt - Date.now()) / 1000));

      if (timerRemainingSeconds === 60 && timerTotalSeconds >= 180) {
        document.dispatchEvent(new CustomEvent("culina:timerminute", { detail: { step: timerStep + 1 } }));
      }

      if (timerRemainingSeconds <= 0) {
        timerRemainingSeconds = 0;
        stopTimer();
        playBeep();
        document.dispatchEvent(
          new CustomEvent("culina:timerdone", {
            detail: { step: timerStep + 1, seconds: timerTotalSeconds },
          })
        );
      }

      renderTimer();
    }, 1000);
  }

  function setTimerSeconds(seconds, start) {
    stopTimer();
    timerStepIndex = currentStepIndex;
    timerTotalSeconds = Math.max(1, Math.round(seconds));
    timerRemainingSeconds = timerTotalSeconds;
    renderTimer();

    if (start) {
      startTimer();
    }
  }

  function addTimerSeconds(seconds) {
    if (timerRemainingSeconds <= 0 && !timerRunning) {
      setTimerSeconds(seconds, true);
      return;
    }

    timerTotalSeconds += Math.round(seconds);
    timerRemainingSeconds += Math.round(seconds);

    if (timerRunning && timerEndsAt) {
      timerEndsAt += Math.round(seconds) * 1000;
    }

    renderTimer();

    if (!timerRunning) {
      startTimer();
    }
  }

  // ---------------------------------------------------------------------
  // Steps and progress
  // ---------------------------------------------------------------------

  function calculateProgressPercent() {
    return Math.round((completedSteps.size / steps.length) * 100);
  }

  function renderProgress() {
    const percent = calculateProgressPercent();

    if (progressPercentText) {
      progressPercentText.textContent = percent + "%";
    }

    if (progressFill) {
      progressFill.style.width = percent + "%";
    }

    if (completedStepsCount) {
      completedStepsCount.textContent = completedSteps.size;
    }

    if (finishCard) {
      if (completedSteps.size === steps.length) {
        if (!finishCard.classList.contains("show")) {
          renderTimeSummary();
        }

        finishCard.classList.add("show");
      } else {
        finishCard.classList.remove("show");
      }
    }
  }

  function renderStepList() {
    stepButtons.forEach(function (button) {
      const index = Number(button.dataset.stepIndex);

      button.classList.toggle("active", index === currentStepIndex);
      button.classList.toggle("completed", completedSteps.has(index));
    });
  }

  function renderCurrentStep() {
    const step = steps[currentStepIndex];

    if (!step) {
      return;
    }

    if (currentStepNumber) {
      currentStepNumber.textContent = step.number || currentStepIndex + 1;
    }

    if (currentStepTitle) {
      currentStepTitle.textContent = "Step " + (currentStepIndex + 1) + " of " + steps.length;
    }

    if (currentStepText) {
      currentStepText.textContent = step.text || "Review this step before continuing.";
    }

    if (stepCounterText) {
      stepCounterText.textContent = "Step " + (currentStepIndex + 1) + " of " + steps.length;
    }

    if (previousStepBtn) {
      previousStepBtn.disabled = currentStepIndex === 0;
    }

    if (nextStepBtn) {
      nextStepBtn.disabled = currentStepIndex === steps.length - 1;
    }

    if (completeStepBtn) {
      if (completedSteps.has(currentStepIndex)) {
        completeStepBtn.innerHTML = "<i class='bi bi-check2-circle'></i> Completed";
      } else {
        completeStepBtn.innerHTML = "<i class='bi bi-check2-circle'></i> Mark as Completed";
      }
    }

    renderStepList();
    renderProgress();
    renderTrouble();

    if (timerRunning) {
      renderTimer();
    } else {
      resetTimerForCurrentStep();
    }
  }

  function goToStep(index) {
    const safeIndex = Math.min(Math.max(index, 0), steps.length - 1);

    if (feedbackIndex !== null) {
      closeFeedback();
    }

    if (safeIndex !== currentStepIndex) {
      // Staying on a step for a while before moving on counts as cooking.
      if (closeStint() >= 10) {
        noteActivity();
      }
    }

    currentStepIndex = safeIndex;
    renderCurrentStep();
  }

  function markStepComplete(index) {
    completedSteps.add(index);
    stepStats[index].completed = true;
    noteActivity();
    renderStepList();
    renderProgress();

    if (index === currentStepIndex && completeStepBtn) {
      completeStepBtn.innerHTML = "<i class='bi bi-check2-circle'></i> Completed";
    }
  }

  // Marks the current step done. With learning on, asks how the step went
  // first; otherwise moves on to the next step, as before.
  function completeAndAdvance() {
    markStepComplete(currentStepIndex);

    if (learning) {
      showFeedback(currentStepIndex);
      return;
    }

    if (currentStepIndex < steps.length - 1) {
      setTimeout(function () {
        goToStep(currentStepIndex + 1);
      }, 450);
    }
  }

  stepButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      goToStep(Number(button.dataset.stepIndex));
    });
  });

  if (previousStepBtn) {
    previousStepBtn.addEventListener("click", function () {
      goToStep(currentStepIndex - 1);
    });
  }

  if (nextStepBtn) {
    nextStepBtn.addEventListener("click", function () {
      goToStep(currentStepIndex + 1);
    });
  }

  if (completeStepBtn) {
    completeStepBtn.addEventListener("click", completeAndAdvance);
  }

  if (startTimerBtn) {
    startTimerBtn.addEventListener("click", startTimer);
  }

  if (pauseTimerBtn) {
    pauseTimerBtn.addEventListener("click", function () {
      stopTimer();
    });
  }

  if (resetTimerBtn) {
    resetTimerBtn.addEventListener("click", function () {
      resetTimerForCurrentStep();
    });
  }

  // ---------------------------------------------------------------------
  // "Had trouble with this step?"
  // ---------------------------------------------------------------------

  const troubleBox = document.getElementById("stepTrouble");
  const troubleToggle = document.getElementById("troubleToggleBtn");
  const troubleChoices = document.getElementById("troubleChoices");
  const troubleNote = document.getElementById("troubleNote");
  const troubleButtons = Array.from(document.querySelectorAll("[data-trouble]"));
  const TROUBLE_WORDS = {
    longer: "it took longer",
    unclear: "the instructions were unclear",
    technique: "a tricky technique",
  };

  function renderTrouble() {
    if (!troubleBox) {
      return;
    }

    const chosen = stepStats[currentStepIndex].trouble;

    troubleButtons.forEach(function (button) {
      const selected = button.dataset.trouble === chosen;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });

    if (troubleNote) {
      troubleNote.textContent = chosen
        ? "Noted for step " + (currentStepIndex + 1) + ": " + TROUBLE_WORDS[chosen] + ". Tap it again to undo."
        : "";
    }

    if (chosen) {
      openTroubleChoices(true);
    } else if (troubleChoices && !troubleBox.dataset.keepOpen) {
      openTroubleChoices(false);
    }
  }

  function openTroubleChoices(open) {
    if (!troubleChoices || !troubleToggle) {
      return;
    }

    troubleChoices.hidden = !open;
    troubleToggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function setTrouble(reason) {
    const stats = stepStats[currentStepIndex];

    stats.trouble = stats.trouble === reason ? "" : reason;
    noteActivity();
    renderTrouble();
  }

  if (troubleToggle) {
    troubleToggle.addEventListener("click", function () {
      const open = troubleChoices ? troubleChoices.hidden : false;

      openTroubleChoices(open);
    });
  }

  troubleButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      setTrouble(button.dataset.trouble);
    });
  });

  // ---------------------------------------------------------------------
  // "How did step N go?" after each step (learning on)
  // ---------------------------------------------------------------------

  const feedbackPanel = document.getElementById("stepFeedback");
  const feedbackTitle = document.getElementById("feedbackTitle");
  const feedbackButtons = Array.from(document.querySelectorAll("[data-feedback]"));
  const feedbackNote = document.getElementById("feedbackNote");
  const feedbackNextBtn = document.getElementById("feedbackNextBtn");
  const feedbackSaved = document.getElementById("feedbackSaved");
  const actionRow = document.getElementById("stepActionRow");
  let feedbackIndex = null;

  function feelingOf(stats) {
    return stats.went_fine ? "fine" : stats.trouble;
  }

  function renderFeedback() {
    if (feedbackIndex === null) {
      return;
    }

    const stats = stepStats[feedbackIndex];
    const feeling = feelingOf(stats);

    feedbackButtons.forEach(function (button) {
      const selected = button.dataset.feedback === feeling;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });

    if (feedbackSaved) {
      feedbackSaved.textContent = feeling || stats.note ? "Saved to your cooking profile." : "";
    }
  }

  function showFeedback(index) {
    if (!feedbackPanel) {
      return;
    }

    feedbackIndex = index;
    feedbackPanel.hidden = false;

    // The question replaces the Previous / Completed / Next buttons, so there's one way on.
    if (actionRow) {
      actionRow.hidden = true;
    }

    if (troubleBox) {
      troubleBox.hidden = true;
    }

    if (feedbackTitle) {
      feedbackTitle.textContent = "How did step " + (index + 1) + " go?";
    }

    if (feedbackNote) {
      feedbackNote.value = stepStats[index].note || "";
    }

    if (feedbackNextBtn) {
      feedbackNextBtn.innerHTML =
        index < steps.length - 1 ? "Next step <i class='bi bi-arrow-right'></i>" : "Save <i class='bi bi-check2'></i>";
    }

    renderFeedback();
  }

  // feeling: "fine", "longer", "unclear", "technique" or "" (keep as it is).
  function setFeedback(index, feeling, note) {
    const stats = stepStats[index];

    if (!stats) {
      return;
    }

    if (feeling === "fine") {
      stats.went_fine = !(stats.went_fine && note === undefined);
      stats.trouble = "";
    } else if (feeling) {
      stats.trouble = stats.trouble === feeling && note === undefined ? "" : feeling;
      stats.went_fine = false;
    }

    if (note) {
      stats.note = String(note).slice(0, 300);

      if (feedbackNote && feedbackIndex === index) {
        feedbackNote.value = stats.note;
      }
    }

    noteActivity();
    renderFeedback();
    renderTrouble();
  }

  function saveTypedNote() {
    if (feedbackIndex === null || !feedbackNote) {
      return;
    }

    const typed = feedbackNote.value.trim().slice(0, 300);

    if (typed !== stepStats[feedbackIndex].note) {
      stepStats[feedbackIndex].note = typed;
      noteActivity();
    }
  }

  function closeFeedback() {
    saveTypedNote();
    feedbackIndex = null;

    if (feedbackPanel) {
      feedbackPanel.hidden = true;
    }

    if (actionRow) {
      actionRow.hidden = false;
    }

    if (troubleBox) {
      troubleBox.hidden = !learning;
    }
  }

  // Closes the question and goes to the next step (if there is one). Returns true if it moved.
  function finishFeedback() {
    const index = feedbackIndex;

    closeFeedback();

    if (index !== null && index === currentStepIndex && currentStepIndex < steps.length - 1) {
      goToStep(currentStepIndex + 1);
      return true;
    }

    return false;
  }

  feedbackButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      if (feedbackIndex !== null) {
        setFeedback(feedbackIndex, button.dataset.feedback);
      }
    });
  });

  if (feedbackNextBtn) {
    feedbackNextBtn.addEventListener("click", finishFeedback);
  }

  if (feedbackNote) {
    feedbackNote.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        finishFeedback();
      }
    });

    feedbackNote.addEventListener("change", saveTypedNote);
  }

  // ---------------------------------------------------------------------
  // Finish card: time taken and "How did it turn out?"
  // ---------------------------------------------------------------------

  const timeSummary = document.getElementById("cookingTimeSummary");
  const outcomeButtons = Array.from(document.querySelectorAll("[data-outcome]"));
  const outcomeNote = document.getElementById("outcomeNote");

  function totalCookingSeconds() {
    return stepStats.reduce(function (sum, stats) {
      return sum + stats.seconds;
    }, 0) + openSeconds();
  }

  function renderTimeSummary() {
    if (!timeSummary) {
      return;
    }

    const minutes = Math.max(1, Math.round(totalCookingSeconds() / 60));
    const estimate = Number(config.estimated_minutes || 0);

    timeSummary.textContent =
      "You spent about " + minutes + " minute" + (minutes === 1 ? "" : "s") + " in cooking mode" +
      (estimate ? "; the recipe estimated " + estimate + " minutes." : ".");
  }

  outcomeButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      outcome = button.dataset.outcome;

      outcomeButtons.forEach(function (other) {
        const selected = other === button;
        other.classList.toggle("selected", selected);
        other.setAttribute("aria-pressed", selected ? "true" : "false");
      });

      if (outcomeNote) {
        outcomeNote.textContent = "Thanks. Saved to your cooking profile on the dashboard.";
      }

      noteActivity();
      sendNow();
    });
  });

  // ---------------------------------------------------------------------
  // Learning on/off switch
  // ---------------------------------------------------------------------

  const learningSwitch = document.getElementById("learningSwitch");
  const learningState = document.getElementById("learningState");

  function saveSetting(name, value) {
    if (!config.settings_url) {
      return Promise.resolve(null);
    }

    const body = new URLSearchParams();
    body.append(name, value);

    return fetch(config.settings_url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "fetch",
      },
      body: body,
    })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .catch(function () {
        return null;
      });
  }

  function setLearning(on, save) {
    learning = Boolean(on);

    document.querySelectorAll("[data-learning-only]").forEach(function (element) {
      element.hidden = !learning;
    });

    if (learningSwitch) {
      learningSwitch.checked = learning;
    }

    if (learningState) {
      learningState.textContent = learning ? "On" : "Off";
    }

    if (save) {
      saveSetting("learn", learning ? "on" : "off");
    }

    if (learning && meaningful) {
      scheduleSend();
    }
  }

  if (learningSwitch) {
    learningSwitch.addEventListener("change", function () {
      setLearning(learningSwitch.checked, true);
    });
  }

  setLearning(learning, false);

  // ---------------------------------------------------------------------
  // Toolbar panels: "What can I say?" and "What's saved?"
  // ---------------------------------------------------------------------

  const panelButtons = Array.from(document.querySelectorAll("[data-panel-toggle]"));

  function openPanel(id, open) {
    panelButtons.forEach(function (button) {
      const panelElement = document.getElementById(button.dataset.panelToggle);
      const show = button.dataset.panelToggle === id ? open : false;

      if (panelElement) {
        panelElement.hidden = !show;
      }

      button.setAttribute("aria-expanded", show ? "true" : "false");
      button.classList.toggle("active", show);
    });
  }

  panelButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      openPanel(button.dataset.panelToggle, button.getAttribute("aria-expanded") !== "true");
    });
  });

  // ---------------------------------------------------------------------
  // For the hands-free voice (cooking_voice.js)
  // ---------------------------------------------------------------------

  window.CulinaCooking = {
    steps: steps,
    config: config,
    index: function () {
      return currentStepIndex;
    },
    completedCount: function () {
      return completedSteps.size;
    },
    isCompleted: function (index) {
      return completedSteps.has(index);
    },
    goToStep: goToStep,
    next: function () {
      goToStep(currentStepIndex + 1);
    },
    back: function () {
      goToStep(currentStepIndex - 1);
    },
    completeAndAdvance: completeAndAdvance,
    markStepComplete: markStepComplete,
    startTimer: startTimer,
    pauseTimer: stopTimer,
    resetTimer: resetTimerForCurrentStep,
    setTimerSeconds: setTimerSeconds,
    addTimerSeconds: addTimerSeconds,
    timer: function () {
      return {
        running: timerRunning,
        remaining: timerRemainingSeconds,
        total: timerTotalSeconds,
        endsAt: timerEndsAt,
        step: timerStepIndex,
      };
    },
    clockTime: clockTime,
    feedbackIndex: function () {
      return feedbackIndex;
    },
    setFeedback: setFeedback,
    finishFeedback: finishFeedback,
    closeFeedback: closeFeedback,
    setOutcome: function (value) {
      const button = document.querySelector("[data-outcome='" + value + "']");

      if (button) {
        button.click();
      }
    },
    markRepeat: function () {
      const stats = stepStats[currentStepIndex];
      stats.repeats = Math.min(50, stats.repeats + 1);
      noteActivity();
    },
    setTrouble: function (reason) {
      if (stepStats[currentStepIndex].trouble !== reason) {
        setTrouble(reason);
      }
    },
    showTroubleChoices: function () {
      openTroubleChoices(true);
    },
    markVoiceUsed: function () {
      if (!voiceUsed) {
        voiceUsed = true;
        noteActivity();
      }
    },
    prepareSound: prepareSound,
    isLearning: function () {
      return learning;
    },
    saveSetting: saveSetting,
    openPanel: openPanel,
  };

  renderCurrentStep();
});
