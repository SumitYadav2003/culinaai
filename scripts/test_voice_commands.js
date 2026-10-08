/*
 * Tests for the hands-free cooking voice commands.
 *
 * Run from the project root (needs Node.js, nothing to install):
 *     node scripts/test_voice_commands.js
 *
 * Each line is something a cook might say, written the way the browser's
 * speech recognition tends to type it, and what CulinaAI should do.
 * Prints how many were understood and lists any that weren't.
 */
const voice = require("../frontend/static/js/cooking_voice_commands.js");

const PHRASES = [
  // Next step
  ["next", "next"], ["Next step", "next"], ["what's next", "next"], ["What's next?", "next"],
  ["go on", "next"], ["carry on", "next"], ["and then?", "next"], ["move on", "next"],
  ["keep going", "next"], ["continue", "next"], ["next one please", "next"], ["OK next", "next"],
  ["what do I do next", "next"], ["what comes after this", "next"], ["skip this step", "next"],
  ["can you go to the next step please", "next"], ["next step mate", "next"], ["right, what's next", "next"],
  ["then what", "next"], ["onwards", "next"],

  // Back
  ["back", "back"], ["go back", "back"], ["previous step", "back"], ["go back to the last step", "back"],
  ["the one before", "back"], ["can you go back please", "back"], ["previous", "back"], ["step back", "back"],

  // Read a step
  ["read step 1", "read_step"], ["read step one for me", "read_step"], ["read the second step", "read_step"],
  ["what's step two", "read_step"], ["tell me step 3", "read_step"], ["go to step 4", "read_step"],
  ["skip to step five", "read_step"], ["step 2", "read_step"], ["read step to", "read_step"],
  ["read the first step", "read_step"], ["start from the beginning", "read_step"], ["read the final step", "read_step"],
  ["jump to step twelve", "read_step"],

  // Read the current step
  ["read the step", "read_current"], ["read it", "read_current"], ["read it out", "read_current"],
  ["what does it say", "read_current"], ["what do I do now", "read_current"], ["what now", "read_current"],
  ["read this step for me", "read_current"], ["can you read it to me please", "read_current"],
  ["start", "read_current"], ["I'm ready", "read_current"], ["let's go", "read_current"], ["let's start", "read_current"],
  ["read me the instructions", "read_current"], ["what am I supposed to do", "read_current"],

  // Repeat
  ["repeat", "repeat"], ["say that again", "repeat"], ["again please", "repeat"], ["pardon?", "repeat"],
  ["come again", "repeat"], ["sorry what", "repeat"], ["what was that", "repeat"], ["one more time", "repeat"],
  ["what did you say", "repeat"], ["I didn't catch that", "repeat"], ["sorry?", "repeat"], ["can you repeat that", "repeat"],
  ["read it again", "repeat"], ["once more", "repeat"],

  // Stop talking
  ["stop", "stop"], ["stop reading", "stop"], ["stop talking", "stop"], ["shush", "stop"], ["quiet", "stop"],
  ["be quiet", "stop"], ["that's enough", "stop"], ["hang on", "stop"], ["hold on", "stop"], ["wait", "stop"],
  ["one sec", "stop"], ["just a second", "stop"], ["hang on a tick", "stop"], ["OK OK", "stop"], ["got it", "stop"],
  ["pause", "stop"], ["cancel", "stop"], ["stop please", "stop"],

  // Mark complete
  ["done", "complete"], ["I'm done", "complete"], ["done that", "complete"], ["finished", "complete"],
  ["finished that", "complete"], ["all done", "complete"], ["mark it as done", "complete"], ["mark as complete", "complete"],
  ["tick it off", "complete"], ["that step is done", "complete"], ["completed", "complete"], ["I've finished", "complete"],
  ["yep done", "complete"], ["step 3 is done", "complete"],

  // Timers
  ["start the timer", "timer_start"], ["start timer", "timer_start"], ["timer on", "timer_start"],
  ["resume the timer", "timer_start"], ["time me", "timer_start"], ["kick off the timer", "timer_start"],
  ["pause the timer", "timer_pause"], ["stop the timer", "timer_pause"], ["hold the timer", "timer_pause"],
  ["reset the timer", "timer_reset"], ["restart the timer", "timer_reset"], ["start the timer again", "timer_reset"],
  ["set a timer for 5 minutes", "timer_set"], ["set a timer for five minutes", "timer_set"],
  ["give me ten minutes", "timer_set"], ["remind me in 3 minutes", "timer_set"], ["timer for 90 seconds", "timer_set"],
  ["set the timer to twenty five minutes", "timer_set"], ["half an hour timer", "timer_set"],
  ["set a timer for a minute and a half", "timer_set"], ["five minute timer", "timer_set"], ["10 minutes", "timer_set"],
  ["give me another two minutes", "timer_add"], ["add 5 minutes", "timer_add"], ["two more minutes please", "timer_add"],
  ["add another minute", "timer_add"],
  ["how long left", "timer_left"], ["how much longer", "timer_left"], ["how long's left on that", "timer_left"],
  ["how much time is left", "timer_left"], ["is it done yet", "timer_left"], ["how long to go", "timer_left"],
  ["how many minutes left", "timer_left"], ["time left?", "timer_left"], ["how long does this take", "timer_left"],

  // Where am I
  ["where was I", "where"], ["where am I", "where"], ["which step am I on", "where"], ["what step is this", "where"],
  ["I've lost my place", "where"],
  ["how many steps left", "steps_left"], ["how many more steps", "steps_left"], ["am I nearly done", "steps_left"],
  ["are we almost there", "steps_left"],

  // Ingredients and temperatures
  ["how much salt", "how_much", "salt"], ["how much salt do I need", "how_much", "salt"],
  ["how many eggs", "how_much", "eggs"], ["how much cilantro do I need", "how_much", "cilantro"],
  ["how much of the butter goes in", "how_much", "butter"], ["what amount of flour", "how_much", "flour"],
  ["how many garlic cloves do I need for this", "how_much", "garlic cloves"],
  ["what temperature", "temperature"], ["what temperature is the oven", "temperature"], ["how hot", "temperature"],
  ["what gas mark", "temperature"], ["what heat should the hob be on", "temperature"], ["what do I preheat to", "temperature"],
  ["what's the oven temp", "temperature"],
  ["what do I need for this step", "step_ingredients"], ["what ingredients", "step_ingredients"],
  ["what goes in", "step_ingredients"], ["what am I adding", "step_ingredients"],
  ["read me the ingredients", "all_ingredients"], ["list the ingredients", "all_ingredients"],

  // Trouble (feeds learning from your cooking)
  ["I'm having trouble", "trouble_ask"], ["I'm stuck", "trouble_ask"], ["it's not working", "trouble_ask"],
  ["I need help with this step", "trouble_ask"], ["something went wrong", "trouble_ask"],
  ["I don't understand", "trouble", "unclear"], ["this doesn't make sense", "trouble", "unclear"],
  ["I'm confused", "trouble", "unclear"], ["what does that mean", "trouble", "unclear"],
  ["this is taking ages", "trouble", "longer"], ["it's taking too long", "trouble", "longer"],
  ["the chicken is not cooked yet", "trouble", "longer"], ["I need more time", "trouble", "longer"],
  ["this is tricky", "trouble", "technique"], ["this is really hard", "trouble", "technique"],
  ["I'm struggling", "trouble", "technique"], ["how do I do that", "trouble", "technique"],

  // Voice
  ["slower please", "slower"], ["slow down", "slower"], ["too fast", "slower"], ["faster", "faster"],
  ["speed up", "faster"], ["louder", "louder"], ["speak up", "louder"], ["I can't hear you", "louder"],
  ["quieter", "quieter"], ["too loud", "quieter"], ["turn it down", "quieter"],
  ["help", "help"], ["what can I say", "help"], ["what can you do", "help"],
  ["thanks", "thanks"], ["thank you", "thanks"], ["cheers", "thanks"], ["cheers mate", "thanks"], ["ta", "thanks"],
  ["nice one", "thanks"], ["brilliant", "thanks"], ["thanks a lot", "thanks"],
  ["stop listening", "stop_listening"], ["turn off the voice", "stop_listening"], ["goodbye", "stop_listening"],
  ["bye", "stop_listening"], ["I'm done cooking", "stop_listening"],

  // Wrapped in politeness and fillers
  ["hey Culina, what's next", "next"], ["um can you read step 3 for me please", "read_step"],
  ["could you please start the timer", "timer_start"], ["okay so what do I do now", "read_current"],
  ["right, how much butter do I need", "how_much", "butter"],

  // Not commands: chatter in the kitchen should be left alone
  ["I'll be right back", "unknown"], ["the kids are home from school", "unknown"],
  ["turn up the heat", "unknown"], ["did you feed the dog", "unknown"],

  // More everyday phrasings
  ["alright what's after that", "next"], ["ok I've done that bit", "complete"],
  ["right I'm finished with this one", "complete"], ["next bit", "next"], ["can I have the next step", "next"],
  ["what was step 2 again", "read_step"], ["remind me what step three said", "read_step"],
  ["sorry could you say that one more time", "repeat"], ["eh what", "repeat"], ["shh", "stop"],
  ["give me a minute", "stop"], ["start a 7 minute timer", "timer_set"],
  ["set the timer for quarter of an hour", "timer_set"], ["how long have I got left", "timer_left"],
  ["how long on the timer", "timer_left"], ["is the timer done", "timer_left"],
  ["how much water do I need", "how_much"], ["how many onions", "how_much"],
  ["what's the temperature again", "temperature"], ["oven temperature", "temperature"],
  ["I don't get it", "trouble"], ["this is a bit fiddly", "trouble"], ["read it slower", "slower"],
  ["can you speak a bit louder", "louder"], ["what's left", "steps_left"], ["skip ahead", "next"],
  ["back one", "back"], ["go back one step", "back"], ["where are we", "where"], ["cheers that's great", "thanks"],
  ["that's lovely thanks", "thanks"], ["let's begin", "read_current"], ["what do we do first", "read_current"],
  ["read step number six", "read_step"], ["can you tell me the next step", "next"], ["finished step 4", "complete"],
  ["timer please", "timer_start"], ["stop the clock", "timer_pause"], ["switch off the mic", "stop_listening"],
  ["thank you very much", "thanks"], ["OK what do I do after this", "next"], ["move to the next step", "next"],
  ["next instruction", "next"], ["go to the next one", "next"], ["previous one", "back"], ["take me back", "back"],
  ["can we go back a step", "back"], ["read out step 5", "read_step"], ["what does step 6 say", "read_step"],
  ["what's the first step", "read_step"], ["say it again please", "repeat"], ["sorry I missed that", "repeat"],
  ["could you repeat the step", "repeat"], ["hush now", "stop"], ["okay that's enough thanks", "stop"],
  ["hold on a sec", "stop"], ["I've done it", "complete"], ["done with this step", "complete"],
  ["this one's done", "complete"], ["put a timer on for 8 minutes", "timer_set"],
  ["start a timer for 2 minutes", "timer_set"], ["set timer 15 minutes", "timer_set"], ["pause it", "stop"],
  ["how long has the timer got", "timer_left"], ["how much time do I have", "timer_left"],
  ["how much milk", "how_much"], ["how many tomatoes do I need", "how_much"],
  ["what temperature should the oven be", "temperature"], ["how hot should the pan be", "temperature"],
  ["what ingredients do I need for this", "step_ingredients"], ["I'm a bit lost", "trouble_ask"],
  ["I'm not sure what to do", "trouble_ask"], ["it's going wrong", "trouble_ask"], ["that's confusing", "trouble"],
  ["could you speak slower", "slower"], ["a bit quicker please", "faster"], ["what can I ask you", "help"],
  ["much appreciated", "thanks"], ["turn off listening", "stop_listening"], ["we're done here", "stop_listening"],
  ["which step are we on", "where"], ["how many steps are left", "steps_left"], ["go", "read_current"],
  ["read", "read_current"], ["tell me what to do", "read_current"], ["what's this step", "read_current"],
  ["skip", "next"], ["what do I need", "step_ingredients"], ["the oven, what temperature", "temperature"],
];

