/* =========================================================
   CULINAAI VOICE INPUT
   Purpose:
   - Allows users to speak ingredients, allergies, equipment,
     utensils and additional instructions.
   - Uses the browser Web Speech API.
   - Automatically formats spoken list items with commas.
   - Works best in Google Chrome / Microsoft Edge.
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    const voiceButtons = document.querySelectorAll("[data-voice-target]");
    const statusBox = document.querySelector("[data-voice-status]");

    const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;

    let activeRecognition = null;
    let activeButton = null;

    if (!voiceButtons.length) {
        return;
    }

    if (!SpeechRecognition) {
        voiceButtons.forEach(function (button) {
            button.disabled = true;
            button.classList.add("voice-not-supported");
            button.setAttribute(
                "title",
                "Voice input is not supported in this browser. Please use Chrome or Edge."
            );
        });

        showVoiceStatus(
            "Voice input is not supported in this browser. Please use Google Chrome or Microsoft Edge.",
            "warning"
        );

        return;
    }

    voiceButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            const targetId = button.getAttribute("data-voice-target");
            const targetInput = document.getElementById(targetId);
            const mode = button.getAttribute("data-voice-mode") || "replace";

            if (!targetInput) {
                showVoiceStatus("Voice target field was not found.", "error");
                return;
            }

            if (activeRecognition) {
                activeRecognition.stop();
                resetActiveButton();
                return;
            }

            startVoiceRecognition(button, targetInput, mode);
        });
    });

    function startVoiceRecognition(button, targetInput, mode) {
        const recognition = new SpeechRecognition();

        recognition.lang = "en-GB";
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        activeRecognition = recognition;
        activeButton = button;

        button.classList.add("voice-listening");
        button.innerHTML = '<i class="bi bi-mic-fill"></i> Listening...';

        showVoiceStatus(
            "Listening now... speak clearly into your microphone.",
            "listening"
        );

        try {
            recognition.start();
        } catch (error) {
            showVoiceStatus("Voice input could not start. Please try again.", "error");
            activeRecognition = null;
            resetActiveButton();
            return;
        }

        recognition.onresult = function (event) {
            const spokenText = event.results[0][0].transcript.trim();

            if (!spokenText) {
                showVoiceStatus("No speech was detected. Please try again.", "warning");
                return;
            }

            const finalText = insertVoiceText(targetInput, spokenText, mode);

            showVoiceStatus(
                'Voice input added: "' + finalText + '"',
                "success"
            );
        };

        recognition.onerror = function (event) {
            let message = "Voice input stopped unexpectedly. Please try again.";

            if (event.error === "not-allowed") {
                message =
                    "Microphone permission was blocked. Please allow microphone access in your browser.";
            }

            if (event.error === "no-speech") {
                message = "No speech was detected. Please speak clearly and try again.";
            }

            if (event.error === "audio-capture") {
                message =
                    "No microphone was found. Please check your microphone settings.";
            }

            if (event.error === "network") {
                message =
                    "Voice input needs browser speech recognition access. Please check your internet connection and try again.";
            }

            showVoiceStatus(message, "error");
        };

        recognition.onend = function () {
            activeRecognition = null;
            resetActiveButton();
        };
    }

    function insertVoiceText(targetInput, spokenText, mode) {
        const cleanedText = cleanSpokenText(spokenText, targetInput);
        const currentValue = targetInput.value.trim();

        if (mode === "append" && currentValue.length > 0) {
            targetInput.value = currentValue + ", " + cleanedText;
        } else {
            targetInput.value = cleanedText;
        }

        targetInput.focus();

        targetInput.dispatchEvent(new Event("input", { bubbles: true }));
        targetInput.dispatchEvent(new Event("change", { bubbles: true }));

        return cleanedText;
    }

    function cleanSpokenText(text, targetInput) {
        let cleanedText = text
            .replace(/\s+/g, " ")
            .replace(/\s+,/g, ",")
            .replace(/,\s*/g, ", ")
            .trim();

        const targetId = targetInput.id || "";
        const targetName = targetInput.name || "";

        const shouldUseListFormatting =
            targetId.includes("ingredients") ||
            targetId.includes("allergies") ||
            targetId.includes("other_diet_preference") ||
            targetId.includes("other_kitchen_equipment") ||
            targetId.includes("other_utensils") ||
            targetName.includes("ingredients") ||
            targetName.includes("allergies");

        if (shouldUseListFormatting) {
            cleanedText = cleanedText
                .replace(/\bcomma\b/gi, ",")
                .replace(/\bcoma\b/gi, ",")
                .replace(/\band\b/gi, ",")
                .replace(/\bplus\b/gi, ",")
                .replace(/\balso\b/gi, ",")
                .replace(/\bwith\b/gi, ",")
                .replace(/\bas well as\b/gi, ",")
                .replace(/\salong with\s/gi, ", ")
                .replace(/\s*,\s*/g, ", ")
                .replace(/,+/g, ",")
                .replace(/^,\s*/, "")
                .replace(/,\s*$/, "")
                .trim();
        }

        return capitaliseFirstLetter(cleanedText);
    }

    function capitaliseFirstLetter(text) {
        if (!text) {
            return "";
        }

        return text.charAt(0).toUpperCase() + text.slice(1);
    }

    function resetActiveButton() {
        if (!activeButton) {
            return;
        }

        activeButton.classList.remove("voice-listening");
        activeButton.innerHTML = '<i class="bi bi-mic-fill"></i> Speak';
        activeButton = null;
    }

    function showVoiceStatus(message, type) {
        if (!statusBox) {
            return;
        }

        statusBox.hidden = false;
        statusBox.textContent = message;

        statusBox.classList.remove(
            "voice-status-success",
            "voice-status-error",
            "voice-status-warning",
            "voice-status-listening"
        );

        statusBox.classList.add("voice-status-" + type);

        if (type === "success") {
            setTimeout(function () {
                statusBox.hidden = true;
            }, 3500);
        }
    }
});