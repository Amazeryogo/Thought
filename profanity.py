import re

# A simple list of profane words for demonstration purposes.
# In a real-world scenario, you might want to use a more comprehensive library or external list.
BANNED_WORDS = [
    "badword1",
    "badword2",
    "profanity3",
    # Add more as needed
]

def filter_profanity(text):
    if not text:
        return text

    filtered_text = text
    for word in BANNED_WORDS:
        # Use regex for word boundaries to avoid filtering parts of legitimate words
        pattern = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
        filtered_text = pattern.sub('*' * len(word), filtered_text)

    return filtered_text
