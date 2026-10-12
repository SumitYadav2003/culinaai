/* =========================================================
   CulinaAI Recipe Generation Loading Animation
   File: frontend/static/js/recipe_loading.js
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
  const loadingOverlay = document.querySelector("[data-culina-loading-overlay]");
  const loadingStep = document.querySelector("[data-culina-loading-step]");

  if (!loadingOverlay) {
    return;
  }

  const loadingTitle = document.querySelector("[data-culina-loading-title]");
  const loadingText = document.querySelector("[data-culina-loading-text]");

  // Used when the form doesn't bring its own steps (data-loading-steps="a|b|c").
  const defaultSteps = [
    "Reading your ingredients…",
    "Writing the recipe…",
    "Checking it against your diet and allergies…",
    "Working out nutrition, cost and carbon…",
    "Almost ready…"
  ];
  let steps = defaultSteps;

  let stepIndex = 0;
  let stepInterval = null;

  function updateStep() {
    if (!loadingStep) {
      return;
    }

    loadingStep.textContent = steps[stepIndex % steps.length];
    stepIndex += 1;
  }

  // Each form can describe what it's doing: making a recipe, changing one, cooking a version.
  function useFormText(form) {
    if (form.dataset.loadingTitle && loadingTitle) {
      loadingTitle.textContent = form.dataset.loadingTitle;
    }
    if (form.dataset.loadingText && loadingText) {
      loadingText.textContent = form.dataset.loadingText;
    }
    steps = form.dataset.loadingSteps ? form.dataset.loadingSteps.split("|") : defaultSteps;
  }

  function showLoading() {
    stepIndex = 0;
    updateStep();

    loadingOverlay.classList.add("show");
    document.body.classList.add("culina-loading-disabled");

    stepInterval = window.setInterval(updateStep, 1450);
  }

  function bindLoadingForms() {
    const forms = document.querySelectorAll("[data-recipe-loading-form]");

    forms.forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (typeof form.checkValidity === "function" && !form.checkValidity()) {
          return;
        }

        useFormText(form);

        const submitButton = form.querySelector(
          "button[type='submit'], input[type='submit']"
        );

        if (submitButton) {
          submitButton.disabled = true;
          submitButton.dataset.originalText = submitButton.innerHTML || submitButton.value || "";

          if (submitButton.tagName.toLowerCase() === "button") {
            submitButton.innerHTML =
              '<span class="spinner-border spinner-border-sm me-2"></span>' + (submitButton.dataset.busyText || "Working…");
          } else {
            submitButton.value = submitButton.dataset.busyText || "Working…";
          }
        }

        showLoading();
      });
    });
  }

  bindLoadingForms();

  window.addEventListener("pageshow", function () {
    loadingOverlay.classList.remove("show");
    document.body.classList.remove("culina-loading-disabled");

    if (stepInterval) {
      window.clearInterval(stepInterval);
      stepInterval = null;
    }
  });
});
