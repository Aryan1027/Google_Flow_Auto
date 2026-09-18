"""
Centralized selectors for the Google Flow web interface (https://flow.google.com / https://labs.google/fx/tools/flow).
All UI-specific selectors are isolated in this file for ease of maintenance.
"""

# Authentication and Account Selectors
AUTH_SELECTORS = [
    "a[href*='accounts.google.com']",
    "button:has-text('Sign in')",
    "button:has-text('Log in')",
    "button[aria-label*='Sign in' i]",
    "[data-action='sign-in']",
    "div:has-text('Sign in to continue')",
]

# User Logged-In Indicators
AUTHENTICATED_SELECTORS = [
    "button[aria-label*='Google Account' i]",
    "img[alt*='Google Account' i]",
    "div[aria-label*='Account' i]",
    "button[aria-label*='Settings' i]",
]

# Prompt Input Elements
PROMPT_INPUT_SELECTORS = [
    "textarea[placeholder*='prompt' i]",
    "textarea[placeholder*='Describe' i]",
    "textarea[placeholder*='video' i]",
    "textarea[aria-label*='prompt' i]",
    "div[contenteditable='true'][role='textbox']",
    "div[contenteditable='true']",
    "input[type='text'][placeholder*='prompt' i]",
    "textarea",
]

# Generation Trigger (Generate / Submit Button)
GENERATE_BUTTON_SELECTORS = [
    "button:has-text('Generate')",
    "button:has-text('Create')",
    "button[aria-label*='Generate' i]",
    "button[aria-label*='Submit' i]",
    "button[aria-label*='Send' i]",
    "button svg[data-icon='send']",
]

# Generation In-Progress / Processing Indicators
GENERATING_INDICATORS = [
    "[aria-label*='Generating' i]",
    "[aria-label*='Processing' i]",
    "div:has-text('Generating...')",
    "div:has-text('Creating video...')",
    "div:has-text('Rendering...')",
    "mat-progress-spinner",
    "mat-progress-bar",
    ".spinner",
    ".loading-spinner",
    "[role='progressbar']",
]

# Generation Completion / Finished Video Element
GENERATED_VIDEO_SELECTORS = [
    "video[src]",
    "video:not([src=''])",
    ".video-card video",
    "[data-test-id*='generated-video']",
    "[data-test-id*='asset-card'] video",
    "div.asset-card",
]

# Download Action Selectors
DOWNLOAD_BUTTON_SELECTORS = [
    "button[aria-label*='Download' i]",
    "a[aria-label*='Download' i]",
    "button:has-text('Download')",
    "[data-test-id='download-button']",
    "button[aria-label*='Export' i]",
]

# Context / More Options Menu (Three dots)
MORE_OPTIONS_SELECTORS = [
    "button[aria-label*='More options' i]",
    "button[aria-label*='More actions' i]",
    "button[aria-label*='Menu' i]",
    "mat-icon:has-text('more_vert')",
    "button svg[data-icon='more-vert']",
]

# Error or Limit Messages
ERROR_ALERT_SELECTORS = [
    "div[role='alert']",
    "div:has-text('Quota exceeded')",
    "div:has-text('Rate limit')",
    "div:has-text('Generation failed')",
    "div:has-text('Try again later')",
    "div:has-text('Something went wrong')",
]
