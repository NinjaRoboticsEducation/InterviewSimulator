<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{{TITLE}}</title>
  <link rel="stylesheet" href="styles.css">
  <script src="script.js" defer></script>
</head>
<body>
  <nav class="lang-toggle no-print" aria-label="Resume language">
    <button type="button" data-lang="en" class="active" aria-pressed="true">English</button>
    <button type="button" data-lang="ja" aria-pressed="false">日本語</button>
  </nav>
  <p class="sr-only" id="language-status" aria-live="polite">English resume displayed</p>
  {{RESUME_EN}}
  {{RESUME_JA}}
</body>
</html>
