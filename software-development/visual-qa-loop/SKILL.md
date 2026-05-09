---
name: visual-qa-loop
description: A workflow for performing Visual Quality Assurance (VQA) by extracting keyframes from automated test videos for visual inspection.
---

# visual-qa-loop

A specialized workflow for performing Visual Quality Assurance (VQA) on automated tests when the agent needs to "see" the outcome of a process (e.g., a game, a complex animation, or a UI interaction) that is running in a headless or automated browser.

## Trigger
Use this skill when:
- An automated test (Playwright, Selenium, etc.) fails or achieves sub-optimal results (e.g., a bot fails to reach a score in a game).
- The user asks to "see" or "verify" the visual experience of a running automation.
- You need to diagnose visual bugs (misalignments, rendering errors, or physics issues) that aren't captured by text-based logs.

## Workflow

### 1. Configure Recording
Ensure the automation tool is configured to capture video.
- **Playwright**: Set `video: 'on'` in `playwright.config.js`.

### 2. Locate the Video
After the test run, inspect the output directory (e.g., `test-results/`) to find the `.webm` or `.mp4` file associated with the test.

### 3. Extract Keyframes via FFmpeg
Since the agent cannot "watch" a video directly, use `ffmpeg` via the `terminal` tool to extract specific frames for analysis.
- **Extract at a specific timestamp**:
  ```bash
  ffmpeg -i <video_path> -ss <HH:MM:SS> -vframes 1 <output_name>.png
  ```
- **Extract multiple frames** (e.g., start, middle, end, or error moment):
  ```bash
  ffmpeg -i <video_path> -ss 00:00:02 -vframes 1 frame_2s.png
  ffmpeg -i <video_path> -ss 00:00:10 -vframes 1 frame_10s.png
  ```

### 4. Visual Analysis
Pass the extracted image paths to the `vision_analyze` tool. 
- **Question Strategy**: Ask specific questions about the elements you expect to see (e.g., "Is the player character visible?", "Is the obstacle rendered correctly?", "What is the score displayed?").

### 5. Synthesis & Iteration
Combine the vision results with the assertion errors from the test logs:
- *Example*: "Log says score 0, Vision says Score: 0 and the bird is falling too fast" $\rightarrow$ **Action**: Adjust gravity in `game.js`.
- *Example*: "Log says element not clickable, Vision shows the button is covered by a popup" $\rightarrow$ **Action**: Fix CSS/Z-index.

## Pitfalls
- **File Paths**: Always use `realpath` to ensure `vision_analyze` can access the file if using absolute paths.
- **Timestamp Precision**: Use `-ss` *before* `-i` for faster seeking, or *after* `-i` for more precise seeking (though slower).
- **Resolution**: Ensure the extracted frames are of sufficient resolution to read text (like scores).
