---
repo: zensharma0512-a11y/Zenify
---

I built Zenify: snap a photo of your meal and it logs the calories and macros for you 📸🍛

Logging meals by hand is tedious, so I wanted the photo to do the work.

How it works:
→ An AI vision model spots every food on the plate and estimates the grams
→ Each item is checked against a built-in database of 348 foods and drinks, 148 of them Indian (yes, golgappa and kaapi are in there)
→ You can adjust anything, then log calories, protein, carbs, fat, fibre, sugar and sodium

It grew into a full daily tracker:
• AI diet and workout plans built around your goal
• Steps, water and sleep goals
• A levelling "Hunter" system with daily quests, XP and ranks from E to Monarch, so staying consistent feels like a game
• Five languages, including Hindi
• Installable as a web app, with zero npm dependencies

One rule I built it around: never trust the model blindly. Every answer is matched against the database, and anything it can't verify is clearly labelled as an AI estimate.

The code is on GitHub 👉 https://github.com/zensharma0512-a11y/Zenify

I'd love feedback, especially on foods it gets wrong!

#BuildInPublic #AI #ComputerVision #HealthTech
