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

  let currentStepIndex = 0;
  const completedSteps = new Set();

  let timerTotalSeconds = getStepDurationSeconds(currentStepIndex);
  let timerRemainingSeconds = timerTotalSeconds;
  let timerInterval = null;
  let timerRunning = false;

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

  function stopTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
    }

    timerInterval = null;
    timerRunning = false;
  }

  function resetTimerForCurrentStep() {
    stopTimer();
    timerTotalSeconds = getStepDurationSeconds(currentStepIndex);
    timerRemainingSeconds = timerTotalSeconds;
    renderTimer();
  }

  function renderTimer() {
    if (timerDisplay) {
      timerDisplay.textContent = formatTime(timerRemainingSeconds);
    }

    if (timerStepLabel) {
      const minutes = steps[currentStepIndex]?.timer_minutes || 3;
      timerStepLabel.textContent = "Timer for step " + (currentStepIndex + 1) + " · " + minutes + " min";
    }
  }

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
      currentStepTitle.textContent = step.title || "Cooking Step";
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
    resetTimerForCurrentStep();
  }

  function goToStep(index) {
    const safeIndex = Math.min(Math.max(index, 0), steps.length - 1);
    currentStepIndex = safeIndex;
    renderCurrentStep();
  }

  function markCurrentStepComplete() {
    completedSteps.add(currentStepIndex);
    renderStepList();
    renderProgress();

    if (completeStepBtn) {
      completeStepBtn.innerHTML = "<i class='bi bi-check2-circle'></i> Completed";
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
    completeStepBtn.addEventListener("click", function () {
      markCurrentStepComplete();

      if (currentStepIndex < steps.length - 1) {
        setTimeout(function () {
          goToStep(currentStepIndex + 1);
        }, 450);
      }
    });
  }

  if (startTimerBtn) {
    startTimerBtn.addEventListener("click", function () {
      if (timerRunning) {
        return;
      }

      timerRunning = true;

      timerInterval = setInterval(function () {
        timerRemainingSeconds -= 1;

        if (timerRemainingSeconds <= 0) {
          timerRemainingSeconds = 0;
          stopTimer();
        }

        renderTimer();
      }, 1000);
    });
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

  renderCurrentStep();
});
