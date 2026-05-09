---
name: playwright-canvas-game-testing
description: Specialized workflow for testing high-frequency inputs in HTML5 Canvas-based games using Playwright.
---
# Playwright Canvas Game Testing

Specialized workflow for testing high-frequency inputs in HTML5 Canvas-based games using Playwright without triggering timeouts or IPC congestion.

## Problem
Simulating physical input via `page.mouse.click()` or `page.keyboard.press()` inside high-frequency loops (e.g., a game loop or a "Flappy Bird" agent) often leads to:
- `Error: mouse.click: Test timeout of XXXms exceeded.`
- High IPC (Inter-Process Communication) overhead.
- Event loop congestion in the Playwright driver.

## Solution: Direct Context Injection
Instead of simulating the hardware event, trigger the game logic directly within the browser context using `page.evaluate()`.

### Step 1: Expose Game API
In your game source code (`game.js`), attach the control functions to the `window` object.

```javascript
// Inside game.js
window.game = {
  jump: () => {
    // your existing jump logic
    bird.velocity = -jumpStrength;
  },
  getScore: () => score,
  isGameOver: () => gameState === 'end'
};
```

### Step 2: Use `page.evaluate` in Playwright
In your test script (`*.spec.js`), call these methods directly.

```javascript
// Instead of:
// await page.mouse.click(x, y);

// Use:
await page.evaluate(() => window.game.jump());
```

## Benefits
- **Zero Latency**: Bypasses the entire input event pipeline.
- **Reliability**: No risk of timing out due to "slow" mouse movements or key presses.
- **Determinism**: Allows the test agent to act with perfect temporal precision.