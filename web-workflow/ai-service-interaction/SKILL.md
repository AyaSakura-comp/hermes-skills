---
name: ai-service-interaction
title: AI Service Interaction Protocol
description: A structured process for dealing with AI or restricted web services (like Gemini, ChatGPT, proprietary dashboards) that often require user authentication or fail due to anti-bot measures.
---
## Workflow Steps

This skill outlines the necessary steps to attempt accessing an AI service while anticipating authentication walls and redirects.

### 1. Initial Attempt (Direct Navigation)
1.  Use `browser_navigate` to go to the primary service URL (e.g., `gemini.google.com`).
2.  Wait for the page load.
3.  Check for any visible sign-in/authentication dialogs in the snapshot.
4.  If a sign-in is required (`Sign in` button visible), **STOP**. Do not proceed with the task.

### 2. Authentication Block Detected (Fallback Procedure)
If an authentication wall is encountered:
1.  Inform the user that authentication is required and that the task cannot be completed without credentials.
2.  Offer fallbacks:
    *   A. Use general web search (e.g., `google_search`) to find the information without the AI's direct summary.
    *   B. Confirm if the user is willing to log in or if a different, publicly accessible knowledge source should be used.

### 3. Redirect/Access Denied (Alternative Entry Point)
If the initial URL fails or redirects to an error/access denied page (like the previous experience with `google.com/ai`):
1.  Analyze the error/redirect page content for clues (e.g., "IP address detected," "Unusual activity").
2.  Suggest alternative, non-API driven methods (e.g., standard Google Search or citing the problem for manual review).

## Pitfalls and Notes
*   Always assume that AI chat services may impose access limits or require logins.
*   When a navigation fails due to blocks, do not keep repeating the navigation. Change the tool or the file.
*   Sensitive tasks should be verified manually by the user rather than blindly scripted.
