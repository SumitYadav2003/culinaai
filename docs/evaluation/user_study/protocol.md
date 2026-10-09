# User study plan

A short, informal usability study: a few people make a recipe with CulinaAI, cook
it (or at least follow it in cooking mode), and fill in a questionnaire.

**Before you start:** if this is part of your degree or research you'll publish, get
ethics approval through your university first and use its consent template if it has
one. Nobody under 18. Nobody with a serious food allergy should cook in the study:
they can still try the allergy settings without eating the result.

## Who and how many

- 5 to 10 adults who cook at home at least now and then. Five people find most of the
  big usability problems; more gives a steadier SUS score.
- Try to include a mix: someone who rarely cooks, someone confident, at least one
  person who isn't a native English speaker (for the voice assistant).
- Each session takes about 45 to 60 minutes if they cook, 25 minutes if they only walk
  through cooking mode.

## What you need

- A laptop or phone with Chrome or Edge (the voice assistant needs the browser's
  speech recognition), signed in to a fresh CulinaAI test account for that participant.
- The live site, culinaai.onrender.com.
- The information sheet and consent form, the questionnaire and the voice checklist
  (this folder), printed or as forms.
- A copy of `responses_template.csv` in `user_study/private/` to type the answers into.

## The session

1. **Welcome (5 min).** Explain the study using the information sheet. Make it clear
   you're testing CulinaAI, not them, and that they can stop at any time. Get consent
   signed. Give them a code (P1, P2, ...) and use only that from now on.
2. **Make a recipe (10 min).** Ask them to make something they'd actually eat with
   ingredients they have. Suggest they try at least one setting that matters to them
   (a diet, an allergy, "Everyday healthy", a cuisine). Don't help unless they're stuck
   for more than a minute; note where they hesitate.
3. **Read the result (5 min).** Ask them to look at the nutrition, cost, carbon and
   cuisine notes and to say out loud what they think each one means. Note anything
   they misread.
4. **Cook in cooking mode (20 to 40 min).** Turn on the voice assistant. Ask them to
   try the commands on the voice checklist at natural moments while cooking. Tick each
   command as understood (CulinaAI did the right thing first time), understood after
   repeating, or not understood. After each step, CulinaAI asks how it went: let them
   answer however they like.
5. **Questionnaire (10 min).** SUS first, straight after using CulinaAI, without
   discussing it. Then the CulinaAI questions and the open questions.
6. **Short chat (5 min).** Ask what was best, what was most annoying, and what they'd
   change. Write down their words.

If they don't cook, do step 4 by reading through the recipe in cooking mode and
trying the voice commands, and write "no" in the `cooked` column.

## What to record (in responses.csv)

| Column | What goes in it |
|---|---|
| participant | P1, P2, ... (never a name) |
| date | The date of the session |
| device | For example "laptop, Chrome" or "Android phone, Chrome" |
| cooking_confidence | 1 (rarely cook) to 5 (very confident), asked at the start |
| cooked | yes or no |
| minutes_to_first_recipe | From opening the generate page to seeing the recipe |
| sus1 ... sus10 | The ten SUS answers, 1 (strongly disagree) to 5 (strongly agree) |
| f_... | The CulinaAI questions, 1 to 5 |
| voice_commands_tried | How many commands from the checklist they tried |
| voice_commands_understood | How many worked first time |
| problems | Short notes of where they got stuck or misread something |
| comments | Their words from the open questions and the chat |

Leave a cell empty if they skipped a question; the SUS score is only worked out for
people who answered all ten.

## Afterwards

- Run `python manage.py evaluate --study docs/evaluation/user_study/private/responses.csv`.
- Keep signed consent forms somewhere safe and separate from the answers, as your
  university's rules say. Don't commit either to GitHub.
- In the dissertation, report the number of participants, the mean SUS score with its
  standard deviation, the voice success rate, and the main problems people ran into,
  with quotes by participant code.
- You can delete the participants' test accounts once the study is written up.
