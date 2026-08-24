# Skills For serious AI users

https://github.com/MaxMoldmann/skills

My agent skills that I use every day to improve my efficiency.

These skills are designed to be easy to adapt, and composable. They should work with any model. Some are my own skills, some are modificatons of other peoples great work and some are straight copies of great skills like caveman, unslop, llm-council and wayfinder. Hack around with them. Make them your own. Enjoy.

If you want to keep up with changes to these skills, and any new ones I create, watch or Star this repository.

## Installation

```bash
gh repo clone MaxMoldmann/skills
```

## Why These Skills Exist

Others have asked me for the skills I work with - I like good skill collections, so I am distributing this as a collection of great skills. I wrote some of these skills myself to improve my life while working with coding agents. Some are other peoples great work that I am redistributing either modified or unmodified.  

### #1: speak

Local Kokoro text-to-speech for agent responses.
Supports 8 different realistic on-demand voices even on a CPU when no supported GPU is available.
Supports /speak on, /speak off and mentioning of "(speak:silent)" to supress during one turn.

### #2: commander

The idea from this came from the Firstmate skill from Kun Chen: 
https://github.com/kunchenguid/firstmate

Our attention is limited, so we run one Agent to manage a crew of other Agents. 
Commander is my Herdr-native supervisor skill for AI-agent fleets. It runs inside Herdr (HERDR_ENV=1), monitors panes through the Commander watcher plugin, learns approval rules from Captain decisions, queues unknown blocks for review, and delegates work to crewmates. You can even go AFK and let the Commander know your intent or goal for certain sessions he should supervise.

### #3: grill-me-softly

> "No-one knows exactly what they want"
>
> David Thomas & Andrew Hunt, [The Pragmatic Programmer](https://www.amazon.co.uk/Pragmatic-Programmer-Anniversary-Journey-Mastery/dp/B0833F1T3V)

This is an adaptation from Matt Pocock's grill-me skills.
https://github.com/mattpocock/skills/blob/main/skills/productivity/grilling/SKILL.md

• **One-at-a-time pacing**: Better for deliberate design choices; Matt asks every currently independent question in one batch.

• **Confidence ordering**: Lowest-GPP questions surface first; Matt orders only by dependency readiness.

• **Adaptive routing**: Non-recommended/freeform answers reprioritize, prune, or add questions immediately.

• **State management**: Tracks skips, raw/normalized answers, retry state, remaining count, and reprioritizations.

• **More User control**: No-input retry, skip for later, stop-early + accept recommendations - which is enabled by the fact that all the high confidence decisions are being asked last.

• **Finish with summary**: Agent outlines his understanding, as a strong confirmation signal to the user that the matter is thoroughly understood.  

### #4: grill-me-softly-m365

Adaptation of the grill-me-softly skill that is designed to work without a code repository in a simple Chat window.

On Windows with M365 Copilot chat: Copy to <OneDrive>/Documents/Cowork/Skills/<skill-name-folder>

### #5: wayfinder

Copy of Matt Pocock's great wayfinder skill:
https://github.com/mattpocock/skills/blob/main/skills/engineering/wayfinder/SKILL.md

Use it as a first step to create requirements for areas with a lot of uncertainties. Plan a huge chunk of work, it becomes a map of investigation tickets on the issue tracker — resolve them one at a time until the way to the destination is clear.

### #6: handoff

Adaptation of Matt Pocock's great handoff skill:
https://github.com/mattpocock/skills/blob/main/skills/productivity/handoff/SKILL.md

This version adds a fitting name for the temporary handoff file and some other adjustments.

### #7: caveman

Copy of Julius Brussee's great caveman skill:
https://github.com/JuliusBrussee/caveman/blob/main/skills/caveman/SKILL.md

AI talk like caveman, save tokens.

### #8: unslop

Copy from poteto's great pstack skills:
https://github.com/cursor/plugins/blob/main/pstack/skills/unslop/SKILL.md

Removes AI patterns and add's a human voice to all AI output.

### #9: llm-council 

Adapted from Ole Lehmann's skill (shared by Charlie J. Hills: https://x.com/charliejhills/status/2049140787200528725). Built on Andrej Karpathy's LLM Council methodology: dispatch the same query to multiple models, have them peer-review anonymously, then synthesize via a chairman. This skill applies that pattern using sub-agents with different thinking lenses (Contrarian, First Principles, Expansionist, Outsider, Executor) instead of different model providers.

### Summary

Enjoy.
