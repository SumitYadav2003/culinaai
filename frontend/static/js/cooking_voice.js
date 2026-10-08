/*
 * CulinaAI hands-free cooking voice.
 * File: frontend/static/js/cooking_voice.js
 *
 * Uses the browser's own Web Speech API: SpeechRecognition to listen and
 * speechSynthesis to talk. No AI and no paid service. Understanding the
 * words is done by cooking_voice_commands.js; this file listens, answers and
 * drives cooking mode through window.CulinaCooking (cooking_mode.js).
 *
 * Works best in Chrome and Edge. Firefox has no speech recognition, so the
 * button explains that and the page works by touch as before.
 */
document.addEventListener("DOMContentLoaded", function () {
  const cooking = window.CulinaCooking;
  const commands = window.CulinaVoiceCommands;
  const panel = document.getElementById("cookingVoicePanel");

  if (!cooking || !commands || !panel) {
    return;
  }

  const toggleBtn = document.getElementById("voiceToggleBtn");
  const toggleLabel = document.getElementById("voiceToggleLabel");
  const statusText = document.getElementById("voiceStatus");
  const heardText = document.getElementById("voiceHeard");
  const replyText = document.getElementById("voiceReply");
  const englishSelect = document.getElementById("voiceEnglish");
  const notice = document.getElementById("voiceNotice");
  const captionStatus = document.getElementById("voiceCaptionStatus");
  let captionTimer = null;

  // The bottom captions open when something is heard or said, and shrink back
  // to a small "Listening…" pill a few seconds later so they don't cover the step.
  function showCaption() {
    clearTimeout(captionTimer);
    panel.classList.add("has-caption");
  }

  function hideCaptionSoon() {
    clearTimeout(captionTimer);
    captionTimer = setTimeout(function () {
      if (!speaking) {
        panel.classList.remove("has-caption");
      }
    }, 6000);
  }

  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis || null;
  const steps = cooking.steps;
  const ingredients = cooking.config.ingredients || [];

  const ENGLISH_CODES = Array.from(englishSelect ? englishSelect.options : []).map(function (option) {
    return option.value;
  });

  // Voices to try when a device has none for the chosen English.
  const VOICE_FALLBACKS = {
    "en-IE": ["en-GB"],
    "en-NZ": ["en-AU", "en-GB"],
    "en-ZA": ["en-GB"],
    "en-IN": ["en-GB"],
    "en-AU": ["en-GB"],
    "en-CA": ["en-US"],
    "en-GB": [],
    "en-US": [],
  };

  let english = chooseEnglish();
  let enabled = false;
  let recognition = null;
  let restartTimer = null;
  let failures = [];
  let speaking = false;
  let speakQueue = [];
  let lastSpokeAt = 0;
  let rate = 1;
  let volume = 1;
  let lastAnswer = { text: "", kind: "" };
  let pendingTroubleAt = 0;
  let pendingOutcome = false;
  let timerHintGiven = new Set();
  let readSteps = new Set();
  let wakeLock = null;

  // ---------------------------------------------------------------------
  // Which English
  // ---------------------------------------------------------------------

  function chooseEnglish() {
    const saved = cooking.config.english;

    if (saved && ENGLISH_CODES.indexOf(saved) !== -1) {
      return saved;
    }

    const browser = (navigator.languages || [navigator.language || ""]).map(function (code) {
      return String(code).replace("_", "-");
    });

    for (const code of browser) {
      const match = ENGLISH_CODES.find(function (option) {
        return option.toLowerCase() === code.toLowerCase();
      });

      if (match) {
        return match;
      }
    }

    return "en-GB";
  }

  if (englishSelect) {
    englishSelect.value = english;
    englishSelect.addEventListener("change", function () {
      english = englishSelect.value;
      cooking.saveSetting("english", english);

      if (enabled) {
        restartListening();
        say("OK, I'll listen for " + englishSelect.options[englishSelect.selectedIndex].text + ".");
      }
    });
  }

  // ---------------------------------------------------------------------
  // Talking
  // ---------------------------------------------------------------------

  function pickVoice() {
    if (!synth) {
      return null;
    }

    const voices = synth.getVoices();
    const tryCodes = [english].concat(VOICE_FALLBACKS[english] || []);

    for (const code of tryCodes) {
      const matches = voices.filter(function (voice) {
        return String(voice.lang).replace("_", "-").toLowerCase() === code.toLowerCase();
      });

      if (matches.length) {
        return (
          matches.find(function (voice) {
            return /natural|neural|google|enhanced|premium/i.test(voice.name);
          }) || matches[0]
        );
      }
    }

    return (
      voices.find(function (voice) {
        return /^en/i.test(voice.lang);
      }) || null
    );
  }

  if (synth && typeof synth.addEventListener === "function") {
    synth.addEventListener("voiceschanged", function () {
      synth.getVoices();
    });
  }

  // Each new answer gets a number, so a cancelled answer's late "ended" event
  // can't start the next answer's sentences twice.
  let speechId = 0;
  let speechWatchdog = null;
  let spokenText = "";
  let ignoreHeardUntil = 0;

  function cancelSpeech() {
    speechId += 1;
    speakQueue = [];
    clearTimeout(speechWatchdog);

    if (synth) {
      synth.cancel();
    }
  }

  // After CulinaAI has spoken, everything the microphone heard meanwhile is
  // thrown away (it's mostly CulinaAI's own voice) by starting a fresh listen.
  function finishedSpeaking() {
    speaking = false;
    lastSpokeAt = Date.now();
    renderStatus();
    hideCaptionSoon();

    if (enabled) {
      ignoreHeardUntil = Date.now() + 350;
      restartListening();
    }
  }

  function stopSpeaking() {
    const wasSpeaking = speaking;

    cancelSpeech();

    if (wasSpeaking) {
      finishedSpeaking();
    }
  }

  function speakNext(id) {
    if (id !== speechId) {
      return;
    }

    clearTimeout(speechWatchdog);
    const chunk = speakQueue.shift();

    if (!chunk) {
      finishedSpeaking();
      return;
    }

    const utterance = new SpeechSynthesisUtterance(chunk.text);
    const voice = pickVoice();

    utterance.lang = voice ? voice.lang : english;

    if (voice) {
      utterance.voice = voice;
    }

    utterance.rate = Math.max(0.5, Math.min(1.6, rate * (chunk.slow ? 0.85 : 1)));
    utterance.volume = volume;
    utterance.onend = function () {
      speakNext(id);
    };
    utterance.onerror = function () {
      speakNext(id);
    };

    // Some browsers occasionally never send "ended"; don't get stuck "speaking".
    speechWatchdog = setTimeout(function () {
      speakNext(id);
    }, 4000 + chunk.text.length * 110 / utterance.rate);

    synth.speak(utterance);
  }

  function speak(text, options) {
    options = options || {};

    if (!synth || !text) {
      return;
    }

    const spoken = commands.speechText(text, english);

    cancelSpeech();
    speakQueue = commands.speechChunks(spoken).map(function (piece) {
      return { text: piece, slow: Boolean(options.slow) };
    });
    spokenText = spoken;
    speaking = true;
    renderStatus();
    speakNext(speechId);
  }

  // Shows the answer on screen and says it out loud.
  function say(text, options) {
    options = options || {};

    if (replyText) {
      replyText.textContent = text;
    }

    showCaption();
    lastAnswer = { text: options.speech || text, kind: options.kind || "answer", slow: options.slow };
    speak(options.speech || text, options);
  }

  function pick(list) {
    return list[Math.floor(Math.random() * list.length)];
  }

  function stepAnnouncement(index, prefix) {
    const step = steps[index];
    return (prefix || "") + "Step " + (index + 1) + ". " + (step.text || step.title || "");
  }

  function readStep(index, options) {
    options = options || {};

    const alreadyRead = readSteps.has(index);

    if (alreadyRead && options.countRepeat !== false) {
      cooking.markRepeat();
    }

    readSteps.add(index);

    // First time a step with its own time is read: say how to start its timer.
    let hint = "";
    const timer = cooking.timer();

    if (steps[index].timer_from_text && !timer.running && !timerHintGiven.has(index) && index === cooking.index()) {
      timerHintGiven.add(index);
      hint = " Say “start the timer” when you're ready for the " + minutesWords(timer.total) + ".";
    }

    say(stepAnnouncement(index, options.prefix) + hint, { kind: "step", slow: options.slow });
  }

  function finishWords() {
    const timer = cooking.timer();
    return timer.endsAt ? " It'll finish at " + cooking.clockTime(timer.endsAt, english) + "." : "";
  }

  const FEEDBACK_REPLIES = {
    fine: ["Great.", "Good to hear.", "Lovely."],
    longer: ["Noted: it took longer."],
    unclear: ["Noted: the instructions weren't clear."],
    technique: ["Noted: a tricky one."],
    "": ["Thanks, I've noted that."],
  };

  // After "How did that step go?": move on and read the next step, or ask about the whole dish.
  function moveOnAfterFeedback(reply) {
    const moved = cooking.finishFeedback();

    if (moved) {
      readStep(cooking.index(), { prefix: reply ? reply + " " : "", countRepeat: false });
    } else if (cooking.completedCount() === steps.length) {
      pendingOutcome = true;
      say((reply ? reply + " " : "") + "That's every step done. Well done! How did it turn out: great, OK, or not so good?");
    } else if (reply) {
      say(reply);
    }
  }

  function minutesWords(seconds) {
    const minutes = Math.floor(seconds / 60);
    const rest = Math.round(seconds % 60);
    const parts = [];

    if (minutes) {
      parts.push(minutes + (minutes === 1 ? " minute" : " minutes"));
    }

    if (rest || !minutes) {
      parts.push(rest + (rest === 1 ? " second" : " seconds"));
    }

    return parts.join(" and ");
  }

  function listWords(items) {
    if (items.length <= 1) {
      return items.join("");
    }

    return items.slice(0, -1).join(", ") + " and " + items[items.length - 1];
  }

  // ---------------------------------------------------------------------
  // Answering
  // ---------------------------------------------------------------------

  const HELP_TEXT =
    "You can say: read the step, next, back, repeat, or stop. " +
    "Start the timer, set a timer for 5 minutes, or how long left. " +
    "Done, to finish a step, and then tell me how it went. How much salt, or what temperature. " +
    "And I'm having trouble, if a step isn't going well. Say stop listening to turn me off.";

  function findTemperatureAnswer() {
    const current = cooking.index();
    const order = [current];

    for (let offset = 1; offset < steps.length; offset += 1) {
      if (current - offset >= 0) order.push(current - offset);
      if (current + offset < steps.length) order.push(current + offset);
    }

    for (const index of order) {
      const found = commands.findTemperature(steps[index].text);

      if (found) {
        const words = commands.describeTemperature(found, english);
        return index === current ? "For this step: " + words + "." : "Step " + (index + 1) + " says " + words + ".";
      }
    }

    return "This recipe doesn't give a temperature.";
  }

  function answerHowMuch(asked) {
    const found = commands.findIngredient(asked, ingredients);

    if (!found.lines.length) {
      return "I can't find " + asked + " in the ingredients for this recipe.";
    }

    const lines = listWords(found.lines);

    if (found.recipeWord) {
      return "The recipe calls it " + found.recipeWord + ": " + lines + ".";
    }

    return "The recipe says: " + lines + ".";
  }

  function act(command) {
    const index = cooking.index();
    const total = steps.length;
    const timer = cooking.timer();

    switch (command.intent) {
      case "next":
        if (index >= total - 1) {
          say("That's the last step. Say “done” when you've finished it.");
        } else {
          cooking.next();
          readStep(index + 1, { prefix: pick(["", "Right. ", "OK. ", "Here we go. "]), countRepeat: false });
        }
        break;

      case "back":
        if (index === 0) {
          say("You're on the first step.");
        } else {
          cooking.back();
          readStep(index - 1, { countRepeat: false });
        }
        break;

      case "read_step": {
        const number = command.step === "last" ? total : command.step;

        if (number < 1 || number > total) {
          say("This recipe has " + total + " step" + (total === 1 ? "" : "s") + ".");
        } else {
          cooking.goToStep(number - 1);
          readStep(number - 1);
        }
        break;
      }

      case "read_current":
        // "Start" or "go" on a step that's already been read starts its timer.
        if (command.start && readSteps.has(index)) {
          act({ intent: "timer_start" });
        } else {
          readStep(index);
        }
        break;

      case "repeat":
        if (lastAnswer.kind === "step" || !lastAnswer.text) {
          readStep(index);
        } else {
          say(lastAnswer.text, { kind: lastAnswer.kind });
        }
        break;

      case "complete":
        if (command.step && command.step !== index + 1) {
          if (command.step < 1 || command.step > total) {
            say("This recipe has " + total + " steps.");
          } else {
            cooking.markStepComplete(command.step - 1);

            if (cooking.completedCount() === total) {
              pendingOutcome = true;
              say("Step " + command.step + " marked as done. That's every step done. How did it turn out: great, OK, or not so good?");
            } else {
              say("Step " + command.step + " marked as done.");
            }
          }
          break;
        }

        cooking.completeAndAdvance();

        if (cooking.feedbackIndex() !== null) {
          say(pick(["Done. ", "Nice one. ", "Great. "]) + "How did that step go?", { kind: "question" });
        } else if (cooking.completedCount() === total) {
          say("That's every step done. Well done! How did it turn out? You can tap great, OK, or didn't go well.");
        } else if (index < total - 1) {
          readStep(index + 1, { prefix: pick(["Nice one. ", "Done. ", "Great. "]), countRepeat: false });
        } else {
          say("Done. " + (total - cooking.completedCount()) + " step" + (total - cooking.completedCount() === 1 ? " is" : "s are") + " still not ticked off.");
        }
        break;

      case "timer_start":
        if (timer.running && timer.step !== index) {
          say(
            "The timer for step " + (timer.step + 1) + " is still running, with " + minutesWords(timer.remaining) +
            " left. Say “reset the timer” to time this step instead."
          );
        } else if (timer.running) {
          say("The timer's already running: " + minutesWords(timer.remaining) + " left." + finishWords());
        } else {
          cooking.startTimer();
          say("Timer started: " + minutesWords(cooking.timer().remaining) + "." + finishWords() + " I'll tell you when it's done.");
        }
        break;

      case "timer_pause":
        cooking.pauseTimer();
        say("Timer paused with " + minutesWords(cooking.timer().remaining) + " left.");
        break;

      case "timer_reset":
        cooking.resetTimer();
        say("Timer reset to " + minutesWords(cooking.timer().total) + ".");
        break;

      case "timer_set":
        cooking.setTimerSeconds(command.seconds, true);
        say("Timer set for " + minutesWords(command.seconds) + "." + finishWords() + " I'll tell you when it's done.");
        break;

      case "timer_add":
        cooking.addTimerSeconds(command.seconds);
        say("Added " + minutesWords(command.seconds) + ". " + minutesWords(cooking.timer().remaining) + " left now." + finishWords());
        break;

      case "timer_left":
        if (timer.running) {
          say(minutesWords(timer.remaining) + " left on the timer" + (timer.step !== index ? " for step " + (timer.step + 1) : "") + "." + finishWords());
        } else if (timer.remaining === 0) {
          say("The timer has finished.");
        } else if (timer.remaining < timer.total) {
          say("The timer is paused with " + minutesWords(timer.remaining) + " left.");
        } else {
          say("This step's timer is " + minutesWords(timer.total) + ". Say “start the timer” when you're ready.");
        }
        break;

      case "steps_left": {
        const done = cooking.completedCount();
        const left = total - done;
        say(left ? "You've done " + done + " of " + total + " steps. " + left + " to go." : "All " + total + " steps are done!");
        break;
      }

      case "where":
        say("You're on step " + (index + 1) + " of " + total + ". " + (steps[index].text || ""), { kind: "step" });
        break;

      case "temperature":
        say(findTemperatureAnswer());
        break;

      case "how_much":
        say(answerHowMuch(command.ingredient));
        break;

      case "step_ingredients": {
        const lines = commands.ingredientsInStep(steps[index].text, ingredients);
        say(
          lines.length
            ? "For this step: " + listWords(lines) + "."
            : "I can't spot any of the listed ingredients in this step. Say “read the ingredients” to hear them all."
        );
        break;
      }

      case "all_ingredients":
        say(
          ingredients.length
            ? "There are " + ingredients.length + " ingredients: " + listWords(ingredients) + "."
            : "I couldn't find the ingredients list for this recipe."
        );
        break;

      case "trouble_ask":
        pendingTroubleAt = Date.now();
        cooking.showTroubleChoices();
        say("Sorry about that. Was it taking longer, were the instructions unclear, or is it a tricky technique?");
        break;

      case "trouble":
        pendingTroubleAt = 0;
        recordTrouble(command.reason);
        break;

      case "trouble_cancel":
        pendingTroubleAt = 0;
        say("No problem.");
        break;

      case "stop":
        if (speaking) {
          stopSpeaking();
        } else if (/^(pause|stop|pause it|stop it)$/.test(command.bare || "") && timer.running && Date.now() - lastSpokeAt > 2000) {
          cooking.pauseTimer();
          say("Timer paused with " + minutesWords(cooking.timer().remaining) + " left. Say “start the timer” to carry on.");
        } else {
          showReply("Stopped.");
        }
        break;

      case "slower":
        rate = Math.max(0.6, rate - 0.15);
        say("OK, I'll speak more slowly.");
        break;

      case "faster":
        rate = Math.min(1.5, rate + 0.15);
        say("OK, a bit faster.");
        break;

      case "normal_speed":
        rate = 1;
        volume = 1;
        say("Back to my normal voice.");
        break;

      case "louder":
        if (volume >= 1) {
          say("I'm already at full volume. Try turning up your device.");
        } else {
          volume = Math.min(1, volume + 0.25);
          if (command.repeat && lastAnswer.text) {
            say(lastAnswer.text, { kind: lastAnswer.kind });
          } else {
            say("Is this better?");
          }
        }
        break;

      case "quieter":
        volume = Math.max(0.25, volume - 0.25);
        say("Is this better?");
        break;

      case "help":
        cooking.openPanel("voiceHelp", true);
        say(HELP_TEXT);
        break;

      case "thanks":
        say(pick(["You're welcome.", "No problem.", "Any time.", "Happy to help."]));
        break;

      case "stop_listening":
        say("Hands-free is off. Tap the button to turn it back on.");
        setEnabled(false, true);
        break;

      case "step_feedback": {
        const feedbackStep = cooking.feedbackIndex();

        if (feedbackStep !== null) {
          cooking.setFeedback(feedbackStep, command.feeling, command.note || "");
        }

        moveOnAfterFeedback(pick(FEEDBACK_REPLIES[command.feeling || ""]));
        break;
      }

      case "feedback_skip":
        moveOnAfterFeedback("OK.");
        break;

      case "outcome":
        pendingOutcome = false;
        cooking.setOutcome(command.outcome);
        say(
          command.outcome === "great"
            ? "Brilliant. Saved to your cooking profile. Enjoy your meal!"
            : command.outcome === "ok"
              ? "Thanks, saved. Enjoy your meal."
              : "Sorry it didn't go well. I've saved that, so CulinaAI can help more next time."
        );
        break;

      default:
        if (command.addressed || command.words <= 3) {
          say("Sorry, I didn't catch that. Say “help” to hear what I can do.");
        }
    }
  }

  function recordTrouble(reason) {
    if (!cooking.isLearning()) {
      if (reason === "unclear") {
        say("Here it is again, a bit slower.", { speech: stepAnnouncement(cooking.index(), "Here it is again. "), kind: "step", slow: true });
      } else {
        say("Learning from your cooking is off, so I won't save that. Take your time.");
      }
      return;
    }

    cooking.setTrouble(reason);

    if (reason === "unclear") {
      say("Noted: the instructions weren't clear. Here it is again, a bit slower.", {
        speech: "Noted, the instructions weren't clear. " + stepAnnouncement(cooking.index(), "Here it is again. "),
        kind: "step",
        slow: true,
      });
    } else if (reason === "longer") {
      say("Noted: this step is taking longer than the recipe says. No rush. Say “add 5 minutes” if you need more time.");
    } else {
      say("Noted: a tricky technique. Take it slowly, and say “repeat” any time.");
    }
  }

  function showReply(text) {
    if (replyText) {
      replyText.textContent = text;
    }

    if (text) {
      showCaption();
      hideCaptionSoon();
    }
  }

  // ---------------------------------------------------------------------
  // Listening
  // ---------------------------------------------------------------------

  function handleFinal(alternatives) {
    const context = {
      pendingTrouble: Date.now() - pendingTroubleAt < 20000,
      pendingFeedback: cooking.feedbackIndex() !== null,
      pendingOutcome: pendingOutcome,
    };
    let chosen = null;
    let chosenText = alternatives[0] || "";

    for (const text of alternatives) {
      const parsed = commands.parse(text, context);

      if (parsed.intent !== "unknown") {
        chosen = parsed;
        chosenText = text;
        break;
      }
    }

    chosen = chosen || commands.parse(chosenText, context);

    if (heardText) {
      heardText.textContent = "Heard: “" + chosenText.trim() + "”" + (chosen.long ? " (not a command)" : "");
    }

    showCaption();
    hideCaptionSoon();

    if (chosen.intent !== "unknown") {
      cooking.markVoiceUsed();
    }

    if (pendingTroubleAt && chosen.intent !== "trouble_ask") {
      pendingTroubleAt = 0;
    }

    if (pendingOutcome && chosen.intent !== "outcome" && chosen.intent !== "repeat" && chosen.intent !== "unknown") {
      pendingOutcome = false;
    }

    act(chosen);
  }

  function renderStatus(message) {
    const text = message || (!enabled ? "Off" : speaking ? "Speaking…" : "Listening…");

    if (statusText) {
      statusText.textContent = text;
      statusText.hidden = text === "Off";
    }

    if (captionStatus) {
      captionStatus.textContent = text;
    }

    panel.classList.toggle("is-listening", enabled && !speaking);
    panel.classList.toggle("is-speaking", enabled && speaking);
  }

  function showNotice(message) {
    if (notice) {
      notice.textContent = message;
      notice.hidden = !message;
    }
  }

  function startListening() {
    if (!Recognition || !enabled) {
      return;
    }

    recognition = new Recognition();
    recognition.lang = english;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 3;

    recognition.onresult = function (event) {
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const transcript = result[0].transcript;

        // While CulinaAI is talking the microphone mostly hears CulinaAI, so
        // only listen for "stop", "wait", "hang on"... and act on nothing else.
        if (speaking) {
          if (commands.heardStop(transcript, spokenText)) {
            stopSpeaking();
            showReply("Stopped.");
          }

          continue;
        }

        if (Date.now() < ignoreHeardUntil) {
          continue; // the last echo of CulinaAI's voice
        }

        if (!result.isFinal) {
          if (heardText) {
            heardText.textContent = "Hearing: “" + transcript.trim() + "”";
          }

          continue;
        }

        handleFinal(
          Array.from(result).map(function (alternative) {
            return alternative.transcript;
          })
        );
      }
    };

    recognition.onerror = function (event) {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        showNotice("Microphone access is blocked. Allow the microphone for this site in your browser settings, then try again.");
        setEnabled(false, false);
      } else if (event.error === "audio-capture") {
        showNotice("No microphone was found on this device.");
        setEnabled(false, false);
      } else if (event.error === "language-not-supported") {
        showNotice("This browser can't listen for that English. Try English (UK) or English (US).");
        setEnabled(false, false);
      } else if (event.error === "network") {
        showNotice("Voice recognition in this browser needs an internet connection.");
      }
    };

    recognition.onend = function () {
      recognition = null;

      if (!enabled) {
        return;
      }

      // Browsers stop listening after a silence; start again, but give up if it keeps failing.
      const now = Date.now();
      failures = failures.filter(function (time) {
        return now - time < 30000;
      });
      failures.push(now);

      if (failures.length > 8) {
        showNotice("The microphone keeps stopping. Tap the button to try again.");
        setEnabled(false, false);
        return;
      }

      restartTimer = setTimeout(startListening, 250);
    };

    try {
      recognition.start();
    } catch (error) {
      // Already started.
    }
  }

  function stopListening() {
    clearTimeout(restartTimer);

    if (recognition) {
      recognition.onend = null;
      recognition.onresult = null;
      recognition.onerror = null;

      try {
        recognition.abort();
      } catch (error) {
        // Already stopped.
      }

      recognition = null;
    }
  }

  function restartListening() {
    stopListening();
    startListening();
  }

  // Keeps the screen on while hands-free is on, where the browser allows it.
  function holdScreen(on) {
    if (on && "wakeLock" in navigator && !wakeLock) {
      navigator.wakeLock
        .request("screen")
        .then(function (lock) {
          wakeLock = lock;
          lock.addEventListener("release", function () {
            wakeLock = null;
          });
        })
        .catch(function () {
          wakeLock = null;
        });
    } else if (!on && wakeLock) {
      wakeLock.release();
      wakeLock = null;
    }
  }

  document.addEventListener("visibilitychange", function () {
    if (enabled && document.visibilityState === "visible") {
      holdScreen(true);
    }
  });

  function setEnabled(on, keepSpeaking) {
    enabled = on;

    panel.classList.toggle("is-on", on);
    document.body.classList.toggle("cooking-captions-on", on);

    if (toggleBtn) {
      toggleBtn.classList.toggle("is-on", on);
      toggleBtn.setAttribute("aria-pressed", on ? "true" : "false");
    }

    if (toggleLabel) {
      toggleLabel.textContent = on ? "Turn off hands-free" : "Hands-free voice";
    }

    if (on) {
      failures = [];
      showNotice("");
      cooking.prepareSound();
      holdScreen(true);
      startListening();
    } else {
      stopListening();
      holdScreen(false);
      pendingTroubleAt = 0;

      if (!keepSpeaking) {
        stopSpeaking();
      }
    }

    renderStatus();
  }

  document.addEventListener("culina:timerdone", function (event) {
    if (enabled) {
      say("Time's up for step " + event.detail.step + ".");
    }
  });

  document.addEventListener("culina:timerminute", function () {
    if (enabled && !speaking) {
      say("One minute left on the timer.");
    }
  });

  if (!Recognition) {
    panel.classList.add("is-unsupported");

    if (toggleBtn) {
      toggleBtn.disabled = true;
    }

    showNotice("Hands-free voice needs Chrome or Edge (it isn't available in this browser). Everything else works by touch.");
    renderStatus("Not available");
    return;
  }

  if (toggleBtn) {
    toggleBtn.addEventListener("click", function () {
      if (enabled) {
        setEnabled(false, false);
        showReply("");
        return;
      }

      setEnabled(true, false);
      say(
        readSteps.size
          ? "Hands-free is on."
          : "Hands-free is on. Say “read the step” when you're ready, or “help” to hear what I can do."
      );
    });
  }

  renderStatus();
});
