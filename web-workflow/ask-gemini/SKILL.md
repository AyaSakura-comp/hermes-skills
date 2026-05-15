---
name: ask-gemini
description: >
  Ask Google Gemini a question via browser automation at gemini.google.com.
  Use when the user asks to ask Gemini a question, wants to interact with
  Google Gemini, or wants to pose a question or get information from Gemini.
---

# Ask Gemini (Google)

Ask Google Gemini a question via browser automation at gemini.google.com.

## Prerequisites

- User must already be logged into Google account in browser (check for account avatar in top-right)
- Browser session already initialized (`browser_navigate` required)

## Steps

1. **Navigate to Gemini:**
   ```
   browser_navigate(url='https://gemini.google.com')
   ```

2. **Wait for page to load and find input field.** Use `browser_snapshot` or `browser_vision(annotate=true)` to locate the textarea. Look for a textbox labeled "Enter a prompt for Gemini". Note its ref (e.g., `@e12`). Also note the send button ref (e.g., `@e10`).

3. **Type the question:**
   ```
   browser_type(ref='@<input_ref>', text='<your question>')
   ```

4. **Click the send button:**
   ```
   browser_click(ref='@<send_button_ref>')
   ```

5. **Wait a few seconds** for Gemini to generate a response.

7. **Read the answer — use `browser_console` for long responses (RECOMMENDED):**
   ```
   browser_console(expression='document.querySelector("main").innerText')
   ```
   This extracts the FULL response text from the DOM in one shot. Never scroll through screenshots for long Gemini responses — it's inefficient and often misses sections.

   If `browser_console` fails or returns empty, fall back to `browser_vision`:
   ```
   browser_vision(question='Read ALL of Gemini\'s response text from the beginning. Include ALL sections, bullet points, and data. Don\'t stop until you\'ve read everything Gemini wrote.')
   ```

8. **Send text result via Discord** (default — no screenshot):
   ```
   send_message(message='<formatted text summary>', target='discord')
   ```

   除非使用者特別要求截圖，否則預設只傳文字結果。

## Important Notes

- **Always use `browser_vision` to read answers** — `browser_snapshot` does not capture Gemini's rich content well.
- **預設不傳截圖**，只傳送文字結果摘要。使用者明確要求時才額外傳截圖。
- If the send button is disabled, the input might be empty or validation is needed. Try clicking elsewhere first.
- If Gemini takes too long to respond (>5s), wait a bit then try `browser_vision` again.
- The page may show a "Temporary chat" banner near the top — this is normal, proceed regardless.

## When to Use

- User asks to ask Gemini a question
- User wants to interact with Google Gemini
- User wants to pose a question or get information from Gemini
- User asks to chat with or query Gemini

## When NOT to Use

- Use `web_search` for simple factual queries
- Use `google-workspace` skill for Gmail/Calendar/Docs tasks
- Use `browser` skill only if user needs general browser navigation tasks