const PENDING = [
  ["it took longer", "trouble", "longer"], ["the first one", "trouble", "longer"],
  ["the instructions were unclear", "trouble", "unclear"], ["number two", "trouble", "unclear"],
  ["tricky technique", "trouble", "technique"], ["three", "trouble", "technique"],
  ["never mind", "trouble_cancel"], ["no", "trouble_cancel"],
];

// CulinaAI's own sentences, heard back through the microphone, must not act as commands.
const ECHOES = [
  ["Timer set for 1 minute. I'll tell you when it's done.", "unknown"],
  ["Add the chopped onion and sauté for 3-4 minutes until softened and translucent.", "unknown"],
  ["Step 2. Heat the vegetable oil in a large pan over medium heat.", "unknown"],
  ["Timer started: 4 minutes. It'll finish at 17:47. I'll tell you when it's done.", "unknown"],
  ["Here we go. Step 3. Add the chicken pieces to the pan", "unknown"],
];

// Answers to "How did that step go?"
const FEEDBACK = [
  ["it was fine", "step_feedback", "fine"], ["good", "step_feedback", "fine"], ["no problems", "step_feedback", "fine"],
  ["not too hard actually", "step_feedback", "fine"], ["it took longer because my pan was small", "step_feedback", "longer"],
  ["the instructions were confusing", "step_feedback", "unclear"], ["I didn't understand the bit about the rice", "step_feedback", "unclear"],
  ["bit tricky flipping the chicken", "step_feedback", "technique"], ["the onions burnt a little", "step_feedback", "technique"],
  ["I used red onion instead", "step_feedback", ""], ["skip", "feedback_skip"], ["next", "feedback_skip"],
  ["never mind", "feedback_skip"], ["start the timer", "timer_start"], ["repeat", "repeat"], ["stop", "stop"],
];

