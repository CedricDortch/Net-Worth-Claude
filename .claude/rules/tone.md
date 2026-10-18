---
paths:
  - "networth/report.py"
  - "networth/templates/**"
---

# Tone: Brutally Honest

The report says what the numbers say.

## Rules

1. Every statement is backed by a number from the analysis.
2. No fake positivity. A bad result is called bad.
3. Criticize the finances, never the person. No insults.
4. Good results get clear, direct praise. No hedging.
5. The summary opens with the verdict, then the reasons.
6. Short, plain sentences. No jargon without a one-line explanation.
7. Wording is chosen by grade and by specific findings; keep templates in `report.py`, not scattered across modules.

## Verdict templates by grade

| Grade | Example |
|---|---|
| A | "Your finances are strong. You're in the top 8% for your age with $640,000. Keep doing exactly what you're doing." |
| B | "You're well ahead of most people your age (top 20%). One or two fixes would put you in the top tier." |
| C | ≥ 60th pct: "You're ahead of most people your age (top 25%), but your score is held back." · 40–60th: "You're average for your age (top 43%). Average is not a plan." · < 40th: "You're behind most people your age (bottom 30%)." |
| D | < 50th pct: "You are behind. You're in the bottom 35% for your age, $X behind the median, and your net worth is shrinking." · ≥ 50th: "Your finances have serious weak spots. You're in the top 34% for your age." |
| F | "Your finances are in serious trouble. Your net worth is −$15,900 and has been falling about $3,918 a year. If nothing changes, you will be $22,198 in the hole in 10 years." |

**The headline must never contradict the rank.** A low grade can come from debt or no cash while net worth is fine for the age, so D/F headlines always state the real standing (tested).

After the headline, the verdict lists: score and grade; "X points from a B" when within 5 points; the biggest drag (the component losing the most weighted points); up to 3 problems and 3 strengths; components not scored.

## Finding templates

- "You are paying 24.9% interest on $4,200 of credit card debt. That costs you about $1,050 a year for nothing."
- "Your car is 40% of your net worth and it loses value every year."
- "You have 0.8 months of expenses in cash. One emergency puts you into debt."
- "Your income went up 40% in 4 years but your net worth barely moved. You are spending your raises."
- Couples: "Partner 2 holds 90% of the household's debt."
- Assumptions: "You assumed 14% a year. The long-run average is closer to 7–10%."

## Required text

Every report ends with: "This report gives estimates based on public averages and simple models. It is not financial, tax, or legal advice."
