# Thought
Thought is an open source social media platform project for sharing your thoughts.

## Features:
### 1) Posts (w image support)
The rudimentary system of Thought allows users to publish and edit posts.
### 2) Direct Messaging
For now, Thought only allows Direct Messaging among users, GC capabilities might be added later
### 3) Git Repository Hosting for each user
Thought allows the hosting of Git Repositories, It is a worse off version of Github and depending on my life's circumstances, i might add more features later down the line.

### 4) Study / Quiz (optional)
Upload PDFs, and Thought extracts their text into a local `.txt` file that is used as context when you ask the AI for multiple-choice questions. Generated quizzes are stored so you can retake them, every answer is recorded, and the Analytics page charts correct/wrong answers per topic and over time.
* Needs `pip install openai pypdf` and an OpenRouter key (`OPENROUTER_API_KEY` env var or `openrouterapikey.txt`). Uploading works without a key; generating does not.
* Files are stored under `QUIZ_PATH` (default `QUIZ/`), the model is set by `QUIZ_MODEL`.
* Turn the whole section off with `QUIZ_ENABLED=0`.

#### Thats all for now, if you want to check it out, you can self host it, As I said, depending on my circumstances, i might host it on [Here](http://thought.amazeryogo.in)
