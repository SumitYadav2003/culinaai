/*
 * CulinaAI hands-free cooking: understanding what the cook says.
 * File: frontend/static/js/cooking_voice_commands.js
 *
 * Plain code, no AI: each command has a list of everyday ways people say it
 * (British, American, Indian, Australian and other Englishes), so "carry on",
 * "what's next?" and "done that" all work, not just "next".
 *
 * parse(text) turns one heard sentence into {intent, ...}. It has no access to
 * the page, so it can be tested on its own:  node scripts/test_voice_commands.js
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.CulinaVoiceCommands = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Tidying what the browser heard
  // ---------------------------------------------------------------------

  const CONTRACTIONS = [
    [/\bcan't\b/g, "cannot"],
    [/\bwon't\b/g, "will not"],
    [/\bshan't\b/g, "shall not"],
    [/n't\b/g, " not"],
    [/\blet's\b/g, "let us"],
    [/\b(what|that|it|where|how|there|who|here|which|this|long|timer|step|everything|one|oven|pan|chicken|rice|water)'s\b/g, "$1 is"],
    [/'m\b/g, " am"],
    [/'re\b/g, " are"],
    [/'ll\b/g, " will"],
    [/'ve\b/g, " have"],
    [/'d\b/g, " would"],
  ];

  // Speech recognition often writes these without the apostrophe.
  const BARE_CONTRACTIONS = [
    [/\bdont\b/g, "do not"],
    [/\bdoesnt\b/g, "does not"],
    [/\bdidnt\b/g, "did not"],
    [/\bcant\b/g, "cannot"],
    [/\bwhats\b/g, "what is"],
    [/\bthats\b/g, "that is"],
    [/\bwheres\b/g, "where is"],
    [/\bim\b/g, "i am"],
    [/\bits\b/g, "it is"],
    [/\blets\b/g, "let us"],
    [/\bcan not\b/g, "cannot"],
  ];

  function normalise(raw) {
    let text = String(raw || "").toLowerCase();
    text = text.replace(/[\u2018\u2019\u02bc`]/g, "'");
    CONTRACTIONS.forEach(function (pair) {
      text = text.replace(pair[0], pair[1]);
    });
    text = text.replace(/-/g, " ");
    text = text.replace(/(\d)\.(\d)/g, "$1qdotq$2");
    text = text.replace(/[^a-z0-9' ]+/g, " ").replace(/'/g, "");
    text = text.replace(/qdotq/g, ".");
    BARE_CONTRACTIONS.forEach(function (pair) {
      text = text.replace(pair[0], pair[1]);
    });
    return text.replace(/\s+/g, " ").trim();
  }

  // Polite wrappers and fillers around the actual command.
  const LEADING = [
    /^(hey|hi|hello|ok|okay|right|alright|all right|so|um|umm|uh|erm|er|oh|well|and|just|please|mate|yeah|yes|yep|ah)\b ?/,
    /^(culina ai|culinaai|culina|colina|culinary|kulina)\b ?/,
    /^(can|could|would|will) you (please )?/,
    /^(can|could|may) (i|we) (have|get) /,
    /^i (want|need|would like) you to /,
    /^(would|do) you mind /,
  ];
  const TRAILING = [
    / (please|for me|for us|mate|love|thanks|thank you|cheers|if you can|if you could|if you would|culina|culina ai|then please)$/,
  ];

  function stripWrappers(text) {
    let current = text;
    let previous = null;
    while (current !== previous) {
      previous = current;
      LEADING.forEach(function (pattern) {
        const next = current.replace(pattern, "");
        if (next) current = next;
      });
      TRAILING.forEach(function (pattern) {
        current = current.replace(pattern, "");
      });
      current = current.trim();
    }
    return current;
  }

  // ---------------------------------------------------------------------
  // Numbers: "step two", "the second step", "twenty five minutes"
  // ---------------------------------------------------------------------

  const UNITS = {
    zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
    eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17,
    eighteen: 18, nineteen: 19,
  };
  const TENS = { twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90 };
  const ORDINALS = {
    first: 1, second: 2, third: 3, fourth: 4, fifth: 5, sixth: 6, seventh: 7, eighth: 8, ninth: 9, tenth: 10,
    eleventh: 11, twelfth: 12, thirteenth: 13, fourteenth: 14, fifteenth: 15, sixteenth: 16,
    seventeenth: 17, eighteenth: 18, nineteenth: 19, twentieth: 20,
  };

  function wordsToNumbers(text) {
    const words = text.split(" ");
    const out = [];
    for (let i = 0; i < words.length; i += 1) {
      const word = words[i];
      if (word in TENS) {
        let value = TENS[word];
        if (words[i + 1] in UNITS && UNITS[words[i + 1]] < 10) {
          value += UNITS[words[i + 1]];
          i += 1;
        }
        out.push(String(value));
      } else if (word in UNITS) {
        out.push(String(UNITS[word]));
      } else {
        out.push(word);
      }
    }
    let result = out.join(" ");
    // Ordinals only next to "step", so "30 seconds" stays a time.
    result = result.replace(/\b([a-z]+) step\b/g, function (match, word) {
      return word in ORDINALS ? ORDINALS[word] + " step" : match;
    });
    result = result.replace(/\bstep ([a-z]+)\b/g, function (match, word) {
      return word in ORDINALS ? "step " + ORDINALS[word] : match;
    });
    result = result.replace(/\b(\d+)(st|nd|rd|th)\b/g, "$1");
    // What speech recognition often writes for a spoken number after "step".
    result = result.replace(/\bstep (to|too)\b/g, "step 2").replace(/\bstep (for|fore)\b/g, "step 4");
    result = result.replace(/\bstep won\b/g, "step 1").replace(/\bstep ate\b/g, "step 8");
    return result;
  }

  // "5 minutes", "a minute and a half", "half an hour", "1 minute 30 seconds" -> seconds
  function parseDuration(numberText) {
    let text = " " + numberText + " ";
    text = text
      .replace(/ (an|a|1) (hour|hr) and a half /g, " 90 minutes ")
      .replace(/ (a|1) (minute|min) and a half /g, " 90 seconds ")
      .replace(/ half (an|a) (hour|hr) /g, " 30 minutes ")
      .replace(/ half (an|a) hour /g, " 30 minutes ")
      .replace(/ (a )?quarter (of )?(an )?(hour|hr) /g, " 15 minutes ")
      .replace(/ half (a|1) (minute|min) /g, " 30 seconds ")
      .replace(/ (\d+) and a half (hours?|minutes?|mins?) /g, " $1.5 $2 ")
      .replace(/ (another|1 more|one more) (hour|minute|second|min|sec) /g, " 1 $2 ")
      .replace(/ (\d+(?:\.\d+)?) (more|extra|additional) /g, " $1 ")
      .replace(/ (a couple of|a couple|couple of) /g, " 2 ")
      .replace(/ a few /g, " 3 ")
      .replace(/ (an|a) (hour|minute|second|sec|min) /g, " 1 $2 ");

    // "3 to 4 minutes" or "3-4 minutes": use the longer time.
    text = text.replace(/ (\d+(?:\.\d+)?) (to|or)? ?(\d+(?:\.\d+)?) (hours?|hrs?|minutes?|mins?|seconds?|secs?) /g, " $3 $4 ");

    const pattern = /(\d+(?:\.\d+)?) ?(hours?|hrs?|minutes?|mins?|seconds?|secs?)\b/g;
    let total = 0;
    let found = false;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      const value = parseFloat(match[1]);
      const unit = match[2];
      if (unit.startsWith("h")) total += value * 3600;
      else if (unit.startsWith("m")) total += value * 60;
      else total += value;
      found = true;
    }
    if (!found || total <= 0) return null;
    return Math.min(Math.round(total), 4 * 3600);
  }

  // ---------------------------------------------------------------------
  // The commands, most specific first
  // ---------------------------------------------------------------------

  const HEAT_WORDS = /\b(heat|hob|stove|oven|gas|flame|burner|cooker)\b/;

  const PATTERNS = {
    stopListening: /\b(stop listening|turn off (the )?(voice|mic|microphone|hands free|listening)|turn (the )?(voice|mic|microphone|hands free) off|switch off (the )?(voice|mic|microphone|hands free)|switch (the )?(voice|mic|microphone|hands free) off|(voice|mic|microphone|hands free) off|disable (the )?(voice|hands free)|goodbye|good bye|bye bye|i am done cooking|we are done here|we are done|all finished cooking|i have finished cooking|finished cooking|that is all for (now|today)|go to sleep|stop the voice)\b|^bye$/,
    help: /^(help|help me|help please|what can i say|what can i ask( you)?|what can you do|what can you help with|what do i say|what are the commands|commands|voice commands|options|list commands|list the commands|how does this work|how do i use (this|you)|what are my options)$|\bwhat (can|should|do) i say\b|\bwhat commands\b/,
    thanks: /^(thanks|thank you|thank you very much|thanks very much|thanks a lot|thanks so much|thank you so much|many thanks|cheers|ta|ta very much|nice one|much appreciated|appreciate it|lovely|brilliant|perfect|great|awesome|cool|nice|excellent|fab|fabulous|sweet|good job|well done)( (mate|love|culina|so much|then))?$/,
    stop: /^(stop now|hush now|quiet now|shush now|pause it|pause that|pause please|stop|stop it|stop that|stop now|stop talking|stop reading|stop speaking|shush|shh+|sh|hush|quiet|be quiet|quiet please|silence|enough|that is enough|ok ok|okay okay|ok stop|okay stop|no stop|alright stop|hang on|hang on a (sec|second|minute|moment|tick)|hold on|hold on a (sec|second|minute|moment|tick)|wait|wait a (sec|second|minute|moment|tick)|1 sec|1 second|one sec|one second|one moment|1 moment|just a (sec|second|minute|moment|tick)|a (sec|second|minute|moment|tick)|give me a (sec|second|minute|moment|tick)|cancel|pause|shut up|zip it|got it|ok got it|okay got it|understood|that is fine|fine|ok|okay|alright|right)$/,

    louder: /\b(louder|speak up|volume up|turn (it |the volume |the voice )?up|cannot hear( you| that| it)?|could not hear( you| that| it)?|too quiet|more volume|increase (the )?volume)\b/,
    quieter: /\b(quieter|softer|volume down|turn (it |the volume |the voice )?down|too loud|not so loud|less loud|lower (your |the )?(voice|volume)|decrease (the )?volume)\b/,
    slower: /\b(slow( it)? down|slower|too fast|more slowly|slowly|not so fast)\b/,
    faster: /\b(faster|speed up|speed it up|quicker|more quickly|too slow|hurry up)\b/,
    normalSpeed: /\b(normal speed|normal voice|reset (the )?(voice|speed))\b/,

    troubleUnclear: /\b((do not|did not|cannot) (understand|get (it|this|that)|follow)|(does not|do not) make (any )?sense|makes no sense|confus(ed|ing)|not clear|unclear|what does (that|this|it) mean|what do you mean)\b/,
    troubleLonger: /\b(taking (too long|ages|forever|longer|a long time|so long|a while)|takes (too long|ages|forever|longer)|took (too long|ages|forever|longer|a long time)|running (late|behind)|behind schedule|need more time|(is|are) not (done|ready|cooked) yet|still not (done|ready|cooked))\b/,
    troubleTechnique: /\b(tricky|too hard|really hard|(this|it|that) is hard|difficult|struggling|struggle|cannot do (this|it|that)|how do i (do that|do this|do it)|not sure how|fiddly)\b/,
    troubleAsk: /\b((having|got|have|had|i have) (some |a |a bit of )?(trouble|problems?|difficulty|issues?|a problem)|i am stuck|stuck|i am (a bit |totally |completely )?lost$|not sure what to do|do not know what to do|(it|this|that) is not working|(something|it) (went|has gone|is going) wrong|messed (it |this |that )?up|help (me )?with (this|the) step|need help|i need some help)\b/,

    timerLeft: /\b(how (much )?(long|longer|time|many (minutes|seconds))( is| do i have| have i got| do we have)?( left| to go| remaining)?|time (left|remaining)|is it (done|ready|finished) yet|is (the )?timer (done|finished|up)|how is the timer|what is (left on )?the timer|check (the )?timer)\b/,
    // "add 5 minutes", "another 2 minutes", "2 more minutes", "add another minute"; not "add the onion ... for 4 minutes"
    timerAdd: /\b(add|plus|another|extra)( on)?( an| a| another| extra| more)? (\d+(\.\d+)?|a|an|couple|few)( more| extra)? ?(hours?|hrs?|minutes?|mins?|seconds?|secs?)?\b|\b\d+(\.\d+)? (more|extra|additional) (hours?|hrs?|minutes?|mins?|seconds?|secs?)\b|\b(another|1 more|one more|a few more|a couple more) (hour|minute|min|second|sec)s?\b/,
    timerSetWord: /\b(timer|remind|give me|time me|set|countdown|count down|wait|alarm|stopwatch)\b/,
    timerPause: /\b(pause|stop|hold|freeze|halt)( the| my)? (timer|clock|countdown|count down)\b|\b(timer|clock) (pause|stop|off|hold)\b/,
    timerReset: /\b(reset|restart)( the| my)? (timer|clock|countdown)\b|\b(timer|clock) (reset|restart)\b|\bstart (the )?(timer|clock) (again|over)\b/,
    timerStart: /\b(start|begin|resume|run|go|set off|kick off|continue|unpause|turn on|switch on)( the| my)? (timer|clock|countdown|count down)\b|\b(timer|clock) (on|start|go)\b|^(time me|start timing|start counting|resume|timer|the timer|clock|start the clock)$/,

    stepsLeft: /\bhow many (more )?steps\b|\bsteps (left|to go|remaining)\b|\b(nearly|almost) (done|there|finished)\b|\bhow (far|close) (am i|are we)\b|\bhow many (more|left|to go)$|^what is left( to do)?$|^(much|anything) left$/,
    where: /\bwhere (was|am|were|are) (i|we)\b|\b(which|what) step\b|\blost my place\b|\bwhat number (step )?(am i on|is this)\b/,
    temperature: /\b(temperature|temp|gas mark|degrees|celsius|fahrenheit)\b|\bhow hot\b|\b(what|which|how much) heat\b|\bwhat (setting|level)\b|\bpreheat\b|\bheat (level|setting)\b|\bhigh or low\b|\bwhat (oven|hob|stove)\b/,
    howMuch: /\b(how much|how many|what amount of|what quantity of|quantity of|amount of)( of)?( the)? (.+)$/,
    allIngredients: /\b(read|list|tell me|what are|go through)( me| out| us)?( all)? the ingredients\b|^(ingredients|ingredient list|ingredients list|the ingredients|all the ingredients)$|\bshopping list\b/,
    stepIngredients: /\bwhat (do|will|should) (i|we) need\b|\b(what|which) ingredients\b|\bwhat goes (in|into)\b|\bwhat (am i|do i|should i|are we) (add|adding|use|using|put in|putting in)\b|\bingredients for this\b/,
    stepNumber: /\bstep (?:number )?(\d+)\b|\b(\d+) step\b/,
    firstStep: /\b(the )?(first|1) (step|one)\b|\b(start|go back|back|start again) (from|to) the (beginning|start|top)\b|\bfrom the (beginning|start|top)\b|^(start again|start over|from the top)$/,
    lastStep: /\bthe (final|very last) step\b|\b(read|go to|skip to|jump to) the last step\b|\bgo to the end\b|\bskip to the end\b/,
    completeLoose: /^(i am |i have |i have just |just )?(done|finished|completed?)( with)? (that|this|it)( bit| one| part| step)?$|^(that|this)( bit| one| part| step)? is (done|finished|complete)$|^(this|that) (1|one) is (done|finished)$/,
    complete: /^(done|i am done|all done|finished|i (have )?finished|i am finished|that is (done|finished)|done (that|it|this|this step|with (that|this|it))|finished (that|it|this|this step|with (that|this|it))|completed?|complete (it|this|that|the step|this step)|(that|this) step is (done|finished|complete)|step (done|complete|completed|finished)|mark( it| this| that| this step| the step)?( as)? (done|complete|completed|finished)|tick (it|that|this)( off)?|tick off|check|checked|did it|did that|i did it|i have done (it|that)|(ok|okay|yep|yes|yeah) (done|finished))$/,
    next: /\bnext\b|^(go on|carry on|keep going|continue|onwards|onward|forward|move on|moving on|and then|then what|then|after that|what is after (this|that)|skip|skip (it|this|this step|that)|go forward|skip ahead|go ahead|move ahead|forward 1|next bit|the next bit)$|\bwhat (do i do|comes|happens) (next|after (this|that))\b/,
    back: /\b(go back|take me back|previous|prev|before (that|this)|the 1 before|step back|last step|back up|rewind|go backwards)\b|^back$|^(back please|back 1)$/,
    repeat: /\b(repeat|say (that|it|this) again|again please|come again|1 more time|one more time|what was that|what did you say|i did not (hear|catch) (that|you|it|what you said)|missed that|say again|once more|read (it|that|this) again|go again|again)\b|^(pardon|pardon me|sorry|sorry what|what|huh|eh|eh what|huh what|what what|excuse me|beg your pardon|i beg your pardon)$/,
    ready: /^(i am ready|ready|let us go|let us start|let us begin|let us cook|start|begin|start cooking|begin cooking|go|go ahead|start reading|ok go|okay go|start the recipe|begin the recipe)$/,
    read: /\b(read|what does (it|this|that) say|what do (i|we) (do|have to do|need to do)( now| here| first)?$|what now|what am i (doing|supposed to do)|tell me (the|this|what)|what is (this|the|the current) step|instructions|say it)\b/,
  };

  const TROUBLE_REPLIES = {
    longer: /\b(long|longer|ages|slow|time|forever|took|taking|1|first|option 1|number 1)\b/,
    unclear: /\b(unclear|instruction|instructions|confus\w*|understand|clear|sense|explain|wording|words|2|second|option 2|number 2)\b/,
    technique: /\b(tricky|technique|hard|difficult|skill|fiddly|method|how to|3|third|option 3|number 3)\b/,
    cancel: /^(no|nope|never mind|nevermind|cancel|nothing|forget it|it is fine|all good|it is ok|it is okay|no thanks|does not matter|it does not matter)$/,
  };

  // Words that show the cook was talking to CulinaAI, so an unknown sentence
  // gets a "didn't catch that" instead of silence.
  const ADDRESSED = /\b(culina|colina|step|timer|read|recipe|minutes?|ingredients?|repeat|next)\b/;

  const HOW_MUCH_TAIL = / (do|should|will|shall) (i|we) (need|use|add|put|put in|have)$| (goes|go) in$| (is|are) (needed|it|there|in it)$| in (this|the) (step|recipe|dish)$| for (this|the) (step|recipe|dish)$| does it (need|take|use)$| in it$| altogether$| in total$| again$| do i need for this$/;
  const NOT_INGREDIENTS = /^(time|longer|long|more|steps?|left|minutes?|seconds?|heat|people|servings?|is left|to go)$/;

  function cleanIngredient(text) {
    let current = text;
    let previous = null;
    while (current !== previous) {
      previous = current;
      current = current.replace(HOW_MUCH_TAIL, "").trim();
    }
    return current;
  }

  // "cheers, that's great" or "that's lovely, thanks": only thank-you words.
  const THANKS_WORDS = new Set(["thanks", "thank", "you", "very", "much", "cheers", "ta", "nice", "one", "lovely",
    "brilliant", "perfect", "great", "awesome", "cool", "that", "is", "was", "mate", "love", "so", "a", "lot",
    "appreciated", "appreciate", "it", "excellent", "fab", "fabulous", "good", "job", "well", "really", "helpful"]);
  const THANKS_KEY = /\b(thanks|thank|cheers|ta|lovely|brilliant|perfect|great|awesome|cool|excellent|fab|fabulous|appreciate|appreciated|helpful)\b/;

  function isThanks(text) {
    return THANKS_KEY.test(text) && text.split(" ").every(function (word) { return THANKS_WORDS.has(word); });
  }

  function wordCount(text) {
    return text ? text.split(" ").length : 0;
  }

  // Commands that make sense in a long sentence. Anything else said in more
  // than 8 words is probably kitchen conversation (or CulinaAI's own voice).
  const LONG_OK = new Set(["how_much", "temperature", "trouble", "trouble_ask", "help", "stop_listening", "louder",
    "step_ingredients", "all_ingredients", "where", "steps_left", "timer_left"]);
  const MAX_COMMAND_WORDS = 7;
  const SMALL_WORDS = new Set(["a", "an", "the", "and", "for", "to", "of", "me", "please", "i", "it", "is", "my", "on", "in",
    "you", "could", "can", "would", "that", "this", "just", "so", "sorry", "now"]);

  // While CulinaAI is waiting for "How did that step go?", these still work as commands.
  const COMMANDS_DURING_QUESTION = new Set(["timer_start", "timer_pause", "timer_reset", "timer_set", "timer_add",
    "timer_left", "read_step", "help", "stop_listening", "repeat", "how_much", "temperature", "back", "where",
    "steps_left", "louder", "quieter", "slower", "faster", "all_ingredients", "step_ingredients"]);
  const SKIP_ANSWER = /^(skip|skip it|no|nope|never mind|nevermind|nothing|no comment|pass|next|next step|next 1|next one|move on|carry on|go on|nothing to say|no thanks|not now|done|ok done|okay done|later)$/;

  function parse(raw, context) {
    context = context || {};
    const heard = normalise(raw);
    const text = stripWrappers(heard);

    if (text && context.pendingOutcome) {
      const outcome = parseOutcome(heard);
      if (outcome) return { intent: "outcome", outcome: outcome, heard: heard, words: wordCount(text) };
    }

    if (text && context.pendingFeedback) {
      const words = wordCount(text);
      if (SKIP_ANSWER.test(text)) return { intent: "feedback_skip", heard: heard, words: words };
      if (PATTERNS.stop.test(text) && !/^(ok|okay|alright|right|fine|that is fine)$/.test(text)) {
        return { intent: "stop", bare: text, heard: heard, words: words };
      }
      const command = parseCommand(raw, context);
      if (COMMANDS_DURING_QUESTION.has(command.intent)) return command;
      const feedback = parseFeedback(raw);
      return Object.assign({ intent: "step_feedback", heard: heard, words: words }, feedback);
    }

    const command = parseCommand(raw, context);
    const contentWords = text.split(" ").filter(function (word) { return !SMALL_WORDS.has(word); }).length;
    if (contentWords > MAX_COMMAND_WORDS && !LONG_OK.has(command.intent) && command.intent !== "unknown") {
      return { intent: "unknown", heard: command.heard, words: command.words, long: true, addressed: false };
    }
    return command;
  }

  function parseCommand(raw, context) {
    context = context || {};
    const heard = normalise(raw);
    const text = stripWrappers(heard);
    const numbers = wordsToNumbers(text);
    const result = function (intent, extra) {
      return Object.assign({ intent: intent, heard: heard, words: wordCount(text) }, extra || {});
    };

    if (!text) return result("unknown");

    if (context.pendingTrouble) {
      if (TROUBLE_REPLIES.cancel.test(text)) return result("trouble_cancel");
      for (const reason of ["unclear", "technique", "longer"]) {
        if (TROUBLE_REPLIES[reason].test(numbers)) return result("trouble", { reason: reason });
      }
    }

    if (PATTERNS.stopListening.test(text)) return result("stop_listening");
    if (PATTERNS.help.test(text)) return result("help");
    if (PATTERNS.thanks.test(text) || isThanks(text)) return result("thanks");
    if (PATTERNS.stop.test(text)) return result("stop", { bare: text });

    if (!HEAT_WORDS.test(text)) {
      if (PATTERNS.louder.test(text)) return result("louder", { repeat: /\bhear\b/.test(text) });
      if (PATTERNS.quieter.test(text)) return result("quieter");
    }
    if (PATTERNS.normalSpeed.test(text)) return result("normal_speed");
    if (PATTERNS.slower.test(text)) return result("slower");
    if (PATTERNS.faster.test(text)) return result("faster");

    if (PATTERNS.troubleUnclear.test(text)) return result("trouble", { reason: "unclear" });
    if (PATTERNS.troubleLonger.test(text)) return result("trouble", { reason: "longer" });
    if (PATTERNS.troubleTechnique.test(text)) return result("trouble", { reason: "technique" });
    if (PATTERNS.troubleAsk.test(text)) return result("trouble_ask");

    // Timers
    if (PATTERNS.timerPause.test(text)) return result("timer_pause");
    if (PATTERNS.timerReset.test(text)) return result("timer_reset");
    if (PATTERNS.timerLeft.test(text)) return result("timer_left");
    const duration = parseDuration(numbers);
    if (duration && PATTERNS.timerAdd.test(numbers)) return result("timer_add", { seconds: duration });
    if (duration && !PATTERNS.stepNumber.test(numbers)) {
      const onlyDuration = /^(\d+(\.\d+)? ?(hours?|hrs?|minutes?|mins?|seconds?|secs?) ?(and )?)+$/.test(numbers.replace(/\b(a|an)\b/g, "").trim());
      if (PATTERNS.timerSetWord.test(numbers) || onlyDuration) return result("timer_set", { seconds: duration });
    }
    if (PATTERNS.timerStart.test(text)) return result("timer_start");

    // Questions about the recipe
    if (PATTERNS.stepsLeft.test(text)) return result("steps_left");
    if (PATTERNS.where.test(text) && !PATTERNS.stepNumber.test(numbers)) return result("where");
    if (PATTERNS.temperature.test(text)) return result("temperature");
    const howMuch = text.match(PATTERNS.howMuch);
    if (howMuch) {
      const ingredient = cleanIngredient(howMuch[4]);
      if (ingredient && !NOT_INGREDIENTS.test(ingredient)) return result("how_much", { ingredient: ingredient });
    }
    if (PATTERNS.allIngredients.test(text)) return result("all_ingredients");
    if (PATTERNS.stepIngredients.test(text)) return result("step_ingredients");

    // Moving between steps
    if (/\b(go |step )?back (1|a)( step)?$/.test(numbers)) return result("back");
    const stepMatch = numbers.match(PATTERNS.stepNumber);
    if (stepMatch) {
      const number = parseInt(stepMatch[1] || stepMatch[2], 10);
      const after = numbers.slice(stepMatch.index + stepMatch[0].length).trim();
      if (wordCount(after) > 3) {
        // "Step 2. Heat the oil in a large pan…" is a step being read out, not a command.
        return result("unknown", { addressed: false });
      }
      if (/\b(done|finished|completed?)\b/.test(text)) return result("complete", { step: number });
      return result("read_step", { step: number });
    }
    if (PATTERNS.lastStep.test(text)) return result("read_step", { step: "last" });
    if (PATTERNS.firstStep.test(numbers)) return result("read_step", { step: 1 });

    if (PATTERNS.complete.test(text) || PATTERNS.completeLoose.test(text)) return result("complete");
    if (PATTERNS.next.test(text)) return result("next");
    if (!/\bbe (right )?back\b/.test(text) && PATTERNS.back.test(numbers)) return result("back");
    if (PATTERNS.repeat.test(numbers)) return result("repeat");
    if (PATTERNS.ready.test(text)) return result("read_current", { start: true });
    if (PATTERNS.read.test(text)) return result("read_current");

    return result("unknown", { addressed: ADDRESSED.test(text) });
  }

  // ---------------------------------------------------------------------
  // "How did that step go?" and "How did it turn out?"
  // ---------------------------------------------------------------------

  const FEEDBACK = {
    unclear: /\b(unclear|confus\w*|(did not|do not|cannot|could not) (understand|follow|get it|get what)|not clear|(instruction|instructions|step|wording) (was|were|is|are) (vague|wrong|confusing|unclear|not clear)|did not make sense|made no sense|makes no sense|wording|vague)\b/,
    technique: /\b(tricky|technique|hard|difficult|fiddly|struggled|struggling|struggle|skill|messy|burnt|burned|stuck|stuck to|went wrong|messed up|tough)\b/,
    longer: /\b(longer|ages|forever|slow|too long|took a while|took a long time|more time|extra time|longer than|over time|was slow)\b/,
    fine: /\b(fine|good|great|easy|ok|okay|alright|all right|went well|smooth|smoothly|perfect|no problems?|no issues?|nice|brilliant|lovely|simple|not bad|well|grand|sorted|no trouble)\b/,
  };

  // Turns a spoken or typed answer into one of the four choices, and keeps
  // the cook's own words when they say more than a word or two.
  function parseFeedback(raw) {
    const original = String(raw || "").replace(/\s+/g, " ").trim();
    let text = normalise(raw).replace(/\bnot (too |that |very |really |so |at all )?(hard|difficult|tricky|confusing|long|bad|slow|tough)\b/g, " fine ");
    let feeling = "";
    for (const key of ["unclear", "technique", "longer", "fine"]) {
      if (FEEDBACK[key].test(text)) {
        feeling = key;
        break;
      }
    }
    const note = wordCount(normalise(raw)) >= 4 ? (original.charAt(0).toUpperCase() + original.slice(1)).slice(0, 300) : "";
    return { feeling: feeling, note: note };
  }

  function parseOutcome(raw) {
    const text = normalise(raw).replace(/\bnot (too )?bad\b/g, " okay ").replace(/\bnot (very |that |so )?(good|great)\b/g, " bad ");
    if (/\b(bad|did not (go|work|turn out)|terrible|awful|burnt|burned|disaster|went wrong|rubbish|horrible|poor|failed|mess|ruined|inedible)\b/.test(text)) return "bad";
    if (/\b(great|brilliant|amazing|perfect|delicious|lovely|fantastic|excellent|good|awesome|tasty|yummy|loved|superb|spot on|well)\b/.test(text)) return "great";
    if (/\b(ok|okay|fine|alright|all right|decent|average|so so|not sure|mixed|meh)\b/.test(text)) return "ok";
    return "";
  }

  // While CulinaAI is talking, the microphone hears its voice and the cook's
  // together. This looks at the last few words for a stop word that isn't in
  // what CulinaAI is saying, so "stop" works even mid-sentence.
  const STOP_WORDS = new Set(["stop", "wait", "enough", "quiet", "shush", "shh", "hush", "pause", "cancel", "silence"]);
  const STOP_PAIRS = ["hang on", "hold on", "shut up", "be quiet", "hold up"];

  function heardStop(raw, spokenText) {
    const spoken = " " + normalise(spokenText) + " ";
    const words = normalise(raw).split(" ").filter(Boolean);
    const tail = words.slice(-4);
    for (const word of tail) {
      if (STOP_WORDS.has(word) && spoken.indexOf(" " + word + " ") === -1) return true;
    }
    const tailText = " " + tail.join(" ") + " ";
    return STOP_PAIRS.some(function (pair) {
      return tailText.indexOf(" " + pair + " ") !== -1 && spoken.indexOf(" " + pair + " ") === -1;
    });
  }

  // A quick check on half-heard speech, so "stop" cuts the voice off at once.
  function isStopPhrase(raw) {
    const text = stripWrappers(normalise(raw));
    return wordCount(text) <= 4 && /\b(stop|shush|shh|hush|quiet|hang on|hold on|wait|enough|cancel|pause|shut up|silence)\b/.test(text)
      && !/\b(timer|clock|listening)\b/.test(text);
  }

  // ---------------------------------------------------------------------
  // Kitchen words that differ between countries
  // ---------------------------------------------------------------------

  const INGREDIENT_SYNONYMS = [
    ["coriander", "cilantro", "dhania", "coriander leaves"],
    ["aubergine", "eggplant", "brinjal"],
    ["courgette", "zucchini"],
    ["spring onion", "scallion", "green onion"],
    ["mince", "minced beef", "ground beef", "ground meat", "minced meat", "keema"],
    ["chickpea", "garbanzo", "garbanzo bean", "chana"],
    ["double cream", "heavy cream", "whipping cream"],
    ["single cream", "light cream"],
    ["plain flour", "all purpose flour", "maida"],
    ["self raising flour", "self rising flour"],
    ["wholemeal flour", "whole wheat flour", "atta"],
    ["gram flour", "chickpea flour", "besan"],
    ["caster sugar", "superfine sugar"],
    ["icing sugar", "powdered sugar", "confectioners sugar"],
    ["bicarbonate of soda", "bicarb", "baking soda"],
    ["cornflour", "cornstarch", "corn starch"],
    ["pepper", "bell pepper", "capsicum"],
    ["chilli", "chili", "chile", "mirch"],
    ["prawn", "shrimp"],
    ["rocket", "arugula"],
    ["beetroot", "beet"],
    ["swede", "rutabaga"],
    ["mangetout", "snow pea"],
    ["tomato puree", "tomato paste"],
    ["pak choi", "bok choy"],
    ["stock", "broth"],
    ["yoghurt", "yogurt", "curd", "dahi"],
    ["cumin", "jeera"],
    ["turmeric", "haldi"],
    ["ginger", "adrak"],
    ["garlic", "lahsun"],
    ["coconut milk", "nariyal milk"],
    ["rapeseed oil", "canola oil"],
    ["butter beans", "lima beans"],
    ["broad beans", "fava beans"],
    ["minced pork", "ground pork", "pork mince"],
    ["chicken mince", "ground chicken", "minced chicken"],
    ["turkey mince", "ground turkey", "minced turkey"],
  ];

  function singular(word) {
    if (/ies$/.test(word)) return word.slice(0, -3) + "y";
    if (/(ches|shes|oes|sses)$/.test(word)) return word.slice(0, -2);
    if (/s$/.test(word) && !/ss$/.test(word)) return word.slice(0, -1);
    return word;
  }

  function singularPhrase(phrase) {
    return phrase.split(" ").map(singular).join(" ");
  }

  function containsPhrase(line, phrase) {
    if (!phrase) return false;
    const escaped = phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "s? ");
    return new RegExp("\\b" + escaped + "(s|es)?\\b").test(line);
  }

  const GENERIC_WORDS = /^(fresh|chopped|of|the|some|my|this|that|a|an|and|large|small|medium|dried|ground|whole|sliced|diced|minced|to|in|for|it|is)$/;

  // Which recipe ingredient lines match what the cook asked about. "cilantro"
  // finds "fresh coriander", and "aubergines" finds "1 aubergine".
  function findIngredient(query, lines) {
    const asked = singularPhrase(normalise(query).replace(/^(the|some|my) /, ""));
    if (!asked) return { lines: [], asked: "", recipeWord: "" };
    const tidyLines = (lines || []).map(function (line) {
      return { original: line, text: singularPhrase(normalise(line)) };
    });

    const candidates = [asked];
    INGREDIENT_SYNONYMS.forEach(function (group) {
      const tidyGroup = group.map(singularPhrase);
      if (tidyGroup.some(function (word) { return containsPhrase(asked, word) || containsPhrase(word, asked); })) {
        tidyGroup.forEach(function (word) {
          if (candidates.indexOf(word) === -1) candidates.push(word);
        });
      }
    });

    for (const candidate of candidates) {
      const found = tidyLines.filter(function (line) { return containsPhrase(line.text, candidate); });
      if (found.length) {
        return {
          lines: found.map(function (line) { return line.original; }),
          asked: asked,
          recipeWord: candidate === asked ? "" : candidate,
        };
      }
    }

    // Last try: any meaningful word of the question ("how much of the red onion" -> "onion").
    const words = asked.split(" ").filter(function (word) { return word.length > 2 && !GENERIC_WORDS.test(word); });
    for (let i = words.length - 1; i >= 0; i -= 1) {
      const found = tidyLines.filter(function (line) { return containsPhrase(line.text, words[i]); });
      if (found.length) {
        return { lines: found.map(function (line) { return line.original; }), asked: asked, recipeWord: "" };
      }
    }
    return { lines: [], asked: asked, recipeWord: "" };
  }

  // Ingredient lines that the step mentions by name.
  function ingredientsInStep(stepText, lines) {
    const step = singularPhrase(normalise(stepText));
    return (lines || []).filter(function (line) {
      const words = singularPhrase(normalise(line)).split(" ").filter(function (word) {
        return word.length > 3 && !GENERIC_WORDS.test(word) && !/^\d/.test(word) && !/^(tbsp|tsp|tablespoon|teaspoon|gram|cup|pinch|clove|handful|bunch|piece|optional|taste|finely|roughly|peeled)$/.test(word);
      });
      return words.some(function (word) { return containsPhrase(step, word); });
    });
  }

  // ---------------------------------------------------------------------
  // Temperatures: Celsius, Fahrenheit and gas marks
  // ---------------------------------------------------------------------

  const GAS_MARKS = [[140, 1], [150, 2], [170, 3], [180, 4], [190, 5], [200, 6], [220, 7], [230, 8], [240, 9]];

  function toFahrenheit(celsius) {
    return Math.round((celsius * 9 / 5 + 32) / 5) * 5;
  }

  function toCelsius(fahrenheit) {
    return Math.round(((fahrenheit - 32) * 5 / 9) / 5) * 5;
  }

  function gasMark(celsius) {
    let best = GAS_MARKS[0];
    GAS_MARKS.forEach(function (pair) {
      if (Math.abs(pair[0] - celsius) < Math.abs(best[0] - celsius)) best = pair;
    });
    return Math.abs(best[0] - celsius) <= 15 ? best[1] : null;
  }

  // Finds the oven temperature, gas mark or hob heat in a step's text.
  function findTemperature(text) {
    const source = String(text || "");
    const degrees = source.match(/(\d{2,3})\s*(?:°|º|degrees?|deg)\s*(c|f|celsius|fahrenheit|centigrade)?\b(\s*\(?\s*fan\s*\)?|\s*fan\b)?/i);
    if (degrees) {
      const value = parseInt(degrees[1], 10);
      const unit = (degrees[2] || "c").toLowerCase().startsWith("f") ? "F" : "C";
      return { kind: "oven", value: value, unit: unit, fan: Boolean(degrees[3]) };
    }
    const gas = source.match(/gas\s*mark\s*(\d)/i);
    if (gas) return { kind: "gas", value: parseInt(gas[1], 10) };
    const heat = source.match(/\b(medium[\s-]high|medium[\s-]low|high|medium|low|gentle|moderate)\s+heat\b/i);
    if (heat) return { kind: "heat", value: heat[1].toLowerCase().replace("-", " ") };
    return null;
  }

  function describeTemperature(found, english) {
    if (!found) return "";
    if (found.kind === "heat") return found.value + " heat";
    if (found.kind === "gas") {
      const celsius = { 1: 140, 2: 150, 3: 170, 4: 180, 5: 190, 6: 200, 7: 220, 8: 230, 9: 240 }[found.value];
      if (english === "en-US") return "gas mark " + found.value + ", that is about " + toFahrenheit(celsius) + " degrees Fahrenheit";
      return "gas mark " + found.value + ", that is about " + celsius + " degrees Celsius";
    }
    const fan = found.fan ? " fan" : "";
    if (found.unit === "F") {
      if (english === "en-US") return found.value + " degrees Fahrenheit" + fan;
      return found.value + " degrees Fahrenheit, that is about " + toCelsius(found.value) + " degrees Celsius" + fan;
    }
    if (english === "en-US") return found.value + " degrees Celsius" + fan + ", that is about " + toFahrenheit(found.value) + " degrees Fahrenheit";
    const mark = gasMark(found.value);
    if ((english === "en-GB" || english === "en-IE") && mark && !found.fan) {
      return found.value + " degrees Celsius, or gas mark " + mark;
    }
    return found.value + " degrees Celsius" + fan;
  }

  // ---------------------------------------------------------------------
  // Making recipe text sound right when read aloud
  // ---------------------------------------------------------------------

  function speechText(text, english) {
    let spoken = String(text || "");
    spoken = spoken
      .replace(/(\d{2,3})\s*(?:°|º)\s*C\b/g, function (match, value) {
        const celsius = parseInt(value, 10);
        return english === "en-US"
          ? value + " degrees Celsius, that is about " + toFahrenheit(celsius) + " Fahrenheit,"
          : value + " degrees Celsius";
      })
      .replace(/(\d{2,3})\s*(?:°|º)\s*F\b/g, "$1 degrees Fahrenheit")
      .replace(/(\d)\s*(?:°|º)/g, "$1 degrees")
      .replace(/\b(\d+)\s*\/\s*2\b/g, function (match, top) { return top === "1" ? "half" : match; })
      .replace(/\b1\s*\/\s*4\b/g, "a quarter")
      .replace(/\b3\s*\/\s*4\b/g, "three quarters")
      .replace(/\b1\s*\/\s*3\b/g, "a third")
      .replace(/½/g, " and a half").replace(/¼/g, " and a quarter").replace(/¾/g, " and three quarters")
      .replace(/(\d)\s*kg\b/gi, "$1 kilograms")
      .replace(/(\d)\s*g\b/g, "$1 grams")
      .replace(/(\d)\s*ml\b/gi, "$1 millilitres")
      .replace(/\btbsp\b\.?/gi, "tablespoons")
      .replace(/\btsp\b\.?/gi, "teaspoons")
      .replace(/(\d)\s*oz\b/gi, "$1 ounces")
      .replace(/(\d)\s*lbs?\b/gi, "$1 pounds")
      .replace(/(\d)\s*mins?\b/gi, "$1 minutes")
      .replace(/(\d)\s*hrs?\b/gi, "$1 hours")
      .replace(/(\d)\s*cm\b/gi, "$1 centimetres")
      .replace(/\bapprox\.?/gi, "about")
      .replace(/\be\.g\./gi, "for example")
      .replace(/&/g, " and ")
      .replace(/\*\*/g, "")
      // "1 teaspoons" -> "1 teaspoon"
      .replace(/\b1 (tablespoon|teaspoon|gram|kilogram|millilitre|ounce|pound|minute|hour|centimetre)s\b/g, "1 $1");
    if (english === "en-US" || english === "en-CA") {
      spoken = spoken.replace(/\bhob\b/gi, "stove").replace(/\b(under|preheat) the grill\b/gi, "$1 the broiler");
    }
    return spoken.replace(/\s+/g, " ").replace(/,\s*([.!?;:,])/g, "$1").trim();
  }

  // Splits text into pieces short enough for the browser's voice (Chrome stops long ones).
  function speechChunks(text) {
    const sentences = String(text || "").match(/[^.!?;]+[.!?;]*/g) || [];
    const chunks = [];
    sentences.forEach(function (sentence) {
      let piece = sentence.trim();
      while (piece.length > 180) {
        let cut = piece.lastIndexOf(",", 180);
        if (cut < 60) cut = piece.lastIndexOf(" ", 180);
        if (cut < 1) cut = 180;
        chunks.push(piece.slice(0, cut + 1).trim());
        piece = piece.slice(cut + 1).trim();
      }
      if (piece) chunks.push(piece);
    });
    return chunks;
  }

  return {
    normalise: normalise,
    stripWrappers: stripWrappers,
    wordsToNumbers: wordsToNumbers,
    parseDuration: parseDuration,
    parse: parse,
    isStopPhrase: isStopPhrase,
    heardStop: heardStop,
    parseFeedback: parseFeedback,
    parseOutcome: parseOutcome,
    findIngredient: findIngredient,
    ingredientsInStep: ingredientsInStep,
    findTemperature: findTemperature,
    describeTemperature: describeTemperature,
    toFahrenheit: toFahrenheit,
    gasMark: gasMark,
    speechText: speechText,
    speechChunks: speechChunks,
    INGREDIENT_SYNONYMS: INGREDIENT_SYNONYMS,
  };
});