const OUTCOMES = [["it was delicious", "great"], ["really good", "great"], ["not bad", "ok"], ["it was okay", "ok"],
  ["I burnt it", "bad"], ["not great to be honest", "bad"]];

let passed = 0;
const failures = [];

function check(list, context) {
  list.forEach(function (row) {
    const [phrase, intent, extra] = row;
    const result = voice.parse(phrase, context);
    let ok = result.intent === intent;
    if (ok && extra && intent === "how_much") ok = result.ingredient === extra;
    if (ok && extra && intent === "trouble") ok = result.reason === extra;
    if (ok) passed += 1;
    else failures.push(`"${phrase}" -> ${JSON.stringify(result)} (expected ${intent}${extra ? " " + extra : ""})`);
  });
}

check(PHRASES, {});
check(PENDING, { pendingTrouble: true });
check(ECHOES, {});

FEEDBACK.forEach(function (row) {
  const [phrase, intent, feeling] = row;
  const result = voice.parse(phrase, { pendingFeedback: true });
  const ok = result.intent === intent && (feeling === undefined || result.feeling === feeling);
  if (ok) passed += 1;
  else failures.push(`answer "${phrase}" -> ${JSON.stringify(result)} (expected ${intent} ${feeling || ""})`);
});

OUTCOMES.forEach(function (row) {
  const result = voice.parse(row[0], { pendingOutcome: true });
  if (result.intent === "outcome" && result.outcome === row[1]) passed += 1;
  else failures.push(`outcome "${row[0]}" -> ${JSON.stringify(result)} (expected ${row[1]})`);
});

