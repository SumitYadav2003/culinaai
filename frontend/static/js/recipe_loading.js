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

  const steps = [
    "Reading your ingredients...",
    "Checking cuisine, diet and allergies...",
    "Building a personalised recipe...",
    "Validating safety and recipe quality...",
    "Preparing cooking guidance...",
    "Almost ready..."
  ];

  let stepIndex = 0;
  let stepInterval = null;

  function updateStep() {
    if (!loadingStep) {
      return;
    }

    loadingStep.textContent = steps[stepIndex % steps.length];
    stepIndex += 1;
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

        const submitButton = form.querySelector(
          "button[type='submit'], input[type='submit']"
        );

        if (submitButton) {
          submitButton.disabled = true;
          submitButton.dataset.originalText = submitButton.innerHTML || submitButton.value || "";

          if (submitButton.tagName.toLowerCase() === "button") {
            submitButton.innerHTML =
              '<span class="spinner-border spinner-border-sm me-2"></span>Generating...';
          } else {
            submitButton.value = "Generating...";
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
