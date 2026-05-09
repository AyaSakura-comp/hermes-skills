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

6. **Read the answer with `browser_vision`:**
   ```
   browser_vision(question='Describe Gemini\'s complete answer in detail, including all key points, formatting, and any code blocks or structured content.')
   ```

7. **Send screenshot via Discord** using MEDIA: path format (see Important Notes below):
   ```
   # Take a vision screenshot for the Discord message
   result = browser_vision(question='Describe the full page including Gemini\'s question and answer together.')
   # result contains screenshot_path — use it as MEDIA: attachment
   send_message(message='MEDIA:<screenshot_path>\n\n[Summary text]', target='discord')
   ```

## Important Notes

- **Always use `browser_vision` to read answers** — `browser_snapshot` does not capture Gemini's rich content well.
- **When sending screenshots, always use `MEDIA: <path>` format** via `send_message`, NEVER use markdown image links. This ensures Discord delivers it as a proper image attachment.
- If the send button is disabled, the input might be empty or validation is needed. Try clicking elsewhere first.
- If Gemini takes too long to respond (>5s), wait a bit then try `browser_vision` again.
- The page may show a "Temporary chat" banner near the top — this is normal, proceed regardless.
- Always send screenshots/images via Discord as full image attachments, not just file paths.

## When to Use

- User asks to ask Gemini a question
- User wants to interact with Google Gemini
- User wants to pose a question or get information from Gemini
- User asks to chat with or query Gemini

## When NOT to Use

- Use `web_search` for simple factual queries
- Use `google-workspace` skill for Gmail/Calendar/Docs tasks
- Use `browser` skill only if user needs general browser navigation tasks