// "Stop" heard mixed in with CulinaAI's own voice
const STOPS = [
  [voice.heardStop("heat the vegetable oil in a large pan stop", "Step 2. Heat the vegetable oil in a large pan."), true],
  [voice.heardStop("over medium heat hang on", "over medium heat and stir"), true],
  [voice.heardStop("leave to rest and wait", "Leave to rest and wait 5 minutes."), false],
  [voice.heardStop("heat the vegetable oil", "Heat the vegetable oil."), false],
];
STOPS.forEach(function (pair, index) {
  if (pair[0] === pair[1]) passed += 1;
  else failures.push(`stop check ${index + 1}: got ${pair[0]}`);
});

// Helpers used when answering questions
const lines = ["2 tbsp fresh coriander, chopped", "1 large aubergine", "400 g beef mince", "1 tsp salt", "2 garlic cloves"];
const helperChecks = [
  [voice.findIngredient("cilantro", lines).lines[0], "2 tbsp fresh coriander, chopped"],
  [voice.findIngredient("cilantro", lines).recipeWord, "coriander"],
  [voice.findIngredient("eggplants", lines).lines[0], "1 large aubergine"],
  [voice.findIngredient("ground beef", lines).lines[0], "400 g beef mince"],
  [voice.findIngredient("garlic cloves", lines).lines[0], "2 garlic cloves"],
  [voice.findIngredient("saffron", lines).lines.length, 0],
  [voice.parseDuration("set a timer for 1 minute 30 seconds"), 90],
  [voice.parseDuration(voice.wordsToNumbers("twenty five minutes")), 1500],
  [voice.parseDuration("half an hour"), 1800],
  [voice.describeTemperature(voice.findTemperature("Preheat the oven to 180°C."), "en-US"), "180 degrees Celsius, that is about 355 degrees Fahrenheit"],
  [voice.describeTemperature(voice.findTemperature("Preheat the oven to 180°C."), "en-GB"), "180 degrees Celsius, or gas mark 4"],
  [voice.describeTemperature(voice.findTemperature("Fry over medium-high heat."), "en-GB"), "medium high heat"],
  [voice.speechText("Add 200g rice and 1 tbsp oil.", "en-GB"), "Add 200 grams rice and 1 tablespoon oil."],
  [voice.speechText("Preheat the oven to 180°C.", "en-US"), "Preheat the oven to 180 degrees Celsius, that is about 355 Fahrenheit."],
  [voice.speechText("Put the pan on the hob.", "en-US"), "Put the pan on the stove."],
  [voice.ingredientsInStep("Fry the garlic and stir in the coriander.", lines).length, 2],
];
helperChecks.forEach(function (pair, index) {
  if (pair[0] === pair[1]) passed += 1;
  else failures.push(`helper check ${index + 1}: got ${JSON.stringify(pair[0])}, expected ${JSON.stringify(pair[1])}`);
});

const total = PHRASES.length + PENDING.length + ECHOES.length + FEEDBACK.length + OUTCOMES.length + STOPS.length + helperChecks.length;
console.log(`Voice commands: ${passed} of ${total} understood correctly (${Math.round((passed / total) * 100)}%).`);
if (failures.length) {
  console.log("\nNot understood:");
  failures.forEach(function (line) { console.log("  " + line); });
  process.exit(1);
}
